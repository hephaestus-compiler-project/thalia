#! /usr/bin/env python3

import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup


REGULAR_CLASS = 0
INTERFACE = 1
ABSTRACT_CLASS = 2
ENUM = 3

EXCLUDED_FILES = [
    'package-summary.html',
    'package-tree.html',
    'package-use.html'
]


def extract_package_name(html_doc):
    return html_doc.find_all(class_="subTitle")[1].find_all(text=True)[2]


def extract_class_name(html_doc):
    regex = re.compile("([A-Za-z0-9\\.]+).*")
    text = html_doc.find(class_="typeNameLabel").text
    match = re.match(regex, text)
    if not match:
        raise Exception("Cannot extract class name: {!r}".format(text))
    return match.group(1)


def extract_class_type_parameters(html_doc):
    regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
    text = html_doc.find(class_="typeNameLabel").text.split("<", 1)
    if len(text) == 1:
        return []
    text = text[1][:-1].encode("ascii", "ignore").decode().replace(" , ", ",")
    return [p[0] for p in re.findall(regex, text)]


def extract_super_class(html_doc):
    text = html_doc.select(".description .blockList pre")[0].text.encode(
        "ascii", "ignore").decode()
    text = text.replace("\n", " ")
    segs = text.split(" extends ")
    if len(segs) == 1:
        return None
    super_class = segs[1].split(" implements ")[0]
    return super_class


def extract_class_type(html_doc):
    text = html_doc.select(".description pre")[0].text
    if 'interface' in text:
        return INTERFACE
    if 'abstract class' in text:
        return ABSTRACT_CLASS
    if 'enum' in text:
        return None
    return REGULAR_CLASS


def extract_super_interfaces(html_doc):
    regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
    text = html_doc.select(".description .blockList pre")[0].text.encode(
        "ascii", "ignore").decode()
    text = text.replace("\n", " ")
    segs = text.split(" implements ")
    if len(segs) == 1:
        return []
    text = segs[1].replace(", ", ",")
    return [p for p in re.findall(regex, text)]


def extract_method_type_parameters(method_doc, is_constructor):
    if is_constructor:
        return []
    regex = re.compile(
        r"(static )?(default )?(<(.*)>)?.+")
    text = method_doc.find(class_="colFirst").text.encode(
        "ascii", "ignore").decode()
    match = re.match(regex, text)
    if not match:
        raise Exception("Cannot match method's signature {!r}".format(text))
    type_parameters = match.group(4)
    if type_parameters:
        regex = re.compile(r"(?:[^,<]|<[^>]*>)+")
        type_parameters = re.findall(regex, type_parameters)
    return type_parameters or []


def extract_method_return_type(method_doc, is_constructor):
    if is_constructor:
        return None

    regex = re.compile(
        r"(static )?(default )?(protected )?(<.*>)?(.+)")
    text = method_doc.find(class_="colFirst").text.encode(
        "ascii", "ignore").decode()
    match = re.match(regex, text)
    if not match:
        raise Exception("Cannot match method's signature {!r}".format(text))
    return_type = match.group(5)
    assert return_type is not None
    return return_type


def extract_method_parameter_types(method_doc, is_constructor):
    key = ".colConstructorName code" if is_constructor else ".colSecond code"
    regex = re.compile("\\(?([^ ,<>]+(<.*>)?)[ ]+[a-z0-9_]+,? *\\)?")
    try:
        text = method_doc.select(key)[0].text.replace(
            "\n", " ").replace("\xa0", " ").replace("\u200b", "").split(
                "(", 1)[1]
    except IndexError:
        # We probably encounter a field
        return None
    return [p[0] for p in re.findall(regex, text)]


def extract_method_access_mod(method_doc, is_con):
    column = method_doc.find(class_="colFirst")
    if column is None and is_con:
        # We have a public constructor
        return "public"

    text = column.text.encode("ascii", "ignore").decode()
    return "protected" if "protected" in text else "public"


def extract_method_name(method_doc, is_constructor):
    try:
        key = ".colConstructorName a" if is_constructor else ".colSecond a"
        return method_doc.select(key)[0].text
    except IndexError:
        # We are probably in a field
        return None


def extract_isstatic(method_doc, is_constructor):
    if is_constructor:
        return False
    return 'static' in method_doc.find(class_="colFirst").text


def is_constructor(method_doc):
    return method_doc.find(class_="colConstructorName") is not None


def extract_field_name(field_doc):
    return field_doc.select(".colSecond a")[0].text


def extract_field_type(field_doc):
    return extract_method_return_type(field_doc, False)


def extract_field_access_mod(field_doc):
    return extract_method_access_mod(field_doc, False)


def process_methods(methods, is_con):
    method_objs = []
    for method_doc in methods:
        method_name = extract_method_name(method_doc, is_con)
        isstatic = extract_isstatic(method_doc, is_con)
        ret_type = extract_method_return_type(method_doc, is_con)
        type_params = extract_method_type_parameters(method_doc, is_con)
        param_types = extract_method_parameter_types(method_doc, is_con)
        access_mod = extract_method_access_mod(method_doc, is_con)

        if param_types is None:
            # It's either a field, or a nested class
            continue
        method_obj = {
            "name": method_name,
            "parameters": param_types,
            "type_parameters": type_params,
            "return_type": ret_type,
            "is_static": isstatic,
            "is_constructor": is_con,
            "access_mod": access_mod,
        }
        method_objs.append(method_obj)
    return method_objs


def process_fields(fields):
    field_objs = []
    for field_doc in fields:
        field_name = extract_field_name(field_doc)
        field_type = extract_field_type(field_doc)
        access_mod = extract_field_access_mod(field_doc)
        isstatic = extract_isstatic(field_doc, False)

        field_obj = {
            "name": field_name,
            "type": field_type,
            "is_static": isstatic,
            "access_mod": access_mod
        }
        field_objs.append(field_obj)
    return field_objs


def _extract_fields(html_doc):
    doc = html_doc.find(class_="memberSummary")
    if doc is None:
        # Handle IllegalFormatException.html
        return []
    if doc.select("caption span")[0].text != "Fields":
        return []

    return doc.find_all(class_="rowColor") + doc.find_all(class_="altColor")


def process_class(html_doc):
    class_name = extract_class_name(html_doc)
    package_name = extract_package_name(html_doc)
    full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                           cls=class_name)
    super_class = extract_super_class(html_doc)
    super_interfaces = extract_super_interfaces(html_doc)
    class_type = extract_class_type(html_doc)
    methods = html_doc.find_all(class_="rowColor") + html_doc.find_all(
        class_="altColor")
    methods_ = []
    constructors = []
    for m in methods:
        if is_constructor(m):
            constructors.append(m)
        else:
            methods_.append(m)
    fields = _extract_fields(html_doc)
    method_objs = process_methods(methods_, False)
    constructor_objs = process_methods(constructors, True)
    field_objs = process_fields(fields)
    class_obj = {
      'name': full_class_name,
      'type_parameters': extract_class_type_parameters(html_doc),
      'implements': super_interfaces,
      'inherits': super_class,
      "class_type": class_type,
      'methods': method_objs + constructor_objs,
      'fields': field_objs,
    }
    return class_obj


def preprocess_args(args):
    # Some pre-processing to create the output directory.

    if not os.path.isdir(args.output):
        try:
            os.makedirs(args.output, exist_ok=True)
        except IOError as e:
            print(e)
            sys.exit(0)


def file2html(path):
    with open(path, 'r') as f:
        return BeautifulSoup(f, "html.parser")


def dict2json(outdir, data):
    path = os.path.join(outdir, data["name"]) + ".json"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--language",
        default="java",
        choices=["java"],
        help="Language associated with the given API docs"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Directory to output JSON files"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Input directory of API docs (in HTML format)"
    )
    return parser.parse_args()


def main():
    args = get_args()
    preprocess_args(args)
    for base in os.listdir(args.input):
        if base in EXCLUDED_FILES:
            continue
        apidoc_path = os.path.join(args.input, base)
        if not apidoc_path.endswith(".html"):
            continue
        data = process_class(file2html(apidoc_path))
        dict2json(args.output, data)


if __name__ == '__main__':
    main()
