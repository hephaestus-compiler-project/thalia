from abc import ABC, abstractmethod
from typing import NamedTuple, List

import networkx as nx

from src.ir import BUILTIN_FACTORIES, types as tp
from src.ir.builtins import BuiltinFactory


IN = 0
OUT = 1
WIDENING = 2


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

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(str(self.name))

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.name == other.name


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

    @abstractmethod
    def build(self, docs: dict) -> nx.DiGraph:
        self.graph = nx.DiGraph()
        return self.graph


class JavaAPIGraphBuilder(APIGraphBuilder):
    def __init__(self, target_language):
        super().__init__()
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self._class_name = None

    def parse_type(self, str_t: str) -> tp.Type:
        tf = self.bt_factory
        if str_t.endswith("[]"):
            str_t = str_t.split("[]")[0]
            return tf.get_array_type().new([self.parse_type(str_t)])
        elif str_t.endswith("..."):
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
        elif str_t == "java.lang.String":
            return tf.get_string_type()
        elif str_t == "java.lang.Object":
            return tf.get_any_type()
        elif str_t == "java.lang.BigDecimal":
            return tf.get_double_type()
        elif str_t == "void":
            return tf.get_void_type()
        else:
            return tp.SimpleClassifier(str_t)

    def build(self, docs: dict) -> nx.DiGraph:
        self.graph = nx.DiGraph()
        for api_doc in docs.values():
            if api_doc["type_parameters"]:
                # TODO: Handle parametric polymorphism.
                continue
            self.process_class(api_doc)
        return self.graph

    def process_fields(self, class_node, fields):
        for field_api in fields:
            if field_api["is_static"]:
                field_node = Field(self._class_name + "." + field_api["name"])
                self.graph.add_node(field_node)
            else:
                field_node = Field(field_api["name"])
                self.graph.add_node(field_node)
                self.graph.add_edge(class_node, field_node, label=IN)
            field_type = TypeNode(self.parse_type(field_api["type"]))
            self.graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["access_mod"] == "protected":
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
            self.graph.add_edge(method_node, ret_type, label=OUT)

    def process_class(self, class_api):
        self._class_name = class_api["name"]
        class_node = TypeNode(self.parse_type(self._class_name))
        self.graph.add_node(class_node)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])
        super_types = {
            self.parse_type(st)
            for st in class_api["implements"]
        }
        super_types.add(self.parse_type(class_api["inherits"]))
        for st in super_types:
            self.graph.add_edge(class_node, st, label=WIDENING)


def find_all_simple_paths(G, cutoff, max_paths=None):
    source_nodes = [
        node
        for node, indegree in G.in_degree(G.nodes())
        if indegree == 0
    ]

    if cutoff == 0:
        return [[node] for node in source_nodes]
    else:
        stop = False
        all_paths = []
        current_paths = [[node] for node in source_nodes]
        for j in range(min(cutoff, len(G))):
            next_paths = []
            for i, path in enumerate(current_paths):
                for neighbor in G.neighbors(path[-1]):
                    if neighbor not in path or isinstance(neighbor, TypeNode):
                        new_path = path[:] + [neighbor]
                        next_paths.append(new_path)
                        if len(new_path) == cutoff:
                            all_paths.append(new_path)
                        if max_paths and len(all_paths) == max_paths:
                            stop = True
                            break
                if stop:
                    break
            current_paths = next_paths
            if stop:
                break

        return all_paths
