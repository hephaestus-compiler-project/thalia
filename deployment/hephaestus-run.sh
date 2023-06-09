#! /bin/bash

basedir=$(dirname "$0")
stdlib=$1
libpath=$2
args=$3
libname=$4


run_hephaestus()
{
  local libpath=$1
  local libname=$(basename $libpath)
  local args=$2

  if [[ ! -d "$libpath/json-docs" || -z $(find "$libpath/json-docs" -mindepth 1 -print -quit) ]]; then
    # Create API specification from javadoc
    doc2json.sh -d "$(dirname $libpath)" -l $libname -L java
    if [ $? -ne 0 ]; then
      return 1
    fi
  fi

  rm -rf libs

  # Create a directory containing API docs (in JSON format) coming from
  # the given stdlib and library being exercised.
  mkdir libs
  cp $stdlib/* libs
  cp $libpath/json-docs/* libs

  rm -rf ~/.m2
  mvn -f $libpath/pom.xml dependency:tree
  mvn -f $libpath/dependency.xml dependency:tree

  classpath=$(mvn -f $libpath/pom.xml dependency:build-classpath -Dmdep.outputFile=/dev/stdout -q)
  depspath=$(mvn -f $libpath/dependency.xml dependency:build-classpath -Dmdep.outputFile=/dev/stdout -q)
  classpath="$classpath:$depspath"

  # Create api-rules.json
  ls $libpath/json-docs | $basedir/create-api-rules.py > api-rules.json

  base_args="--iterations 10000000 --batch 30 -P -L --transformations 0 \
    --max-depth 2 --generator api  \
    --library-path "$classpath" --api-doc-path libs --api-rules api-rules.json \
    --max-conditional-depth 2 $args"
  echo "$base_args" | xargs ./hephaestus.py
  echo "$base_args --erase-types" | xargs ./hephaestus.py
  echo "$base_args --inject-type-error" | xargs ./hephaestus.py
  echo "$base_args --erase-types --inject-type-error" | xargs ./hephaestus.py

  echo "$base_args --path-search-strategy ksimple" | xargs ./hephaestus.py
  echo "$base_args --erase-types --path-search-strategy ksimple" | xargs ./hephaestus.py
  echo "$base_args --inject-type-error --path-search-strategy ksimple" | xargs ./hephaestus.py
  echo "$base_args --erase-types --inject-type-error --path-search-strategy ksimple" | xargs ./hephaestus.py
}

if [ -z $libpath ]; then
  echo "You need to specify the library path"
  exit 1
fi

if [ -z $stdlib ]; then
  echo "You need to specify the path for stdlib"
  exit 1
fi


if [ ! -z $libname ]; then
  echo "Testing library $libname"
  run_hephaestus "$libpath/$libname" "$args"
  exit 0
fi

for lib in $libpath/*; do
  echo "Testing library $(basename $lib)"
  run_hephaestus "$lib" "$args"
done
