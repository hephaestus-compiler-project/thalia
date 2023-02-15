from abc import ABC, abstractmethod
from collections import OrderedDict
from copy import deepcopy
import re
from typing import List, Dict


import networkx as nx

from src.ir import BUILTIN_FACTORIES, types as tp, kotlin_types as kt
from src.ir.builtins import BuiltinFactory
from src.translators.kotlin import KotlinTranslator
from src.generators.api.api_graph import (APIGraph, IN, OUT, Method,
                                          Constructor, Field)
from src.generators.api.type_parsers import (TypeParser, KotlinTypeParser,
                                             JavaTypeParser)

PROTECTED = "protected"


class APIGraphBuilder(ABC):
    def __init__(self):
        self.graph: nx.DiGraph = None
        self.subtyping_graph: nx.DiGraph = None
        self.functional_types: Dict[tp.Type, tp.ParameterizedType] = {}
        self.bt_factory: BuiltinFactory = None

    def build(self, docs: dict) -> APIGraph:
        self.graph = nx.DiGraph()
        self.subtyping_graph = nx.DiGraph()
        for api_doc in docs.values():
            self.process_class(api_doc)
        return APIGraph(self.graph, self.subtyping_graph,
                        self.functional_types, self.bt_factory)

    @abstractmethod
    def get_type_parser(self) -> TypeParser:
        pass

    @abstractmethod
    def process_class(self, class_api: dict):
        pass

    @abstractmethod
    def process_methods(self, methods: List[dict]):
        pass

    @abstractmethod
    def process_fields(self, fields: List[dict]):
        pass


class JavaAPIGraphBuilder(APIGraphBuilder):
    def __init__(self, target_language):
        super().__init__()
        self.target_language = target_language
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self._class_name = None
        self._class_type_var_map: dict = {}
        self._current_func_type_var_map: dict = {}
        self._is_func_interface: bool = False

    def build(self, docs: dict) -> APIGraph:
        for api_doc in docs.values():
            if not api_doc["type_parameters"]:
                continue
            cls_name = api_doc["name"]
            self._class_name = cls_name
            self._class_type_var_map[cls_name] = OrderedDict()
            self._rename_type_parameters(
                cls_name, api_doc["type_parameters"],
                self._class_type_var_map[cls_name]
            )
        return super().build(docs)

    def get_type_parser(self):
        return JavaTypeParser(
            self.target_language,
            self._class_type_var_map.get(self._class_name, {}),
            self._current_func_type_var_map,
            self._class_type_var_map
        )

    def parse_type(self, str_t: str):
        return self.get_type_parser().parse_type(str_t)

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
            field_type = self.parse_type(field_api["type"])
            self.graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def _rename_type_parameters(self, prefix: str,
                                type_parameters: List[str],
                                type_name_map: OrderedDict):
        # We use an OrderedDict because we need to store type parameters
        # in the order they appear in the corresponding definitions.
        for i, type_param_str in enumerate(type_parameters):
            type_param = self.get_type_parser().parse_type_parameter(
                type_param_str, keep=True)

            # We use this auxiliarry type parameter to handle the renaming
            # of recursive bounds.
            type_param_no_bound = tp.TypeParameter(
                type_param.name, variance=type_param.variance)
            new_name = prefix + ".T" + str(i + 1)
            type_var_map = {type_param_no_bound: tp.TypeParameter(new_name)}

            bound = None
            if type_param.bound:
                bound = tp.substitute_type(type_param.bound, type_var_map)

            renamed = tp.TypeParameter(new_name, bound=bound)
            type_name_map[type_param.name] = renamed
            if bound and bound.is_parameterized():

                # This loop iterates over the type parameters of the type
                # constructor associated with the bound. It then replaces
                # the "incomplete" type parameter with "renamed", as the
                # latter is now complete.
                for i, tpa in enumerate(
                        list(bound.t_constructor.type_parameters)):
                    if tpa.name == renamed.name:
                        bound.t_constructor.type_parameters[i] = deepcopy(
                            renamed)

    def _build_api_output_type(self, source_node, output_type,
                               is_constructor=False):
        if is_constructor:
            output_type = self._class_node

        is_array = output_type.name == self.bt_factory.get_array_type().name
        if output_type.is_parameterized() and not is_array:
            target_node = output_type.t_constructor
            self.graph.add_node(target_node)
            kwargs = {
                "constraint": output_type.get_type_variable_assignments()
            }
            self.graph.add_edge(source_node, target_node, label=OUT,
                                **kwargs)
        else:
            target_node = output_type
            self.graph.add_node(target_node)
            self.graph.add_edge(source_node, target_node, label=OUT)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue
            name = method_api["name"]
            self._current_func_type_var_map = OrderedDict()
            self._rename_type_parameters(
                self._class_name + "." + name, method_api["type_parameters"],
                self._current_func_type_var_map
            )
            type_parameters = list(self._current_func_type_var_map.values())
            is_constructor = method_api["is_constructor"]
            is_static = method_api["is_static"]
            parameters = [self.parse_type(p) for p in method_api["parameters"]]
            for param in parameters:
                self.graph.add_node(param)
            if is_constructor:
                method_node = Constructor(self._class_name,
                                          parameters)
            elif is_static:
                method_node = Method(self._class_name + "." + name,
                                     self._class_name,
                                     parameters,
                                     type_parameters)
            else:
                method_node = Method(name, self._class_name, parameters,
                                     type_parameters)
            self.graph.add_node(method_node)
            if not (is_constructor or is_static):
                self.graph.add_edge(class_node, method_node, label=IN)
            output_type = None
            ret_type = method_api["return_type"]
            if not is_constructor:
                output_type = self.parse_type(ret_type)
            self._build_api_output_type(method_node, output_type,
                                        is_constructor)
            self._current_func_type_var_map = {}
            is_abstract = not method_api.get("is_default", False) and not \
                method_api["is_static"]
            if self._is_func_interface and is_abstract:
                func_params = [param.box_type() for param in parameters]
                ret_type = self.parse_type(ret_type)
                func_type = self.bt_factory.get_function_type(
                    len(func_params)).new(func_params + [ret_type.box_type()])
                self.functional_types[class_node] = func_type

    def construct_class_type(self, class_api):
        class_name = class_api["name"]
        if class_api["type_parameters"]:
            class_node = tp.TypeConstructor(
                class_name,
                list(self._class_type_var_map[class_name].values()))
        else:
            class_node = self.parse_type(class_name)
        return class_node

    def process_class(self, class_api):
        self._class_name = class_api["name"]
        class_node = self.construct_class_type(class_api)
        self._class_node = class_node
        self.graph.add_node(class_node)
        self.subtyping_graph.add_node(class_node)
        self._is_func_interface = class_api.get("functional_interface", False)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])
        super_types = {
            self.parse_type(st)
            for st in class_api["implements"] + class_api["inherits"]
        }
        if not super_types:
            super_types.add(self.parse_type("java.lang.Object"))
        for st in super_types:
            kwargs = {}
            source = st
            if st.is_parameterized():
                source = st.t_constructor
                kwargs["constraint"] = st.get_type_variable_assignments()
            self.subtyping_graph.add_node(source)
            # Do not connect a node with itself.
            if class_node != source:
                self.subtyping_graph.add_edge(source, class_node,
                                              **kwargs)


class KotlinAPIGraphBuilder(APIGraphBuilder):
    def __init__(self, target_language="kotlin"):
        super().__init__()
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self._class_name = None
        self._class_type_var_map: dict = {}
        self._current_func_type_var_map: dict = {}
        self._is_func_interface: bool = False
        self._type_parameters = set()
        self.kt_translator = KotlinTranslator()

    def build(self, docs: dict) -> APIGraph:
        for api_doc in docs.values():
            if not api_doc["type_parameters"]:
                continue
            cls_name = api_doc["name"]
            self._class_name = cls_name
            self._class_type_var_map[cls_name] = OrderedDict()
            self._rename_type_parameters(
                cls_name, api_doc["type_parameters"],
                self._class_type_var_map[cls_name]
            )
        return super().build(docs)

    def get_type_parser(self):
        return KotlinTypeParser(
            self.target_language,
            self._class_type_var_map.get(self._class_name, {}),
            self._current_func_type_var_map,
            self._class_type_var_map,
            self._type_parameters
        )

    def parse_type(self, str_t: str):
        return self.get_type_parser().parse_type(str_t)

    def _rename_type_parameters(self, prefix: str,
                                type_parameters: List[str],
                                type_name_map: OrderedDict):
        # We use an OrderedDict because we need to store type parameters
        # in the order they appear in the corresponding definitions.
        for i, type_param_str in enumerate(type_parameters):
            type_param = self.parse_type_parameter(type_param_str,
                                                   keep=True)

            # We use this auxiliarry type parameter to handle the renaming
            # of recursive bounds.
            type_param_no_bound = tp.TypeParameter(
                type_param.name, variance=type_param.variance)
            new_name = prefix + ".T" + str(i + 1)
            type_var_map = {type_param_no_bound: tp.TypeParameter(new_name)}

            bound = None
            if type_param.bound:
                bound = tp.substitute_type(type_param.bound, type_var_map)

            renamed = tp.TypeParameter(new_name, bound=bound)
            type_name_map[type_param.name] = renamed
            if bound and bound.is_parameterized():

                # This loop iterates over the type parameters of the type
                # constructor associated with the bound. It then replaces
                # the "incomplete" type parameter with "renamed", as the
                # latter is now complete.
                for i, tpa in enumerate(
                        list(bound.t_constructor.type_parameters)):
                    if tpa.name == renamed.name:
                        bound.t_constructor.type_parameters[i] = deepcopy(
                            renamed)

    def _build_api_output_type(self, source_node, output_type,
                               is_constructor=False):
        if is_constructor:
            output_type = self._class_node

        is_array = output_type.name == self.bt_factory.get_array_type().name
        if output_type.is_parameterized() and not is_array:
            target_node = output_type.t_constructor
            self.graph.add_node(target_node)
            kwargs = {
                "constraint": output_type.get_type_variable_assignments()
            }
            self.graph.add_edge(source_node, target_node, label=OUT,
                                **kwargs)
        else:
            target_node = output_type
            self.graph.add_node(target_node)
            self.graph.add_edge(source_node, target_node, label=OUT)

    def process_fields(self, class_node, fields):
        for field_api in fields:
            if field_api["access_mod"] == PROTECTED:
                continue
            if class_node:
                receiver = class_node
            receiver = (
                self.parse_type(field_api["receiver"])
                if field_api["receiver"]
                else class_node)
            if receiver:
                self._class_name = (
                    receiver.name
                    if not receiver.is_parameterized()
                    else self.kt_translator.get_type_name(receiver)
                )
                self.graph.add_node(receiver)
            field_node = Field(field_api["name"], self._class_name)
            self.graph.add_node(field_node)
            if receiver:
                self.graph.add_edge(receiver, field_node, label=IN)
            field_type = self.parse_type(field_api["type"])
            self._build_api_output_type(field_node, field_type)

    def process_methods(self, class_node, methods):
        current_type_parameters = self._type_parameters
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue
            name = method_api["name"]

            self._current_func_type_var_map = OrderedDict()
            self._rename_type_parameters(
                self._class_name or method_api["receiver"] + "." + name,
                method_api["type_parameters"],
                self._current_func_type_var_map
            )
            type_parameters = list(self._current_func_type_var_map.values())
            self._type_parameters = self._type_parameters.union(
                self._current_func_type_var_map.keys())
            if class_node:
                receiver = class_node
            receiver = (self.parse_type(method_api["receiver"])
                        if method_api["receiver"]
                        else class_node)
            if receiver:
                self._class_name = (
                    receiver.name
                    if not receiver.is_parameterized()
                    else self.kt_translator.get_type_name(receiver)
                )
                self.graph.add_node(receiver)

            parameters = [self.parse_type(p) for p in method_api["parameters"]]
            for param in parameters:
                self.graph.add_node(param)

            is_constructor = method_api["is_constructor"]
            if is_constructor:
                method_node = Constructor(self._class_name,
                                          parameters)
            else:
                method_node = Method(name, self._class_name, parameters,
                                     type_parameters)
            self.graph.add_node(method_node)
            if not (is_constructor or receiver is None):
                self.graph.add_edge(receiver, method_node, label=IN)
            output_type = None
            ret_type = method_api["return_type"]
            if not is_constructor:
                output_type = self.parse_type(ret_type)
            self._build_api_output_type(method_node, output_type,
                                        is_constructor)
            self._current_func_type_var_map = {}
            is_abstract = not method_api.get("is_default", False) and not \
                method_api["is_static"]
            if self._is_func_interface and is_abstract:
                func_params = [param.box_type() for param in parameters]
                ret_type = self.parse_type(ret_type)
                func_type = self.bt_factory.get_function_type(
                    len(func_params)).new(func_params + [ret_type.box_type()])
                self.functional_types[class_node] = func_type
            self._type_parameters = current_type_parameters

    def construct_class_type(self, class_api):
        class_name = class_api["name"]
        if class_api["type_parameters"]:
            self._type_parameters = set(
                self._class_type_var_map[class_name].keys())
            class_node = tp.TypeConstructor(
                class_name,
                list(self._class_type_var_map[class_name].values()))
        else:
            class_node = self.parse_type(class_name)
        return class_node

    def _process_class(self, class_api: dict):
        self._class_name = class_api["name"]
        class_node = self.construct_class_type(class_api)
        self._class_node = class_node
        self.graph.add_node(class_node)
        self.subtyping_graph.add_node(class_node)
        self._is_func_interface = class_api.get("functional_interface", False)
        self.process_fields(class_node, class_api["fields"])
        self.process_methods(class_node, class_api["methods"])
        super_types = {
            self.parse_type(st)
            for st in class_api["implements"] + class_api["inherits"]
        }
        if not super_types:
            super_types.add(self.parse_type("Any"))
        for st in super_types:
            kwargs = {}
            source = st
            if st.is_parameterized():
                source = st.t_constructor
                kwargs["constraint"] = st.get_type_variable_assignments()
            self.subtyping_graph.add_node(source)
            # Do not connect a node with itself.
            if class_node != source:
                self.subtyping_graph.add_edge(source, class_node,
                                              **kwargs)
        self._type_parameters = set()

    def process_class(self, class_api):
        if class_api["is_class"]:
            self._process_class(class_api)
        else:
            self._class_name = None
            self.process_methods(None, class_api["methods"])
            self.process_fields(None, class_api["fields"])
