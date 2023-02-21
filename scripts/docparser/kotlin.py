import re

from pathlib import Path

from docparser.base import APIDocConverter
from docparser.utils import file2html, dict2json


class KotlinAPIDocConverter(APIDocConverter):
    EXCLUDED_METHOD_NAME = "<no name provided>"
    PROTECTED = "protected"
    PUBLIC = "public"

    def process(self, args):
        toplevel_path = Path(args.input).joinpath("index.html")
        data = self.process_toplevel(file2html(toplevel_path))
        data["language"] = args.language
        dict2json(args.output, data)
        for path in Path(args.input).rglob('*/index.html'):
            apidoc_path = str(path)
            data = self.process_class(file2html(apidoc_path))
            data["language"] = args.language
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
            "type_parameters": [],
            "is_class": False,
        }
        return api

    def _replace_anchors_with_package_prefix(self, anchors):
        # This method replaces the text of all anchors (note that the text
        # corresponds to type names) with the fully quallified name of the
        # type. The package prefix is found in a attribute of each anchor
        # named "title".
        java_regex = re.compile(
            "https://docs.oracle.com/.*/api/(.*)/[^/]+.html")
        kotlin_regex = re.compile(
            "https://kotlinlang.org/api/latest/.*/stdlib/(.*)/-[^/]+/index.html"
        )
        for anchor in anchors:
            href = anchor.get("href")
            if href.startswith("https://docs.oracle.com"):
                regex = java_regex
            elif href.startswith("https://kotlinlang.org"):
                regex = kotlin_regex
            else:
                continue

            match = re.match(regex, href)
            package_prefix = match.group(1).replace("/", ".")
            segs = package_prefix.rsplit(".", 1)
            if segs[-1].startswith("-"):
                # Handle nested class
                package_prefix = segs[0]
            if not anchor.string.startswith(package_prefix):
                anchor.string.replace_with(package_prefix + "." + anchor.text)

    def _get_super_classes_interfaces(self, html_doc):
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        element = html_doc.select(".cover .platform-hinted .symbol")[0]
        # remove these elements
        rem_elems = element.find_all("span", {"class": "top-right-position"}) + \
            element.find_all("div", {"class": "copy-popup-wrapper"})
        for e in rem_elems:
            e.decompose()
        self._replace_anchors_with_package_prefix(element.select("a"))
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
        self._replace_anchors_with_package_prefix(element.select("a"))
        segs = element.text.split(":")
        cls_text = segs[0].rstrip()
        segs = cls_text.split("<")
        if len(segs) == 1:
            return []
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        text = segs[1][:-1].replace(", ", ",")
        return re.findall(regex, text)

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
            return self.ENUM
        return self.REGULAR_CLASS

    def extract_super_interfaces(self, html_doc):
        return self._get_super_classes_interfaces(html_doc)

    def process_class(self, html_doc):
        class_name = self.extract_class_name(html_doc)
        package_name = "kotlin." + self.extract_package_name(html_doc)
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
        class_obj = {
            'name': full_class_name,
            'type_parameters': type_parameters,
            'implements': super_interfaces,
            'inherits': super_class,
            "class_type": class_type,
            "methods": method_objs + constructor_objs,
            'fields': field_objs,
            "is_class": True,
        }
        return class_obj

    def extract_method_receiver(self, method_doc):
        regex = re.compile(
            r".*fun (<.*> )?(.*)\.[a-zA-Z0-9_]+\(.*\).*")
        match = re.match(regex, method_doc.text)
        if not match:
            return None
        return match.group(2)

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
            self._replace_anchors_with_package_prefix(param.select("a"))
            segs = param.text.strip(", ").split(": ", 1)
            assert len(segs) == 2
            types.append(segs[1])
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
        regex = re.compile(".*va[lr] (.+\\.)?([^ <>\\.]+): .*")
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
        return self.PROTECTED if match else self.PUBLIC

    def process_fields(self, fields):
        field_objs = []
        for field_doc in fields:
            self._replace_anchors_with_package_prefix(field_doc.select("a"))
            field_obj = {
                "name": self.extract_field_name(field_doc),
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
            self._replace_anchors_with_package_prefix(method_doc.select("a"))
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
