#! /bin/bash
#
# ./api-statistics.sh <stdlib-dir> <directory-of-libs> <language> <libname>
basedir=$(dirname "$0")
stdlib=$1
libpath=$2
language=$3
libname=$4


run_hephaestus()
{
  local libpath=$1
  local libname=$(basename $libpath)
  local args=$2

  if [[ ! -d "$libpath/json-docs" || -z $(find "$libpath/json-docs" -mindepth 1 -print -quit) ]]; then
    return 1
  fi

  rm -rf libs

  # Create a directory containing API docs (in JSON format) coming from
  # the given stdlib and library being exercised.
  mkdir libs
  cp $stdlib/* libs
  cp $libpath/json-docs/* libs

  rulespath=$libpath/api-rules.json
  if [ ! -f $rulespath ]; then
    # Create api-rules.json based on common prefix
    ls $libpath/json-docs | $basedir/create-api-rules.py > $rulespath
  fi

  base_args="--iterations 1 --batch 1 -P -L --transformations 0 \
    --max-depth 2 --generator api  --dry-run \
    --api-doc-path libs --api-rules $rulespath \
    --max-conditional-depth 2 --language "$language""
  echo "$base_args" | xargs ./hephaestus.py
  if [ $? -ne 0 ]; then
    echo "$libname,,,,,,,,,," >> statistics.csv
    return 0
  fi

  log=$(find bugs -name 'api-generator')
  echo $log

  # Read the file and extract the statistics
	while IFS=':' read -r key value; do
		key=$(echo "$key" | tr -d '[:space:]')  # Remove leading/trailing whitespace from the key
		value=$(echo "$value" | tr -d '[:space:]')  # Remove leading/trailing whitespace from the value

		case $key in
			"Numberofnodes") nodes="$value" ;;
			"Numberofedges") edges="$value" ;;
			"Numberofmethods") methods="$value" ;;
			"Numberofpolymorphicmethods") polymorphic_methods="$value" ;;
			"Numberoffields") fields="$value" ;;
			"Numberofconstructors") constructors="$value" ;;
			"Numberoftypes") types="$value" ;;
			"Numberoftypeconstructors") type_constructors="$value" ;;
			"Avginheritancechainsize") inheritance_chain_size="$value" ;;
			"AvgAPIsignaturesize") api_signature_size="$value" ;;
		esac
	done < <(grep -E "Number of nodes:|Number of edges:|Number of methods:|Number of polymorphic methods:|Number of fields:|Number of constructors:|Number of types:|Number of type constructors:|Avg inheritance chain size:|Avg API signature size:" $log)

  # Print the extracted statistics
  echo "$libname,$nodes,$edges,$methods,$polymorphic_methods,$fields,$constructors,$types,$type_constructors,$inheritance_chain_size,$api_signature_size" >> statistics.csv
  rm -r bugs
}

if [ -z $libpath ]; then
  echo "You need to specify the library path"
  exit 1
fi

if [ -z $stdlib ]; then
  echo "You need to specify the path for stdlib"
  exit 1
fi

if [ -z $language ]; then
  echo "You need to specify language"
fi

echo "lib,nodes,edges,methods,poly_methods,fields,constructors,types,type_con,avg_inherit_chain,sig_size" > statistics.csv

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
      run_hephaestus "$libpath/$libname" "$args"
  done < priority.csv
else
  for lib in $libpath/*; do
    echo "Testing library $(basename $lib)"
    run_hephaestus "$lib" "$args"
  done
fi
