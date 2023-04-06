#! /bin/bash

blacklist=blacklist

basedir=$(dirname "$0")
stdlib=$1
libpath=$2
args=$3

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

# Find libraries that have not been exercised yet
while read lib; do
  if grep -qoP "^$lib\$" $blacklist; then
    continue
  fi

  libname=$lib
  break
done <<< "$(ls $libpath)"


if [ -z $libname ]; then
  echo "No library found"
  exit 1
fi

libjar=$(find $libpath/$libname -maxdepth 1 -name '*.jar')

rm -rf libs

# Create a directory containing API docs (in JSON format) coming from
# the given stdlib and library being exercised.
mkdir libs
cp $stdlib/* libs
cp $libpath/$libname/json-docs/* libs

# Create api-rules.json
ls $libpath/$libname/json-docs | create-api-rules.py > api-rules.json

echo $args | xargs ./hephaestus.py --iterations 1000000 \
  --batch 30 \
  -P -L \
  --transformations 0 \
  --max-depth 2 \
  --generator api \
  --library-path $libjar \
  --api-doc-path libs \
  --api-rules api-rules.json \
  --max-conditional-depth 2

if [ $? -eq 0 ]; then
  echo "$libname" >> $blacklist
fi
