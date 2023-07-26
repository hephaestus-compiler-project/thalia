import os
import re

from pathlib import Path

from docparser.base import APIDocConverter
from docparser.utils import file2html, dict2json, top_level_split


def map_type(func):
    def inner_func(*args):
        def _map_type(str_t):
            if isinstance(str_t, (list, tuple, set)):
                return [_map_type(t) for t in str_t]

            # Now replace literal types to standard types, e.g.,
            # Char("\") => Char.
            if str_t.startswith("Char("):
                return "Char"
            elif str_t.startswith("Byte("):
                return "Byte"
            elif str_t.startswith("Short("):
                return "Short"
            elif str_t.startswith("Int("):
                return "Int"
            elif str_t.startswith("Long("):
                return "Long"
            elif str_t.startswith("Float("):
                return "Float"
            elif str_t.startswith("Double("):
                return "Double"
            elif str_t.startswith("Boolean("):
                return "Boolean"
            # Now handle named arguments (e.g., val x: String = "fda")
            return str_t.split(" = ", 1)[0]

        res = func(*args)
        if res is None:
            return None
        return _map_type(res)

    return inner_func


class KotlinAPIDocConverter(APIDocConverter):
    EXCLUDED_METHOD_NAME = "<no name provided>"
    PROTECTED = "protected"
    PUBLIC = "public"

    def __init__(self, args):
        super().__init__()
        self.class_name = None

    def process(self, args):
        toplevel_path = Path(args.input).joinpath("index.html")
        self.api_path = os.path.dirname(toplevel_path)
        data = self.process_toplevel(file2html(toplevel_path))
        data["language"] = args.language
        dict2json(args.output, data)
        for path in Path(args.input).rglob('*/index.html'):
            apidoc_path = str(path)
            self.api_path = os.path.dirname(path)
            data = self.process_class(file2html(apidoc_path))
            if data is None:
                continue
            data["language"] = args.language
            dict2json(args.output, data)

    def process_toplevel(self, html_doc):
        self.class_name = None
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
            "type_parameters": [],
            "is_class": False,
        }
        return api

    def _replace_anchors_with_package_prefix(self, anchors,
                                             excluded_strs=[]):
        # This method replaces the text of all anchors (note that the text
        # corresponds to type names) with the fully quallified name of the
        # type. The package prefix is found in a attribute of each anchor
        # named "title".
        java_regex = re.compile(
            "https://docs.oracle.com/.*/api/(.*)/[^/]+.html")
        kotlin_regex = re.compile(
            ".*/(docs/kotlin|stdlib|kotlin-stdlib|kotlin-stdlib-common)/(.+)/-[^/]+/index.html$"
        )
        for anchor in anchors:
            href = anchor.get("href")
            if anchor.string in excluded_strs:
                continue
            if not href.startswith("https") and (href.startswith("-")
                                                 or href.startswith(".")
                                                 or anchor.string.startswith(
                                                     self.class_name or "")):
                href = os.path.realpath(os.path.join(self.api_path, href))
            if href.startswith("https://docs.oracle.com"):
                regex = java_regex
            elif href.startswith("https://kotlinlang.org") or href.startswith(
                    "/"):
                regex = kotlin_regex
            else:
                continue

            match = re.match(regex, href)
            if not match:
                continue
            if href.startswith("https://docs.oracle.com"):
                group = match.group(1)
            else:
                group = match.group(2)
            package_prefix = group.replace("/", ".")
            segs = package_prefix.rsplit(".", 1)
            if segs[-1].startswith("-"):
                # Handle nested class
                package_prefix = segs[0]
            if not anchor.string.startswith(package_prefix):
                anchor.string.replace_with(package_prefix + "." + anchor.text)

    def _get_super_classes_interfaces(self, html_doc):
        element = html_doc.select(".cover .platform-hinted .symbol")[0]
        # remove these elements
        rem_elems = element.find_all("span", {"class": "top-right-position"}) + \
            element.find_all("div", {"class": "copy-popup-wrapper"})
        for e in rem_elems:
            e.decompose()
        self._replace_anchors_with_package_prefix(element.select("a"))
        text = re.sub(r"\(.+\)", "", element.text).replace(", ", ",")
        regex = re.compile(
            r"(object|class|interface) [a-zA-Z0-9.]+\." + self.class_name + "<")
        segs = regex.split(text, 1)
        if len(segs) > 2:
            segs = text.split("> : ", 1)
            if len(segs) == 1:
                return []
            text = segs[-1].strip()
        else:
            if " : " not in text:
                return []
            text = text.split(" : ")[-1].strip()
        return top_level_split(text)

    def extract_package_name(self, html_doc, top_level=False):
        packages = html_doc.select(".breadcrumbs a")[1:]
        if not top_level:
            packages = packages[:-1]
        return ".".join([p.text for p in packages])

    def extract_class_name(self, html_doc):
        return html_doc.select(".cover .cover")[0].text

    @map_type
    def extract_class_type_parameters(self, html_doc):
        element = html_doc.select(".cover .platform-hinted .symbol")[0]
        # remove these elements
        rem_elems = element.find_all("span", {"class": "top-right-position"}) + \
            element.find_all("div", {"class": "copy-popup-wrapper"})
        for e in rem_elems:
            e.decompose()
        self._replace_anchors_with_package_prefix(element.select("a"))
        regex = re.compile(
            r"(object|class|interface) [a-zA-Z0-9.]+\." + self.class_name + "<")
        segs = regex.split(element.text, 1)
        if len(segs) == 1:
            return []
        text = "<" + segs[2]
        balance = 1
        type_param_str = ""
        i = 1
        while balance >= 1:
            c = text[i]
            if c == "<":
                balance += 1
            if c == ">":
                balance -= 1
            if balance:
                type_param_str += c
            i += 1
        text = type_param_str.replace(", ", ",")
        return top_level_split(text)

    def extract_super_class(self, html_doc):
        # In general, we cannot distinguish between interfaces and classes.
        classes = self._get_super_classes_interfaces(html_doc)
        return classes

    def extract_class_type(self, html_doc):
        text = html_doc.select(".cover .platform-hinted .symbol")[0].text
        if 'interface' in text:
            return self.INTERFACE
        if 'abstract class' in text:
            return self.ABSTRACT_CLASS
        if 'enum' in text:
            return self.INTERFACE
        return self.REGULAR_CLASS

    def extract_super_interfaces(self, html_doc):
        return self._get_super_classes_interfaces(html_doc)

    def is_class_inner(self, html_doc):
        return "inner " in html_doc.select(
            ".cover .platform-hinted .symbol")[0].text

    def extract_parent_class(self, html_doc, class_name, package_name):
        parent = None
        is_inner = self.is_class_inner(html_doc)
        if is_inner:
            parent = package_name
        return parent

    def process_class(self, html_doc):
        text = html_doc.select(".cover .platform-hinted .symbol")[0].text
        if "annotation class" in text:
            return None
        class_name = self.extract_class_name(html_doc)
        self.class_name = class_name
        package_name = self.extract_package_name(html_doc)
        full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                               cls=class_name)
        type_parameters = self.extract_class_type_parameters(html_doc)
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
        if class_type != self.ABSTRACT_CLASS:
            constructor_objs = self.process_methods(constructors, True)
        else:
            constructor_objs = []
        field_objs = self.process_fields(fields)
        parent = self.extract_parent_class(html_doc, class_name, package_name)
        class_obj = {
            'name': full_class_name,
            'type_parameters': type_parameters,
            'implements': super_interfaces,
            'inherits': super_class,
            "class_type": class_type,
            "methods": method_objs + constructor_objs,
            'fields': field_objs,
            "is_class": True,
            "parent": parent,
        }
        return class_obj

    @map_type
    def extract_method_receiver(self, method_doc, name):
        regex = re.compile(
            r".*fun (<.*> )?(.*)\." + name + r"\(.*\).*")
        match = re.match(regex, method_doc.text)
        if not match:
            return None
        return match.group(2)

    @map_type
    def extract_method_type_parameters(self, method_doc, is_constructor):
        if is_constructor:
            return []
        regex = re.compile(
            r".*fun <(.*)> (.*\.)?[a-zA-Z0-9_]+\(.*\).*")
        match = re.match(regex, method_doc.text)
        if not match:
            return []
        type_parameters = match.group(1).replace(", ", ",")
        if type_parameters:
            regex = re.compile(r"(?:[^,<]|<[^>]*>)+")
            type_parameters = re.findall(regex, type_parameters)
        return type_parameters

    @map_type
    def extract_method_return_type(self, method_doc, is_constructor):
        if is_constructor:
            return None
        elem = method_doc.find("span", {"class": "top-right-position"})
        elem.decompose()
        segs = method_doc.text.split("): ")
        if len(segs) == 1:
            return "Unit"
        return segs[1]

    @map_type
    def extract_method_parameter_types(self, method_doc, is_constructor):
        types = []
        for param in method_doc.select(".parameter"):
            segs = param.text.strip(", ").split(": ", 1)
            assert len(segs) == 2
            types.append(segs[1].replace('@kotlin.UnsafeVariance\xa0', ''))
        return types

    def extract_method_access_mod(self, method_doc):
        text = method_doc.text
        return self.PROTECTED if "protected " in text else self.PUBLIC

    def extract_method_name(self, method_doc, is_constructor):
        try:
            return method_doc.find(class_="function").text
        except IndexError:
            # We are probably in a field
            return None

    def extract_field_name(self, field_doc):
        field_doc.find("span", {"class": "top-right-position"}).decompose()
        regex = re.compile(r".*va[lr] (.+\.)?([^ <>\.]+): .*")
        match = re.match(regex, field_doc.text)
        assert match is not None
        return match.group(2)

    @map_type
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

    @map_type
    def extract_field_type_parameters(self, field_doc):
        regex = re.compile(".*va[lr] <(.+)> .+: .*")
        match = re.match(regex, field_doc.text)
        if not match:
            return []
        type_parameters = match.group(1).replace(", ", ",")
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        return re.findall(regex, type_parameters)

    @map_type
    def extract_field_receiver(self, field_doc):
        regex = re.compile(r".*va[lr] (<.+> )?(.+)\.[a-zA-Z0-9_]+: .*")
        match = re.match(regex, field_doc.text)
        if not match:
            return None
        return match.group(2)

    def extract_field_access_mod(self, field_doc):
        regex = re.compile("protected va[lr] .*")
        match = re.match(regex, field_doc.text)
        return self.PROTECTED if match else self.PUBLIC

    def process_fields(self, fields):
        field_objs = []
        for field_doc in fields:
            field_name = self.extract_field_name(field_doc)
            self._replace_anchors_with_package_prefix(field_doc.select("a"))
            field_obj = {
                "name": field_name,
                "type": self.extract_field_type(field_doc),
                "is_final": self.is_field_final(field_doc),
                "is_override": self.is_field_override(field_doc),
                "receiver": self.extract_field_receiver(field_doc),
                "type_parameters": self.extract_field_type_parameters(
                    field_doc),
                "access_mod": self.extract_field_access_mod(field_doc),
                "is_static": False
            }
            field_objs.append(field_obj)
        return field_objs

    def process_methods(self, methods, is_constructor):
        method_objs = []
        for method_doc in methods:
            method_name = self.extract_method_name(method_doc, is_constructor)
            self._replace_anchors_with_package_prefix(method_doc.select("a"))
            if method_name == self.EXCLUDED_METHOD_NAME:
                continue
            ret_type = self.extract_method_return_type(method_doc,
                                                       is_constructor)
            type_params = self.extract_method_type_parameters(
                method_doc, is_constructor)
            param_types = self.extract_method_parameter_types(
                method_doc, is_constructor)
            if param_types is None:
                continue
            access_mod = self.extract_method_access_mod(method_doc)
            receiver = self.extract_method_receiver(method_doc, method_name)
            method_obj = {
                "name": method_name,
                "parameters": param_types,
                "type_parameters": type_params,
                "return_type": ret_type,
                "receiver": receiver,
                "is_static": False,
                "is_constructor": is_constructor,
                "access_mod": access_mod
            }
            method_objs.append(method_obj)
        return method_objs
