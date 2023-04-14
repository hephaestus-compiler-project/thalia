#! /bin/bash

basedir=$(dirname "$0")

while getopts "d:l:" opt; do
  case "$opt" in
    d)  libpath=$OPTARG
        ;;
    l)  lib=$OPTARG
        ;;
  esac
done
shift $(($OPTIND - 1));


if [ -z $libpath ]; then
  echo "You need to specify the library path"
  exit 1
fi


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

  find $docpath -type f -name 'package-summary.html' |
  sed -r 's|/[^/]+$||' |
  sort |
  uniq |
  while read package; do
    $basedir/doc2json.py -i $package -o $output --language java
    if [ $? -ne 0 ]; then
      echo $package >> err
      return 1
    fi
  done
  return 0

}


if [ ! -z $lib ]; then
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  exit 0
fi

for lib in $libpath/*; do
  lib=$(basename $lib)
  echo "Parsing docs of $lib"
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  if [ $? -ne 0 ]; then
    rm -r "$libpath/$lib/json-docs"
  fi
done
