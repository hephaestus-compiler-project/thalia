import os
import re

from docparser.base import APIDocConverter
from docparser.utils import file2html, dict2json


class ScalaAPIDocConverter(APIDocConverter):
    EXCLUDED_FILES = [
        'index.html',
        'languageFeature$$experimental$.html'
    ]
    PROTECTED = "protected"
    PUBLIC = "public"
    OBJECT = 5

    def __init__(self):
        super().__init__()
        self.class_name = None
        self.is_object = False

    def process(self, args):
        docs = {}
        objects_methods = {}
        objects_fields = {}
        for base in os.listdir(args.input):
            if base in self.EXCLUDED_FILES:
                continue
            apidoc_path = os.path.join(args.input, base)
            if not apidoc_path.endswith(".html"):
                continue
            data = self.process_class(file2html(apidoc_path))
            if data:
                data["language"] = args.language
            value = docs.get(data["name"])
            if value:
                value["methods"].extend(data["methods"])
                value["fields"].extend(data["fields"])
            else:
                if data["class_type"] != self.OBJECT:
                    data["methods"].extend(objects_methods.get(data["name"],
                                                               []))
                    data["fields"].extend(objects_fields.get(data["name"],
                                                             []))
                    docs[data["name"]] = data
                else:
                    objects_methods[data["name"]] = data["methods"]
                    objects_fields[data["name"]] = data["fields"]
        for data in docs.values():
            dict2json(args.output, data)

    def _replace_anchors_with_package_prefix(self, anchors):
        # This method replaces the text of all anchors (note that the text
        # corresponds to type names) with the fully quallified name of the
        # type. The package prefix is found in a attribute of each anchor
        # named "title".
        for anchor in anchors:
            fname = anchor.get("id")
            cls_name = fname.rsplit(".", 1)[1]
            if fname != anchor.string:
                anchor.string.replace_with(anchor.string.replace(cls_name,
                                                                 fname))

    def _get_super_classes_interfaces(self, html_doc):
        res = html_doc.select("#signature .result")
        if not res:
            return []
        text = res[0].text
        return text.replace(" extends ", "").replace(" with ",
                                                     "!!").split("!!")

    def extract_package_name(self, html_doc):
        return html_doc.find(id="owner").text

    def extract_class_name(self, html_doc):
        return html_doc.select("#definition h1")[0].text.encode(
            "ascii", "ignore").decode()

    def extract_class_type_parameters(self, html_doc):
        tparams = html_doc.select("#signature .tparams")
        if not tparams:
            return []
        return [
            elem.text
            for elem in tparams[0].find_all("span", recursive=False)
        ]

    def extract_super_class(self, html_doc):
        return self._get_super_classes_interfaces(html_doc)

    def extract_class_type(self, html_doc):
        text = html_doc.select("#signature .modifier_kind")[0].text
        text = re.sub(" +", " ", text)
        if 'trait' in text:
            return self.INTERFACE
        if 'abstract class' in text:
            return self.ABSTRACT_CLASS
        if 'enum' in text:
            return self.ENUM
        if 'object' in text:
            return self.OBJECT
        return self.REGULAR_CLASS

    def extract_super_interfaces(self, html_doc):
        return self._get_super_classes_interfaces(html_doc)

    def process_class(self, html_doc):
        class_name = self.extract_class_name(html_doc)
        self.class_name = class_name
        package_name = self.extract_package_name(html_doc)
        full_class_name = "{pkg}.{cls}".format(pkg=package_name,
                                               cls=class_name)
        self._replace_anchors_with_package_prefix(
            html_doc.select("#signature .result a"))
        self._replace_anchors_with_package_prefix(
            html_doc.select("#signature .tparams a"))
        super_class = self.extract_super_class(html_doc)
        super_interfaces = self.extract_super_interfaces(html_doc)
        type_parameters = self.extract_class_type_parameters(html_doc)
        class_type = self.extract_class_type(html_doc)
        self.is_object = class_type == self.OBJECT
        methods = html_doc.select("#allMembers .values.members li")
        constructors = html_doc.select("#constructors li")
        fields = methods
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

    def extract_method_type_parameters(self, method_doc, is_constructor):
        if is_constructor:
            return []
        tparams = method_doc.select(".symbol .tparams")
        if not tparams:
            return []
        return [
            elem.text
            for elem in tparams[0].find_all("span", recursive=False)
        ]

    def extract_method_return_type(self, method_doc, is_constructor):
        if is_constructor:
            return None
        return method_doc.select(".symbol .result")[0].text.split(
            ": ", 1)[1]

    def extract_method_parameter_types(self, method_doc, is_constructor):
        types = []
        for param in method_doc.select(".symbol .params"):
            param_specs = param.find_all("span", recursive=False)
            types.extend([
                param_spec.text.split(": ", 1)[1]
                for param_spec in param_specs
                if "implicit" not in param_spec.get("class", [])
            ])
        return types

    def extract_method_access_mod(self, method_doc):
        return self.PUBLIC

    def extract_method_name(self, method_doc):
        elem = method_doc.select(".symbol")[0]
        name = elem.find(class_="name")
        if name:
            return name.text
        return elem.find(class_="implicit").text

    extract_field_name = extract_method_name

    def extract_field_type(self, field_doc):
        return self.extract_method_return_type(field_doc, False)

    def extract_field_type_parameters(self, field_doc):
        return self.extract_method_type_parameters(field_doc, False)

    def is_field_final(self, field_doc):
        return "final" in field_doc.find(class_="modifier") or \
            "val" in field_doc.find(class_="kind")

    def is_field_override(self, field_doc):
        return "override" in field_doc.find(class_="modifier")

    def extract_field_access_mod(self, field_doc):
        return self.PUBLIC

    def process_fields(self, fields):
        field_objs = []
        for field_doc in fields:
            if not field_doc.select(".symbol .result"):
                # Probably a nested class.
                continue
            if field_doc.find("span", {"class": "kind"}).text not in [
                    "def", "val", "var"]:
                continue
            if field_doc.find(class_="params") is not None:
                # This is a method
                continue
            if field_doc.select(".symbol .tparams"):
                # TODO handle field parameters
                continue
            if not self._should_add_member(field_doc):
                continue
            self._replace_anchors_with_package_prefix(field_doc.select(
                ".symbol a"))
            field_obj = {
                "name": self.extract_field_name(field_doc),
                "type": self.extract_field_type(field_doc),
                "is_final": self.is_field_final(field_doc),
                "is_override": self.is_field_override(field_doc),
                "receiver": None,
                "type_parameters": self.extract_field_type_parameters(
                    field_doc),
                "access_mod": self.extract_field_access_mod(field_doc),
                "is_static": self.is_object,
            }
            field_objs.append(field_obj)
        return field_objs

    def _should_add_member(self, method_doc):
        element = method_doc.select(".fullcomment .attributes.block")
        if not element:
            return True
        is_deprecated = bool(element[0].find("dt", string="Deprecated"))
        if is_deprecated:
            return False
        is_implicit = bool(element[0].find("dt", string="Implicit"))
        is_shadowed = bool(element[0].find("dt", string="Shadowing"))
        if is_shadowed or is_implicit:
            return False
        dt = element[0].find("dt", string="Definition Classes")
        if not dt:
            return True
        text = dt.nextSibling.text
        return any(seg == self.class_name for seg in text.split(" \u2192 "))

    def process_methods(self, methods, is_constructor):
        method_objs = []
        for method_doc in methods:
            if not is_constructor and not method_doc.select(".symbol .result"):
                # Problably this an nested class / object.
                continue

            if method_doc.find(class_="params") is None:
                # Probably this is a field.
                continue

            if not self._should_add_member(method_doc):
                continue

            self._replace_anchors_with_package_prefix(method_doc.select(
                ".symbol a"))
            method_name = self.extract_method_name(method_doc)
            ret_type = self.extract_method_return_type(method_doc,
                                                       is_constructor)
            type_params = self.extract_method_type_parameters(
                method_doc, is_constructor)
            param_types = self.extract_method_parameter_types(
                method_doc, is_constructor)
            access_mod = self.extract_method_access_mod(method_doc)
            method_obj = {
                "name": method_name,
                "parameters": param_types,
                "type_parameters": type_params,
                "return_type": ret_type,
                "receiver": None,
                "is_static": self.is_object,
                "is_constructor": is_constructor,
                "access_mod": access_mod
            }
            method_objs.append(method_obj)
        return method_objs
