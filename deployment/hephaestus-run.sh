#! /bin/bash

blacklist=blacklist

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

  if [ ! -d $libpath/json-docs ]; then
    echo "Lib specification was not found for $libpath"
    return 1
  fi

  libjar=$(find $libpath -maxdepth 1 -name '*.jar')

  rm -rf libs

  # Create a directory containing API docs (in JSON format) coming from
  # the given stdlib and library being exercised.
  mkdir libs
  cp $stdlib/* libs
  cp $libpath/json-docs/* libs

  # Create api-rules.json
  ls $libpath/json-docs | $basedir/create-api-rules.py > api-rules.json

  base_args="--iterations 10000 --batch 30 -P -L --transformations 0 \
    --max-depth 2 --generator api  \
    --library-path $libjar --api-doc-path libs --api-rules api-rules.json \
    --max-conditional-depth 2 $args"
  echo "$base_args" | xargs ./hephaestus.py
  echo "$base_args --erase-types" | xargs ./hephaestus.py
  echo "$base_args --inject-type-error" | xargs ./hephaestus.py
  echo "$base_args --erase-types --inject-type-error" | xargs ./hephaestus.py
}

if [ -z $libpath ]; then
  echo "You need to specify the library path"
  exit 1
fi

if [ -z $stdlib ]; then
  echo "You need to specify the path for stdlib"
  exit 1
fi


if [ ! -f $blacklist ]; then
  touch $blacklist
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
