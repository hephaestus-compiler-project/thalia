#! /bin/bash

basedir=$(dirname "$0")
language=""

while getopts "d:l:L:" opt; do
  case "$opt" in
    d)  libpath=$OPTARG
        ;;
    l)  lib=$OPTARG
        ;;
    L)  language=$OPTARG
        ;;
  esac
done
shift $(($OPTIND - 1));


if [ -z $libpath ]; then
  echo "You need to specify the library path"
  exit 1
fi

if [ -z $language ]; then
  echo "You need to specify the language using the -L option"
  exit 1
fi

set +e 

parse_docs()
{
  local docpath=$1
  local output=$2
  if [ -z $docpath ]; then
    echo "You need to specify the documentation path"
    return 1
  fi

  if [ -z $output ]; then
    echo "You need to specify the output directory"
    return 1
  fi

  mkdir -p $output

  cd $docpath/html-docs
  jar xvf *.jar >/dev/null 2>&1
  cd - >/dev/null

  at_least_one=0
  find $docpath -type f -name 'package-summary.html' |
  sed -r 's|/[^/]+$||' |
  sort |
  uniq |
  while read package; do
    $basedir/doc2json.py -i $package -o $output --language $language 2>/dev/null
    if [ $? -ne 0 ]; then
      echo $package >> err
      return 1
    fi
    at_least_one=1
  done
  if [ "$at_least_one" = "0" ]; then
    echo "$docpath: no package detected" >> err
  fi
  return 0
}


if [ ! -z $lib ]; then
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  exit 0
fi

for lib in $libpath/*; do
  full_lib=$lib
  lib=$(basename $full_lib)
  echo "Parsing docs of $full_lib"
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  if [ $? -ne 0 ]; then
    rm -r "$libpath/$lib/json-docs"
  fi
done
