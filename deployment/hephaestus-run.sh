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
    language=java
    if grep -q -oP "\-\-language scala" <<< "$args"; then
      language=scala
    fi
    doc2json.sh -d "$(dirname $libpath)" -l $libname -L "$language"
    if [ $? -ne 0 ]; then
      return 1
    fi
  fi

  rm -rf libs

  # Create a directory containing API docs (in JSON format) coming from
  # the given stdlib and library being exercised.
  mkdir libs

  if [ ! -f $libpath/pom.xml ]; then
    cp $stdlib/* libs
  fi
  cp $libpath/json-docs/* libs

  if [ -f $libpath/pom.xml ]; then
    rm -rf ~/.m2
    mvn -f $libpath/pom.xml dependency:tree
    mvn -f $libpath/dependency.xml dependency:tree

    classpath=$(mvn -f $libpath/pom.xml dependency:build-classpath -Dmdep.outputFile=/dev/stdout -q)
    depspath=$(mvn -f $libpath/dependency.xml dependency:build-classpath -Dmdep.outputFile=/dev/stdout -q)
    classpath="$classpath:$depspath"
  else
    classpath="$(pwd)"
  fi

  rulespath=$libpath/api-rules.json
  if [ ! -f $rulespath ]; then
    # Create api-rules.json based on common prefix
    ls $libpath/json-docs | $basedir/create-api-rules.py > $rulespath
  fi

  base_args="--iterations 10000000 --batch 30 -P -L --transformations 0 \
    --max-depth 2 --generator api -k \
    --library-path "$classpath" --api-doc-path libs --api-rules $rulespath \
    --max-conditional-depth 3 $args"

  if [ ! -d bugs/$libname-base ]; then
    echo "$base_args --name $libname-base" | xargs ./hephaestus.py
  fi
  if [ ! -d bugs/$libname-erase ]; then
    echo "$base_args --name $libname-erase --erase-types" | xargs ./hephaestus.py
  fi
  if [ ! -d bugs/$libname-inject ]
    echo "$base_args --name $libname-inject --inject-type-error" | xargs ./hephaestus.py
  fi
  if [ ! -d bugs/$libname-both ]; then
    echo "$base_args --name $libname-both --erase-types --inject-type-error" | xargs ./hephaestus.py
  fi
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

if [ -f priority.csv ]; then
  echo "Found priority.csv file"
  while IFS=',' read -r groupid artifactid version; do
    groupname=${groupid//./\-}
    libname="$groupname-$artifactid"
    echo "Testing library $libname"
    if [ -d "$libpath/$libname" ]; then
      run_hephaestus "$libpath/$libname" "$args"
    fi
  done < priority.csv
else
  for lib in $libpath/*; do
    echo "Testing library $(basename $lib)"
    run_hephaestus "$lib" "$args"
  done
fi
