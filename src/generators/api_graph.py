from abc import ABC, abstractmethod
from typing import NamedTuple, Dict, List, Union

import networkx as nx


class TypeNode(NamedTuple):
    name: str

    def __str__(self):
        return "(" + self.name + ")"

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name))


class Field(NamedTuple):
    name: str

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(str(self.name))


class Method(NamedTuple):
    name: str
    parameters: List[TypeNode]

    def __str__(self):
        return "{}({})".format(self.name, ",".join(
            p.name for p in self.parameters))

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name) + str(self.parameters))


class Constructor(NamedTuple):
    name: str
    parameters: List[TypeNode]

    def __str__(self):
        return "{}({})".format(self.name, ",".join(
            p.name for p in self.parameters))

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name) + str(self.parameters))


class APIEdge(NamedTuple):
    target: Union[
        TypeNode,
        Field,
        Method,
        Constructor
    ]

    def __str__(self):
        return "-> {}".format(self.target)

    __repr__ = __str__


class APIGraphBuilder(ABC):
    def __init__(self):
        self.graph: nx.DiGraph = None

    @abstractmethod
    def build(self, docs: dict) -> nx.DiGraph:
        self.graph = nx.DiGraph()
        return self.graph


class JavaAPIGraphBuilder(APIGraphBuilder):
    def __init__(self):
        super().__init__()
        self._class_name = None

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
                self.graph.add_edge(class_node, field_node)
            field_type = TypeNode(field_api["type"])
            self.graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["type_parameters"]:
                # TODO: Handle parametric polymorphism.
                continue
            name = method_api["name"]
            is_constructor = method_api["is_constructor"]
            is_static = method_api["is_static"]
            parameters = [
                TypeNode(p)
                for p in method_api["parameters"]
            ]
            if is_constructor:
                method_node = Constructor(self._class_name + "." + name,
                                          parameters)
            elif is_static:
                method_node = Method(self._class_name + "." + name,
                                     parameters)
            else:
                method_node = Method(name, parameters)
            self.graph.add_node(method_node)
            if not (is_constructor or is_static):
                self.graph.add_edge(class_node, method_node)
            ret_type = (
                TypeNode(self._class_name)
                if is_constructor
                else TypeNode(method_api["return_type"])
            )
            self.graph.add_node(ret_type)
            self.graph.add_edge(method_node, ret_type)

    def process_class(self, class_api):
        self._class_name = class_api["name"]
        class_node = TypeNode(self._class_name)
        self.graph.add_node(class_node)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])


def find_all_simple_paths(G, cutoff):
    source_nodes = [
        node
        for node, indegree in G.in_degree(G.nodes())
        if indegree == 0
    ]

    if cutoff == 0:
        return [[node] for node in source_nodes]
    else:
        all_paths = []
        current_paths = [[node] for node in source_nodes]
        for _ in range(min(cutoff, len(G))):
            next_paths = []
            for path in current_paths:
                for neighbor in G.neighbors(path[-1]):
                    if neighbor not in path or isinstance(neighbor, TypeNode):
                        new_path = path[:] + [neighbor]
                        next_paths.append(new_path)
                        all_paths.append(new_path)
            current_paths = next_paths

        return all_paths
