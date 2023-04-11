import os
import re
import urllib

from docparser.base import APIDocConverter
from docparser.utils import file2html, dict2json, top_level_split, decode


def normalize(func):
    def inner(*args):
        ret = func(*args)
        if isinstance(ret, (set, list, tuple)):
            return [decode(r.replace("  ", " ")) for r in ret]
        if isinstance(ret, str):
            return decode(ret.replace("  ", " "))
        return ret
    return inner


class JavaAPIDocConverter(APIDocConverter):
    EXCLUDED_FILES = [
        'package-summary.html',
        'package-tree.html',
        'package-use.html',
        'package-frame.html'
    ]
    PROTECTED = "protected"
    PUBLIC = "public"

    def __init__(self, args):
        super().__init__()
        self._current_api_cls = None
        self._cls_name = None
        self.jdk_docs = args.jdk_docs

    @normalize
    def extract_package_name(self, html_doc):
        if self.jdk_docs:
            return html_doc.find_all(class_="subTitle")[1].find_all(
                text=True)[2]
        else:
            try:
                return html_doc.select(".subTitle a")[0].text
            except IndexError:
                return html_doc.select(".subTitle")[0].text

    @normalize
    def extract_class_name(self, html_doc):
        if not self.jdk_docs:
            title = html_doc.find(class_="title")["title"]
            if "Annotation" in title:
                return None
            return title.rsplit(" ", 1)[-1]
        regex = re.compile("([@A-Za-z0-9\\.]+).*")
        type_name = html_doc.find(class_="typeNameLabel")
        if not type_name:
            return None
        text = decode(type_name.text)
        match = re.match(regex, text)
        if not match:
            raise Exception("Cannot extract class name: {!r}".format(text))
        return match.group(1)

    @normalize
    def extract_class_type_parameters(self, html_doc):
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        class_def = html_doc.find(class_="title")
        self._replace_anchors_with_package_prefix(class_def.select("a"))
        text = class_def.text.split("<", 1)
        if len(text) == 1:
            return []
        text = decode(text[1][:-1]).replace(" , ", ",")
        return re.findall(regex, text)

    @normalize
    def extract_super_class(self, html_doc):
        supercls_defs = html_doc.select(".description .blockList pre")[0]
        self._replace_anchors_with_package_prefix(supercls_defs.select("a"))
        text = supercls_defs.text.encode("ascii", "ignore").decode()
        text = text.replace("\n", " ").replace("  ", " ").replace(", ", ",")
        if self._cls_name + "<" in text:
            segs = text.split("> extends ")
            if len(segs) == 1:
                return []
            text = segs[-1].split(" implements ")[0]
        else:
            regex2 = re.compile(".*[^?] extends (.*)( implements .*)?")
            match = re.match(regex2, text)
            if not match:
                return []
            text = match.group(1).split(" implements ")[0]

        return top_level_split(text)

    def extract_class_type(self, html_doc):
        text = html_doc.select(".description pre")[0].text
        if 'interface' in text:
            return self.INTERFACE
        if 'abstract class' in text:
            return self.ABSTRACT_CLASS
        if 'enum' in text:
            return self.ENUM
        return self.REGULAR_CLASS

    def extract_class_access_modifier(self, html_doc):
        text = html_doc.select(".description pre")[0].text
        if "protected " in text:
            return "protected"
        else:
            return "public"

    @normalize
    def extract_super_interfaces(self, html_doc):
        text = html_doc.select(".description .blockList pre")[0].text.encode(
            "ascii", "ignore").decode()
        text = text.replace("\n", " ")
        segs = text.split(" implements ")
        if len(segs) == 1:
            return []
        text = segs[1].replace(", ", ",")
        return top_level_split(text)

    @normalize
    def extract_functional_interface(self, html_doc):
        text = decode(html_doc.select(".description .blockList pre")[0].text)
        return "@FunctionalInterface" in text

    def is_class_static(self, html_doc):
        text = decode(html_doc.select(".description .blockList pre")[0].text)
        return " static " in text

    @normalize
    def extract_parent_class(self, html_doc, class_name, package_name):
        parent = None
        segs = class_name.split(".")
        if len(segs) > 1:
            is_static = self.is_class_static(html_doc)
            if not is_static:
                parent = package_name + "." + segs[0]
        return parent

    def process(self, args):
        for base in os.listdir(args.input):
            if base in self.EXCLUDED_FILES:
                continue
            apidoc_path = os.path.join(args.input, base)
            if not apidoc_path.endswith(".html"):
                continue
            data = self.process_class(file2html(apidoc_path))
            if data:
                data["language"] = args.language
            dict2json(args.output, data)

    def process_class(self, html_doc):
        class_name = self.extract_class_name(html_doc)
        if not class_name:
            # TODO handle annotations
            return None

        package_name = self.extract_package_name(html_doc)
        full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                               cls=class_name)
        self._cls_name = class_name
        super_class = self.extract_super_class(html_doc)
        super_interfaces = self.extract_super_interfaces(html_doc)
        class_type = self.extract_class_type(html_doc)
        access_mod = self.extract_class_access_modifier(html_doc)
        is_func_interface = self.extract_functional_interface(html_doc)
        if class_type == self.ENUM:
            # TODO handle enums
            return None
        self._current_api_cls = html_doc
        methods = html_doc.find_all(class_="rowColor") + html_doc.find_all(
            class_="altColor")
        methods_ = []
        constructors = []
        for m in methods:
            if self.is_constructor(m):
                if class_type != self.ABSTRACT_CLASS:
                    constructors.append(m)
            else:
                methods_.append(m)
        fields = self._extract_fields(html_doc)
        method_objs = self.process_methods(methods_, False)
        constructor_objs = self.process_methods(constructors, True)
        field_objs = self.process_fields(fields)
        parent = self.extract_parent_class(html_doc, class_name, package_name)
        class_obj = {
          'name': full_class_name,
          'type_parameters': self.extract_class_type_parameters(html_doc),
          'implements': super_interfaces,
          'inherits': super_class,
          "class_type": class_type,
          'methods': method_objs + constructor_objs,
          'fields': field_objs,
          "functional_interface": is_func_interface,
          "parent": parent,
          "access_mod": access_mod,
        }
        return class_obj

    @normalize
    def extract_method_type_parameters(self, method_doc, is_constructor):
        if is_constructor:
            return []
        regex = re.compile(
            r"(static )?(default )?(<(.*)>)?[^<>,\?](.*)?")
        text = method_doc.find(class_="colFirst").text.encode(
            "ascii", "ignore").decode().replace("  ", " ")
        match = re.match(regex, text)
        if not match:
            raise Exception("Cannot match method's signature {!r}".format(
                text))
        type_parameters = match.group(4)
        if type_parameters:
            type_parameters = top_level_split(type_parameters)
        return type_parameters or []

    @normalize
    def extract_method_return_type(self, method_doc, is_constructor):
        if is_constructor:
            return None

        regex = re.compile(
            r"(static )?(default )?(protected )?(abstract )?(<.*>)?([^<>,\?](.*)?)")
        self._replace_anchors_with_package_prefix(
            method_doc.select(".colFirst a"))
        text = decode(method_doc.find(class_="colFirst").text).replace("  ",
                                                                       " ")
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
            if anchor.string.startswith("@"):
                # Ignore annotations
                if anchor.string not in ["@FunctionalInterface", "@interface"]:
                    anchor.string.replace_with("")
                continue
            title = anchor.get("title")
            if not title or "type parameter" in title:
                # It's either a primitive type of a type parameter. We ignore
                # them.
                continue
            package_prefix = title.split(" in ")[1]
            if not anchor.string.startswith(package_prefix):
                anchor.string.replace_with(package_prefix + "." + anchor.text)

    @normalize
    def extract_method_parameter_types(self, method_doc, is_constructor):
        regex = re.compile(r'(.+) [a-zA-Z_]+')
        if self.jdk_docs:
            key = ".colConstructorName code" if is_constructor else \
                ".colSecond code"
        else:
            key = (".colOne code"
                   if is_constructor else ".colSecond code")
        if not is_constructor and not self.jdk_docs:
            if method_doc.find(class_="colSecond") is None:
                key = ".colLast code"
        self._replace_anchors_with_package_prefix(
            method_doc.select(key + " a"))
        try:
            text = method_doc.select(key)[0].text.replace(
                "\n", " ").replace("\xa0", " ").replace("\u200b", "").split(
                    "(", 1)[1].rsplit(")")[0]
        except IndexError:
            # We probably encounter a field
            return None
        if not text:
            return []
        elements = top_level_split(text)
        param_types = [regex.search(elem).group(1) for elem in elements]
        return param_types

    def extract_method_access_mod(self, method_doc, is_con):
        column = method_doc.find(class_="colFirst")
        if column is None and is_con:
            # We have a public constructor
            return self.PUBLIC

        text = column.text.encode("ascii", "ignore").decode()
        return self.PROTECTED if self.PROTECTED in text else self.PUBLIC

    @normalize
    def extract_method_name(self, method_doc, is_constructor):
        try:
            if self.jdk_docs:
                key = ".colConstructorName a" if is_constructor else \
                    ".colSecond a"
            else:
                key = ".memberNameLink a"
            elements = method_doc.select(key)
            if not elements and not self.jdk_docs and is_constructor:
                key = ".colLast a"
                return method_doc.select(key)[0].text
            else:
                return elements[0].text
        except IndexError:
            # We are probably in a field
            return None

    def extract_isstatic(self, method_doc, is_constructor):
        if is_constructor:
            return False
        return 'static' in method_doc.find(class_="colFirst").text

    def extract_isdefault(self, method_doc, is_constructor):
        if is_constructor:
            return False
        return "default" in method_doc.find(class_="colFirst").text

    def extract_exceptions(self, method_doc):
        if not self.jdk_docs:
            return []
        href = method_doc.select(".memberNameLink a")[0]["href"]
        href = urllib.parse.unquote(href)
        # This is a ref to another class
        if href.endswith(".html"):
            return []
        method_summary = self._current_api_cls.find(
            id=href[1:]).nextSibling.nextSibling
        throws_summary = method_summary.find(class_="throwsLabel")
        if not throws_summary:
            return []
        exception_refs = []
        elem = throws_summary.next.next.next
        while elem and elem.name == "dd":
            exceptions_refs = elem.select("a")
            self._replace_anchors_with_package_prefix(exceptions_refs)
            exception_refs.extend([
                ref.text
                for ref in exceptions_refs
            ])
            elem = elem.nextSibling.nextSibling
        return exception_refs

    def is_constructor(self, method_doc):
        if self.jdk_docs:
            return method_doc.find(class_="colConstructorName") is not None
        base_name = self._cls_name.rsplit(".", 1)[-1]
        return self.extract_method_name(method_doc,
                                        False) == base_name

    @normalize
    def extract_field_name(self, field_doc):
        key = ".colSecond a"
        elements = field_doc.select(key)
        if not elements and not self.jdk_docs:
            key = ".colLast a"
            return field_doc.select(key)[0].text
        return elements[0].text

    @normalize
    def extract_field_type(self, field_doc):
        return self.extract_method_return_type(field_doc, False)

    def extract_field_access_mod(self, field_doc):
        return self.extract_method_access_mod(field_doc, False)

    def process_methods(self, methods, is_con):
        method_objs = []
        for method_doc in methods:
            exceptions = self.extract_exceptions(method_doc)
            method_name = self.extract_method_name(method_doc, is_con)
            isstatic = self.extract_isstatic(method_doc, is_con)
            ret_type = self.extract_method_return_type(method_doc, is_con)
            type_params = self.extract_method_type_parameters(method_doc,
                                                              is_con)
            param_types = self.extract_method_parameter_types(method_doc,
                                                              is_con)
            access_mod = self.extract_method_access_mod(method_doc, is_con)
            is_default = self.extract_isdefault(method_doc, is_con)

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
                "throws": exceptions,
                "is_default": is_default
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
