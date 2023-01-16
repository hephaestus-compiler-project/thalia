#! /usr/bin/env python3
import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup
from pathlib import Path


REGULAR_CLASS = 0
INTERFACE = 1
ABSTRACT_CLASS = 2
ENUM = 3
EXCLUDE_NAME = "<no name provided>"


def _get_super_classes_interfaces(html_doc):
    regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
    element = html_doc.select(".cover .platform-hinted .symbol")[0]
    # remove these elements
    rem_elems = element.find_all("span", {"class": "top-right-position"}) + \
        element.find_all("div", {"class": "copy-popup-wrapper"})
    for e in rem_elems:
        e.decompose()
    segs = element.text.split(": ")
    if len(segs) == 1:
        # No super classes / interfaces.
        return []
    text = element.text.split(": ")[1].replace(" , ", ",").replace(
        ", ", ",").strip(" ")
    return re.findall(regex, text)


def extract_package_name(html_doc, top_level=False):
    packages = html_doc.select(".breadcrumbs a")[1:]
    if not top_level:
        packages = packages[:-1]
    return ".".join([p.text for p in packages])


def extract_class_name(html_doc):
    return html_doc.select(".cover a")[0].text


def extract_class_type_parameters(html_doc):
    element = html_doc.select(".cover .platform-hinted .symbol")[0]
    # remove these elements
    rem_elems = element.find_all("span", {"class": "top-right-position"}) + \
        element.find_all("div", {"class": "copy-popup-wrapper"})
    for e in rem_elems:
        e.decompose()
    segs = element.text.split(": ")
    cls_text = segs[0]
    segs = cls_text.split("<")
    if len(segs) == 1:
        return []
    regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
    text = segs[1][:-2].replace(", ", ",")
    return re.findall(regex, text)


def extract_super_class(html_doc):
    classes = _get_super_classes_interfaces(html_doc)
    if not classes:
        return None
    # In general, we cannot distinguish between interfaces and classes.
    return classes[0]


def extract_class_type(html_doc):
    cl_type = html_doc.select(".cover span")[3].text
    if 'interface' in cl_type:
        return INTERFACE
    if 'abstract class' in cl_type:
        return ABSTRACT_CLASS
    if 'enum' in cl_type:
        return None
    return REGULAR_CLASS


def extract_super_interfaces(html_doc):
    classes = _get_super_classes_interfaces(html_doc)
    return classes


def extract_method_receiver(method_doc):
    regex = re.compile(
        r".*fun (<.*> )?(.*)\..+\(.*\).*")
    match = re.match(regex, method_doc.text)
    if not match:
        return None
    return match.group(2)


def extract_method_type_parameters(method_doc, is_constructor):
    if is_constructor:
        return []
    regex = re.compile(
        r".*fun <(.*)> .+\(.*\).*")
    match = re.match(regex, method_doc.text)
    if not match:
        return []
    type_parameters = match.group(1).replace(", ", ",")
    if type_parameters:
        regex = re.compile(r"(?:[^,<]|<[^>]*>)+")
        type_parameters = re.findall(regex, type_parameters)
    return type_parameters


def extract_method_return_type(method_doc, is_constructor):
    if is_constructor:
        return None
    elem = method_doc.find("span", {"class": "top-right-position"})
    if elem is None:
        import pdb; pdb.set_trace()
    elem.decompose()
    segs = method_doc.text.split("): ")
    if len(segs) == 1:
        return "Unit"
    return segs[1]


def extract_method_parameter_types(method_doc, is_constructor):
    types = []
    for param in method_doc.select(".parameter"):
        segs = param.text.strip(", ").split(": ", 1)
        assert len(segs) == 2
        types.append(segs[1])
    return types


def extract_method_name(method_doc, is_constructor):
    try:
        return method_doc.find(class_="function").text
    except IndexError:
        # We are probably in a field
        return None


def extract_field_name(field_doc):
    field_doc.find("span", {"class": "top-right-position"}).decompose()
    regex = re.compile(".*va[lr] ([^\\.]+\\.)?([^ <>\\.]+): .*")
    match = re.match(regex, field_doc.text)
    assert match is not None
    return match.group(2)


def extract_field_type(field_doc):
    return field_doc.text.split(": ")[1]


def is_field_final(field_doc):
    keywords = [
        e.text.strip(" ")
        for e in field_doc.find_all("span", {"class": "token keyword"})
    ]
    return "val" in keywords


def is_field_override(field_doc):
    keywords = [
        e.text.strip(" ")
        for e in field_doc.find_all("span", {"class": "token keyword"})
    ]
    return "override" in keywords


def extract_field_type_parameters(field_doc):
    regex = re.compile(".*va[lr] <(.+)> .+: .*")
    match = re.match(regex, field_doc.text)
    if not match:
        return []
    type_parameters = match.group(1).replace(", ", ",")
    regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
    return re.findall(regex, type_parameters)


def extract_field_receiver(field_doc):
    regex = re.compile(".*va[lr] (<.+> )?([^\\.]+)\\.[^ <>\\.]+: .*")
    match = re.match(regex, field_doc.text)
    if not match:
        return None
    return match.group(2)


def process_fields(fields):
    field_objs = []
    for field_doc in fields:
        field_obj = {
            "name": extract_field_name(field_doc),
            "type": extract_field_type(field_doc),
            "is_final": is_field_final(field_doc),
            "is_override": is_field_override(field_doc),
            "receiver": extract_field_receiver(field_doc),
            "type_parameters": extract_field_type_parameters(field_doc),
        }
        field_objs.append(field_obj)
    return field_objs


def process_methods(methods, is_constructor):
    method_objs = []
    for method_doc in methods:
        method_name = extract_method_name(method_doc, is_constructor)
        if method_name == EXCLUDE_NAME:
            continue
        ret_type = extract_method_return_type(method_doc, is_constructor)
        type_params = extract_method_type_parameters(
            method_doc, is_constructor)
        param_types = extract_method_parameter_types(
            method_doc, is_constructor)
        if param_types is None:
            continue
        method_obj = {
            "name": method_name,
            "parameters": param_types,
            "type_parameters": type_params,
            "return_type": ret_type,
            "receiver": extract_method_receiver(method_doc),
            "is_static": False,
            "is_constructor": is_constructor,
            "access_mod": "public"
        }
        method_objs.append(method_obj)
    return method_objs


def process_class(html_doc):
    class_name = extract_class_name(html_doc)
    package_name = extract_package_name(html_doc)
    full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                           cls=class_name)
    super_class = extract_super_class(html_doc)
    super_interfaces = extract_super_interfaces(html_doc)
    class_type = extract_class_type(html_doc)
    methods = html_doc.select(
        "div[data-togglable=\"Functions\"] .title .symbol")
    constructors = html_doc.select(
        "div[data-togglable=\"Constructors\"] .title .symbol")
    fields = html_doc.select(
        "div[data-togglable=\"Properties\"] .title .symbol")
    method_objs = process_methods(methods, False)
    constructor_objs = process_methods(constructors, True)
    class_obj = {
        'name': full_class_name,
        'type_parameters': extract_class_type_parameters(html_doc),
        'implements': super_interfaces,
        'inherits': super_class,
        "class_type": class_type,
        "methods": method_objs + constructor_objs,
        'fields': process_fields(fields),
        "is_class": True,
    }
    return class_obj


def process_toplevel(html_doc):
    package_name = extract_package_name(html_doc, True)
    methods = html_doc.select(
        "div[data-togglable=\"Functions\"] .title .symbol")
    fields = html_doc.select(
        "div[data-togglable=\"Properties\"] .title .symbol")
    method_objs = process_methods(methods, False)
    api = {
        "name": package_name,
        "methods": method_objs,
        "fields": process_fields(fields),
        "is_class": False,
    }
    return api


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
        help="Input directory of API docs"
    )
    return parser.parse_args()


def main():
    args = get_args()
    preprocess_args(args)
    toplevel_path = Path(args.input).joinpath("index.html")
    data = process_toplevel(file2html(toplevel_path))
    dict2json(args.output, data)
    for path in Path(args.input).rglob('*/index.html'):
        apidoc_path = str(path)
        data = process_class(file2html(apidoc_path))
        dict2json(args.output, data)


if __name__ == '__main__':
    main()
