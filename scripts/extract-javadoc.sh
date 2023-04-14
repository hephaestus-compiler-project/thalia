#! /bin/bash

libs=$1
curdir=$(pwd)
for file in $libs/*; do
  cd $file/html-docs && jar -xvf "$(ls *javadoc.jar)" > /dev/null
  cd $curdir
done


