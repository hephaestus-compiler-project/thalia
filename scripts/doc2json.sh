#! /bin/bash

basedir=$(dirname "$0")

while getopts "d:o:" opt; do
  case "$opt" in
    d)  docpath=$OPTARG
        ;;
    o)  output=$OPTARG
        ;;
  esac
done
shift $(($OPTIND - 1));

if [ -z $docpath ]; then
  echo "You need to specify the documentation path"
  exit 1
fi

if [ -z $output ]; then
  echo "You need to specify the output directory"
  exit 1
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
  fi
done
