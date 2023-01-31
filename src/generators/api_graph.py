from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import NamedTuple, List, Tuple
import re

import networkx as nx

from src.ir import BUILTIN_FACTORIES, types as tp, kotlin_types as kt
from src.ir.builtins import BuiltinFactory


IN = 0
OUT = 1
WIDENING = 2
PROTECTED = "protected"


class TypeNode(NamedTuple):
    t: tp.Type

    def __str__(self):
        return "(" + str(self.t) + ")"

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.t))

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.t == other.t


class Field(NamedTuple):
    name: str
    cls: str

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(str(self.name) + str(self.cls))

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.name == other.name and
                self.cls == other.cls)


class Method(NamedTuple):
    name: str
    cls: str
    parameters: List[TypeNode]

    def __str__(self):
        return "{}({})".format(self.name, ",".join(
            str(p) for p in self.parameters))

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name) + str(self.cls) + str(self.parameters))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.name == other.name and
            self.cls == other.cls and
            self.parameters == other.parameters
        )


class Constructor(NamedTuple):
    name: str
    parameters: List[TypeNode]

    def __str__(self):
        return "{}({})".format(self.name, ",".join(
            str(p) for p in self.parameters))

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name) + str(self.parameters))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.name == other.name and
            self.parameters == other.parameters
        )


class APIGraphBuilder(ABC):
    def __init__(self):
        self.graph: nx.DiGraph = None
        self.subtyping_graph: nx.DiGraph = None

    def build(self, docs: dict) -> Tuple[nx.DiGraph, nx.DiGraph]:
        self.graph = nx.DiGraph()
        self.subtyping_graph = nx.DiGraph()
        for api_doc in docs.values():
            self.process_class(api_doc)
        return self.graph, self.subtyping_graph

    @abstractmethod
    def process_class(self, class_api: dict):
        pass

    @abstractmethod
    def process_methods(self, methods: List[dict]):
        pass

    @abstractmethod
    def process_fields(self, fields: List[dict]):
        pass

    @abstractmethod
    def parse_type(self, str_t: str,
                   type_variables: List[str] = None) -> tp.Type:
        pass


class JavaAPIGraphBuilder(APIGraphBuilder):
    def __init__(self, target_language):
        super().__init__()
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self._class_name = None
        self._class_type_var_map: dict = {}
        self._type_var_map: dict = {}

    def parse_wildcard(self, str_t) -> tp.WildCardType:
        if str_t == "?":
            return tp.WildCardType()
        if "extends" in str_t:
            return tp.WildCardType(
                self.parse_type(str_t.split(" extends ", 1)[1]),
                variance=tp.Covariant)
        else:
            return tp.WildCardType(
                self.parse_type(str_t.split(" super ", 1)[1]),
                variance=tp.Contravariant)

    def parse_type_parameter(self, str_t: str) -> tp.TypeParameter:
        segs = str_t.split(" extends ")
        if len(segs) == 1:
            return tp.TypeParameter(self._type_var_map.get(str_t, str_t))
        bound = self.parse_type(segs[1])
        return tp.TypeParameter(
            self._type_var_map.get(segs[0], segs[0]), bound=bound)

    def parse_reg_type(self, str_t: str) -> tp.Type:
        if str_t.startswith("?"):
            return self.parse_wildcard(str_t)
        segs = str_t.split(".")
        is_type_var = (
            len(segs) == 1 or
            (
                " extends " in str_t and
                "." not in str_t.split(" extends ")[0]
             )
        )
        if is_type_var:
            return self.parse_type_parameter(str_t)
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        segs = str_t.split("<", 1)
        if len(segs) == 1:
            return tp.SimpleClassifier(str_t)
        base, type_args_str = segs[0], segs[1][:-1]
        type_args = re.findall(regex, type_args_str)
        new_type_args = []
        for type_arg in type_args:
            new_type_args.append(self.parse_type(type_arg))
        type_vars = [
            tp.TypeParameter(base + ".T" + str(i + 1))
            for i in range(len(new_type_args))
        ]
        type_vars = self._class_type_var_map.get(base, type_vars)
        return tp.TypeConstructor(base, type_vars).new(new_type_args)

    def parse_type(self, str_t: str,
                   type_variables: List[str] = None) -> tp.Type:
        tf = self.bt_factory
        if str_t.endswith("[]"):
            str_t = str_t.split("[]")[0]
            return tf.get_array_type().new([self.parse_type(str_t)])
        elif str_t.endswith("..."):
            # TODO consider this as a vararg rather than a single type.
            return self.parse_type(str_t.split("...")[0])
        elif str_t in ["char", "java.lang.Character"]:
            primitive = str_t == "char"
            return tf.get_char_type(primitive)
        elif str_t in ["byte", "java.lang.Byte"]:
            primitive = str_t == "byte"
            return tf.get_byte_type(primitive)
        elif str_t in ["short", "java.lang.Short"]:
            primitive = str_t == "short"
            return tf.get_short_type(primitive=primitive)
        elif str_t in ["int", "java.lang.Integer"]:
            primitive = str_t == "int"
            return tf.get_integer_type(primitive=primitive)
        elif str_t in ["long", "java.lang.Long"]:
            primitive = str_t == "long"
            return tf.get_long_type(primitive=primitive)
        elif str_t in ["float", "java.lang.Float"]:
            primitive = str_t == "float"
            return tf.get_float_type(primitive=primitive)
        elif str_t in ["double", "java.lang.Double"]:
            primitive = str_t == "double"
            return tf.get_double_type(primitive=primitive)
        elif str_t in ["boolean", "java.lang.Boolean"]:
            primitive = str_t == "boolean"
            return tf.get_boolean_type(primitive=primitive)
        elif str_t == "java.lang.String":
            return tf.get_string_type()
        elif str_t == "java.lang.Object":
            return tf.get_any_type()
        elif str_t == "java.lang.BigDecimal":
            return tf.get_double_type()
        elif str_t == "void":
            return tf.get_void_type()
        else:
            return self.parse_reg_type(str_t)

    def process_fields(self, class_node, fields):
        for field_api in fields:
            if field_api["access_mod"] == PROTECTED:
                continue
            if field_api["is_static"]:
                field_node = Field(self._class_name + "." + field_api["name"],
                                   self._class_name)
                self.graph.add_node(field_node)
            else:
                field_node = Field(field_api["name"], self._class_name)
                self.graph.add_node(field_node)
                self.graph.add_edge(class_node, field_node, label=IN)
            field_type = TypeNode(self.parse_type(field_api["type"]))
            self.graph.add_node(field_type)
            self.subtyping_graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue
            if method_api["type_parameters"]:
                # TODO: Handle parametric polymorphism.
                continue
            name = method_api["name"]
            is_constructor = method_api["is_constructor"]
            is_static = method_api["is_static"]
            parameters = [
                TypeNode(self.parse_type(p))
                for p in method_api["parameters"]
            ]
            for param in parameters:
                self.graph.add_node(param)
                self.subtyping_graph.add_node(param)
            if is_constructor:
                method_node = Constructor(self._class_name,
                                          parameters)
            elif is_static:
                method_node = Method(self._class_name + "." + name,
                                     self._class_name,
                                     parameters)
            else:
                method_node = Method(name, self._class_name, parameters)
            self.graph.add_node(method_node)
            if not (is_constructor or is_static):
                self.graph.add_edge(class_node, method_node, label=IN)
            ret_type = (
                TypeNode(self.parse_type(self._class_name))
                if is_constructor
                else TypeNode(self.parse_type(method_api["return_type"]))
            )
            self.graph.add_node(ret_type)
            self.subtyping_graph.add_node(ret_type)
            self.graph.add_edge(method_node, ret_type, label=OUT)

    def process_class(self, class_api):
        self._class_name = class_api["name"]
        class_node = TypeNode(self.parse_type(self._class_name))
        self.graph.add_node(class_node)
        self.subtyping_graph.add_node(class_node)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])
        super_types = {
            TypeNode(self.parse_type(st))
            for st in class_api["implements"] + class_api["inherits"]
        }
        if not super_types:
            super_types.add(TypeNode(self.parse_type("java.lang.Object")))
        for st in super_types:
            self.subtyping_graph.add_node(st)
            # Do not connect a node with itself.
            if class_node != st:
                self.subtyping_graph.add_edge(st, class_node, label=WIDENING)


class KotlinAPIGraphBuilder(APIGraphBuilder):
    def __init__(self, target_language="kotlin"):
        super().__init__()
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self._class_name = None

    def parse_type(self, str_t: str,
                   type_variables: List[str] = None) -> tp.Type:
        tf = self.bt_factory
        if str_t.endswith("Array<"):
            str_t = str_t.split("Array<")[1][:-1]
            return tf.get_array_type().new([self.parse_type(str_t)])
        elif str_t == "CharArray":
            return kt.CharArray
        elif str_t == "ByteArray":
            return kt.ByteArray
        elif str_t == "ShortArray":
            return kt.ShortArray
        elif str_t == "IntArray":
            return kt.IntegerArray
        elif str_t == "LongArray":
            return kt.LongArray
        elif str_t == "FloatArray":
            return kt.FloatArray
        elif str_t == "DoubleArray":
            return kt.DoubleArray
        elif str_t.startswith("vararg "):
            return self.parse_type(str_t.split("vararg ")[1])
        elif str_t == "Char":
            return tf.get_char_type()
        elif str_t == "Byte":
            return tf.get_byte_type()
        elif str_t == "Short":
            return tf.get_short_type()
        elif str_t == "Int":
            return tf.get_integer_type()
        elif str_t == "Long":
            return tf.get_long_type()
        elif str_t == "Float":
            return tf.get_float_type()
        elif str_t == "Double":
            return tf.get_double_type()
        elif str_t == "String":
            return tf.get_string_type()
        elif str_t == "Any":
            return tf.get_any_type()
        elif str_t == "java.lang.BigDecimal":
            return tf.get_double_type()
        elif str_t == "Unit":
            return tf.get_void_type()
        else:
            return tp.SimpleClassifier(str_t)

    def process_fields(self, class_node, fields):
        for field_api in fields:
            if field_api["access_mod"] == PROTECTED:
                continue
            if class_node:
                receiver = class_node
            receiver = (
                TypeNode(self.parse_type(field_api["receiver"]))
                if field_api["receiver"]
                else class_node)
            if receiver:
                self._class_name = str(receiver.t)
                self.graph.add_node(receiver)
                self.subtyping_graph.add_node(receiver)
            field_node = Field(field_api["name"], self._class_name)
            self.graph.add_node(field_node)
            if receiver:
                self.graph.add_edge(receiver, field_node, label=IN)
            field_type = TypeNode(self.parse_type(field_api["type"]))
            self.graph.add_node(field_type)
            self.subtyping_graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue
            if method_api["type_parameters"]:
                # TODO: Handle parametric polymorphism.
                continue
            name = method_api["name"]
            is_constructor = method_api["is_constructor"]
            parameters = [
                TypeNode(self.parse_type(p))
                for p in method_api["parameters"]
            ]
            for param in parameters:
                self.graph.add_node(param)
                self.subtyping_graph.add_node(param)
            if class_node:
                receiver = class_node
            receiver = (
                TypeNode(self.parse_type(method_api["receiver"]))
                if method_api["receiver"]
                else class_node)
            if receiver:
                self._class_name = str(receiver.t)
                self.graph.add_node(receiver)
                self.subtyping_graph.add_node(receiver)
            if is_constructor:
                method_node = Constructor(self._class_name,
                                          parameters)
            else:
                method_node = Method(name, self._class_name, parameters)
            self.graph.add_node(method_node)
            if not (is_constructor or receiver is None):
                self.graph.add_edge(receiver, method_node, label=IN)
            ret_type = (
                TypeNode(self.parse_type(self._class_name))
                if is_constructor
                else TypeNode(self.parse_type(method_api["return_type"]))
            )
            self.graph.add_node(ret_type)
            self.subtyping_graph.add_node(ret_type)
            self.graph.add_edge(method_node, ret_type, label=OUT)

    def _process_class(self, class_api: dict):
        self._class_name = class_api["name"].rsplit(".", 1)[-1]
        class_node = TypeNode(self.parse_type(self._class_name))
        self.graph.add_node(class_node)
        self.subtyping_graph.add_node(class_node)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])
        super_types = {
            TypeNode(self.parse_type(st))
            for st in class_api["implements"] + class_api["inherits"]
        }
        if not super_types:
            super_types.add(TypeNode(self.parse_type("Any")))
        for st in super_types:
            self.subtyping_graph.add_node(st)
            # Do not connect a node with itself.
            if class_node != st:
                self.subtyping_graph.add_edge(st, class_node, label=WIDENING)

    def process_class(self, class_api):
        if class_api["is_class"]:
            self._process_class(class_api)
        else:
            self._class_name = None
            self.process_methods(None, class_api["methods"])
            self.process_fields(None, class_api["fields"])
