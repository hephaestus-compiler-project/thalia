#! /bin/bash
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

  find $docpath -type f -name 'package-summary.html' |
  sed -r 's|/[^/]+$||' |
  sort |
  uniq |
  while read package; do
    doc2json -i $package -o $output --language $language
    if [ $? -ne 0 ]; then
      echo $package >> err
      return 1
    fi
  done
  return 0
}


if [ ! -z $lib ]; then
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  exit $?
fi

for lib in $libpath/*; do
  full_lib=$lib
  lib=$(basename $full_lib)
  echo "Parsing docs of $full_lib"
  parse_docs "$libpath/$lib" "$libpath/$lib/json-docs"
  if [ $? -ne 0 ]; then
    rm -r "$libpath/$lib/json-docs"
  fi
  touch $libpath/$lib/touched
done
