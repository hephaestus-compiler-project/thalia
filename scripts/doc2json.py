#! /usr/bin/env python3
from abc import ABC, abstractmethod
import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup
from pathlib import Path


class APIDocConverter(ABC):
    REGULAR_CLASS = 0
    INTERFACE = 1
    ABSTRACT_CLASS = 2
    ENUM = 3

    @abstractmethod
    def process(self, args):
        pass

    @abstractmethod
    def process_class(self, html_doc):
        pass

    def process_methods(self, methods, is_constructor):
        pass

    def process_fields(self, fields):
        pass


class JavaAPIDocConverter(APIDocConverter):
    EXCLUDED_FILES = [
        'package-summary.html',
        'package-tree.html',
        'package-use.html'
    ]

    def extract_package_name(self, html_doc):
        return html_doc.find_all(class_="subTitle")[1].find_all(text=True)[2]

    def extract_class_name(self, html_doc):
        regex = re.compile("([A-Za-z0-9\\.]+).*")
        text = html_doc.find(class_="typeNameLabel").text
        match = re.match(regex, text)
        if not match:
            raise Exception("Cannot extract class name: {!r}".format(text))
        return match.group(1)

    def extract_class_type_parameters(self, html_doc):
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        class_def = html_doc.find(class_="typeNameLabel")
        self._replace_anchors_with_package_prefix(class_def.select("a"))
        text = class_def.text.split("<", 1)
        if len(text) == 1:
            return []
        text = text[1][:-1].encode(
            "ascii", "ignore").decode().replace(" , ", ",")
        return [p[0] for p in re.findall(regex, text)]

    def extract_super_class(self, html_doc):
        supercls_defs = html_doc.select(".description .blockList pre")[0]
        self._replace_anchors_with_package_prefix(supercls_defs.select("a"))
        text = supercls_defs.text.encode("ascii", "ignore").decode()
        text = text.replace("\n", " ")
        segs = text.split(" extends ")
        if len(segs) == 1:
            return None
        super_class = segs[1].split(" implements ")[0]
        return super_class

    def extract_class_type(self, html_doc):
        text = html_doc.select(".description pre")[0].text
        if 'interface' in text:
            return self.INTERFACE
        if 'abstract class' in text:
            return self.ABSTRACT_CLASS
        if 'enum' in text:
            return self.ENUM
        return self.REGULAR_CLASS

    def extract_super_interfaces(self, html_doc):
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        text = html_doc.select(".description .blockList pre")[0].text.encode(
            "ascii", "ignore").decode()
        text = text.replace("\n", " ")
        segs = text.split(" implements ")
        if len(segs) == 1:
            return []
        text = segs[1].replace(", ", ",")
        return [p for p in re.findall(regex, text)]

    def process(self, args):
        for base in os.listdir(args.input):
            if base in self.EXCLUDED_FILES:
                continue
            apidoc_path = os.path.join(args.input, base)
            if not apidoc_path.endswith(".html"):
                continue
            data = self.process_class(file2html(apidoc_path))
            dict2json(args.output, data)

    def process_class(self, html_doc):
        class_name = self.extract_class_name(html_doc)
        package_name = self.extract_package_name(html_doc)
        full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                               cls=class_name)
        super_class = self.extract_super_class(html_doc)
        super_interfaces = self.extract_super_interfaces(html_doc)
        class_type = self.extract_class_type(html_doc)
        if class_type == self.ENUM:
            # TODO handle enums
            return None
        methods = html_doc.find_all(class_="rowColor") + html_doc.find_all(
            class_="altColor")
        methods_ = []
        constructors = []
        for m in methods:
            if self.is_constructor(m):
                constructors.append(m)
            else:
                methods_.append(m)
        fields = self._extract_fields(html_doc)
        method_objs = self.process_methods(methods_, False)
        constructor_objs = self.process_methods(constructors, True)
        field_objs = self.process_fields(fields)
        class_obj = {
          'name': full_class_name,
          'type_parameters': self.extract_class_type_parameters(html_doc),
          'implements': super_interfaces,
          'inherits': super_class,
          "class_type": class_type,
          'methods': method_objs + constructor_objs,
          'fields': field_objs,
        }
        return class_obj

    def extract_method_type_parameters(self, method_doc, is_constructor):
        if is_constructor:
            return []
        regex = re.compile(
            r"(static )?(default )?(<(.*)>)?.+")
        text = method_doc.find(class_="colFirst").text.encode(
            "ascii", "ignore").decode()
        match = re.match(regex, text)
        if not match:
            raise Exception("Cannot match method's signature {!r}".format(
                text))
        type_parameters = match.group(4)
        if type_parameters:
            regex = re.compile(r"(?:[^,<]|<[^>]*>)+")
            type_parameters = re.findall(regex, type_parameters)
        return type_parameters or []

    def extract_method_return_type(self, method_doc, is_constructor):
        if is_constructor:
            return None

        regex = re.compile(
            r"(static )?(default )?(abstract )?(protected )?(<.*>)?(.+)")
        self._replace_anchors_with_package_prefix(
            method_doc.select(".colFirst a"))
        text = method_doc.find(class_="colFirst").text.encode(
            "ascii", "ignore").decode()
        match = re.match(regex, text)
        if not match:
            raise Exception("Cannot match method's signature {!r}".format(
                text))
        return_type = match.group(6)
        assert return_type is not None
        return return_type

    def _replace_anchors_with_package_prefix(self, anchors):
        # This method replaces the text of all anchors (note that the text
        # corresponds to type names) with the fully quallified name of the
        # type. The package prefix is found in a attribute of each anchor
        # named "title".
        for anchor in anchors:
            title = anchor.get("title")
            if not title or "type parameter" in title:
                # It's either a primitive type of a type parameter. We ignore
                # them.
                continue
            package_prefix = title.split(" in ")[1]
            anchor.string.replace_with(package_prefix + "." + anchor.text)

    def extract_method_parameter_types(self, method_doc, is_constructor):
        key = (".colConstructorName code"
               if is_constructor else ".colSecond code")
        regex = re.compile("\\(?([^ ,<>]+(<.*>)?)[ ]+[a-z0-9_]+,? *\\)?")
        self._replace_anchors_with_package_prefix(
            method_doc.select(key + " a"))
        try:
            text = method_doc.select(key)[0].text.replace(
                "\n", " ").replace("\xa0", " ").replace("\u200b", "").split(
                    "(", 1)[1]
        except IndexError:
            # We probably encounter a field
            return None
        return [p[0] for p in re.findall(regex, text)]

    def extract_method_access_mod(self, method_doc, is_con):
        column = method_doc.find(class_="colFirst")
        if column is None and is_con:
            # We have a public constructor
            return "public"

        text = column.text.encode("ascii", "ignore").decode()
        return "protected" if "protected" in text else "public"

    def extract_method_name(self, method_doc, is_constructor):
        try:
            key = ".colConstructorName a" if is_constructor else ".colSecond a"
            return method_doc.select(key)[0].text
        except IndexError:
            # We are probably in a field
            return None

    def extract_isstatic(self, method_doc, is_constructor):
        if is_constructor:
            return False
        return 'static' in method_doc.find(class_="colFirst").text

    def is_constructor(self, method_doc):
        return method_doc.find(class_="colConstructorName") is not None

    def extract_field_name(self, field_doc):
        return field_doc.select(".colSecond a")[0].text

    def extract_field_type(self, field_doc):
        return self.extract_method_return_type(field_doc, False)

    def extract_field_access_mod(self, field_doc):
        return self.extract_method_access_mod(field_doc, False)

    def process_methods(self, methods, is_con):
        method_objs = []
        for method_doc in methods:
            method_name = self.extract_method_name(method_doc, is_con)
            isstatic = self.extract_isstatic(method_doc, is_con)
            ret_type = self.extract_method_return_type(method_doc, is_con)
            type_params = self.extract_method_type_parameters(method_doc,
                                                              is_con)
            param_types = self.extract_method_parameter_types(method_doc,
                                                              is_con)
            access_mod = self.extract_method_access_mod(method_doc, is_con)

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

    def process_fields(self, fields):
        field_objs = []
        for field_doc in fields:
            field_name = self.extract_field_name(field_doc)
            field_type = self.extract_field_type(field_doc)
            access_mod = self.extract_field_access_mod(field_doc)
            isstatic = self.extract_isstatic(field_doc, False)

            field_obj = {
                "name": field_name,
                "type": field_type,
                "is_static": isstatic,
                "access_mod": access_mod
            }
            field_objs.append(field_obj)
        return field_objs

    def _extract_fields(self, html_doc):
        doc = html_doc.find(class_="memberSummary")
        if doc is None:
            # Handle IllegalFormatException.html
            return []
        if doc.select("caption span")[0].text != "Fields":
            return []

        return doc.find_all(class_="rowColor") + doc.find_all(
            class_="altColor")


class KotlinAPIDocConverter(APIDocConverter):
    EXCLUDED_METHOD_NAME = "<no name provided>"

    def process(self, args):
        toplevel_path = Path(args.input).joinpath("index.html")
        data = self.process_toplevel(file2html(toplevel_path))
        dict2json(args.output, data)
        for path in Path(args.input).rglob('*/index.html'):
            apidoc_path = str(path)
            data = self.process_class(file2html(apidoc_path))
            dict2json(args.output, data)

    def process_toplevel(self, html_doc):
        package_name = self.extract_package_name(html_doc, True)
        methods = html_doc.select(
            "div[data-togglable=\"Functions\"] .title .symbol")
        fields = html_doc.select(
            "div[data-togglable=\"Properties\"] .title .symbol")
        method_objs = self.process_methods(methods, False)
        api = {
            "name": package_name,
            "methods": method_objs,
            "fields": self.process_fields(fields),
            "is_class": False,
        }
        return api

    def _get_super_classes_interfaces(self, html_doc):
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

    def extract_package_name(self, html_doc, top_level=False):
        packages = html_doc.select(".breadcrumbs a")[1:]
        if not top_level:
            packages = packages[:-1]
        return ".".join([p.text for p in packages])

    def extract_class_name(self, html_doc):
        return html_doc.select(".cover a")[0].text

    def extract_class_type_parameters(self, html_doc):
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

    def extract_super_class(self, html_doc):
        classes = self._get_super_classes_interfaces(html_doc)
        if not classes:
            return None
        # In general, we cannot distinguish between interfaces and classes.
        return classes[0]

    def extract_class_type(self, html_doc):
        cl_type = html_doc.select(".cover span")[3].text
        if 'interface' in cl_type:
            return self.INTERFACE
        if 'abstract class' in cl_type:
            return self.ABSTRACT_CLASS
        if 'enum' in cl_type:
            return self.ENUM
        return self.REGULAR_CLASS

    def extract_super_interfaces(self, html_doc):
        return self._get_super_classes_interfaces(html_doc)

    def process_class(self, html_doc):
        class_name = self.extract_class_name(html_doc)
        package_name = self.extract_package_name(html_doc)
        full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                               cls=class_name)
        super_class = self.extract_super_class(html_doc)
        super_interfaces = self.extract_super_interfaces(html_doc)
        class_type = self.extract_class_type(html_doc)
        methods = html_doc.select(
            "div[data-togglable=\"Functions\"] .title .symbol")
        constructors = html_doc.select(
            "div[data-togglable=\"Constructors\"] .title .symbol")
        fields = html_doc.select(
            "div[data-togglable=\"Properties\"] .title .symbol")
        method_objs = self.process_methods(methods, False)
        constructor_objs = self.process_methods(constructors, True)
        class_obj = {
            'name': full_class_name,
            'type_parameters': self.extract_class_type_parameters(html_doc),
            'implements': super_interfaces,
            'inherits': super_class,
            "class_type": class_type,
            "methods": method_objs + constructor_objs,
            'fields': self.process_fields(fields),
            "is_class": True,
        }
        return class_obj

    def extract_method_receiver(self, method_doc):
        regex = re.compile(
            r".*fun (<.*> )?(.*)\..+\(.*\).*")
        match = re.match(regex, method_doc.text)
        if not match:
            return None
        return match.group(2)

    def extract_method_type_parameters(self, method_doc, is_constructor):
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

    def extract_method_return_type(self, method_doc, is_constructor):
        if is_constructor:
            return None
        elem = method_doc.find("span", {"class": "top-right-position"})
        elem.decompose()
        segs = method_doc.text.split("): ")
        if len(segs) == 1:
            return "Unit"
        return segs[1]

    def extract_method_parameter_types(self, method_doc, is_constructor):
        types = []
        for param in method_doc.select(".parameter"):
            segs = param.text.strip(", ").split(": ", 1)
            assert len(segs) == 2
            types.append(segs[1])
        return types

    def extract_method_access_mod(self, method_doc):
        text = method_doc.text
        return "protected" if "protected fun" in text else "public"

    def extract_method_name(self, method_doc, is_constructor):
        try:
            return method_doc.find(class_="function").text
        except IndexError:
            # We are probably in a field
            return None

    def extract_field_name(self, field_doc):
        field_doc.find("span", {"class": "top-right-position"}).decompose()
        regex = re.compile(".*va[lr] ([^\\.]+\\.)?([^ <>\\.]+): .*")
        match = re.match(regex, field_doc.text)
        assert match is not None
        return match.group(2)

    def extract_field_type(self, field_doc):
        return field_doc.text.split(": ")[1]

    def is_field_final(self, field_doc):
        keywords = [
            e.text.strip(" ")
            for e in field_doc.find_all("span", {"class": "token keyword"})
        ]
        return "val" in keywords

    def is_field_override(self, field_doc):
        keywords = [
            e.text.strip(" ")
            for e in field_doc.find_all("span", {"class": "token keyword"})
        ]
        return "override" in keywords

    def extract_field_type_parameters(self, field_doc):
        regex = re.compile(".*va[lr] <(.+)> .+: .*")
        match = re.match(regex, field_doc.text)
        if not match:
            return []
        type_parameters = match.group(1).replace(", ", ",")
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        return re.findall(regex, type_parameters)

    def extract_field_receiver(self, field_doc):
        regex = re.compile(".*va[lr] (<.+> )?([^\\.]+)\\.[^ <>\\.]+: .*")
        match = re.match(regex, field_doc.text)
        if not match:
            return None
        return match.group(2)

    def extract_field_access_mod(self, field_doc):
        regex = re.compile("protected va[lr] .*")
        match = re.match(regex, field_doc.text)
        return "protected" if match else "public"

    def process_fields(self, fields):
        field_objs = []
        for field_doc in fields:
            field_obj = {
                "name": self.extract_field_name(field_doc),
                "type": self.extract_field_type(field_doc),
                "is_final": self.is_field_final(field_doc),
                "is_override": self.is_field_override(field_doc),
                "receiver": self.extract_field_receiver(field_doc),
                "type_parameters": self.extract_field_type_parameters(
                    field_doc),
                "access_mod": self.extract_field_access_mod(field_doc)
            }
            field_objs.append(field_obj)
        return field_objs

    def process_methods(self, methods, is_constructor):
        method_objs = []
        for method_doc in methods:
            method_name = self.extract_method_name(method_doc, is_constructor)
            if method_name == self.EXCLUDED_METHOD_NAME:
                continue
            ret_type = self.extract_method_return_type(method_doc,
                                                       is_constructor)
            type_params = self.extract_method_type_parameters(
                method_doc, is_constructor)
            param_types = self.extract_method_parameter_types(
                method_doc, is_constructor)
            access_mod = self.extract_method_access_mod(method_doc)
            if param_types is None:
                continue
            method_obj = {
                "name": method_name,
                "parameters": param_types,
                "type_parameters": type_params,
                "return_type": ret_type,
                "receiver": self.extract_method_receiver(method_doc),
                "is_static": False,
                "is_constructor": is_constructor,
                "access_mod": access_mod
            }
            method_objs.append(method_obj)
        return method_objs


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
    if data is None:
        # Nothing to store.
        return
    path = os.path.join(outdir, data["name"]) + ".json"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--language",
        default="java",
        choices=["java", "kotlin"],
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


CONVERTERS = {
    "java": JavaAPIDocConverter(),
    "kotlin": KotlinAPIDocConverter()
}


def main():
    args = get_args()
    preprocess_args(args)
    converter = CONVERTERS.get(args.language)
    converter.process(args)


if __name__ == '__main__':
    main()
