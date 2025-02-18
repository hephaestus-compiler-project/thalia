from abc import ABC, abstractmethod
from collections import OrderedDict
from copy import deepcopy, copy
import re
from typing import List, Dict, Set


import networkx as nx

from src.config import cfg
from src.ir import BUILTIN_FACTORIES, types as tp, kotlin_types as kt
from src.ir.builtins import BuiltinFactory
from src.generators.api.api_graph import (APIGraph, IN, OUT, Method,
                                          Constructor, Field, Parameter)
from src.generators.api.type_parsers import (TypeParser, KotlinTypeParser,
                                             JavaTypeParser, ScalaTypeParser)

PROTECTED = "protected"
PUBLIC = "public"
ROOT_CLASSES = {
    "java": "java.lang.Object",
    "kotlin": "kotlin.Any",
    "scala": "scala.Any"
}


class APIGraphBuilder(ABC):
    def __init__(self, target_language, **kwargs):
        self.target_language: str = target_language
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self.api_language: str = None

        self.graph: nx.DiGraph = None
        self.subtyping_graph: nx.DiGraph = None

        self.functional_types: Dict[tp.Type, tp.ParameterizedType] = {}
        self.class_nodes: dict[str, tp.Type] = {}
        self.class_name: str = None

        self._class_type_var_map: dict = {}
        self._current_func_type_var_map: dict = {}
        self._is_func_interface: bool = False

        self.parsed_types: Dict[str, tp.Type] = {}
        self.parent_cls: tp.Type = None
        self.options = kwargs

    @abstractmethod
    def get_type_parser(self) -> TypeParser:
        pass

    @property
    def type_var_mappings(self):
        type_var_mappings = copy(self._class_type_var_map.get(
            getattr(self.parent_cls, "name", None), {}))
        type_var_mappings.update(self._class_type_var_map.get(
            self.class_name, {}))
        return type_var_mappings

    def _update_supertypes(self):
        for type_var_name_map in self._class_type_var_map.values():
            for type_param in type_var_name_map.values():
                if not type_param.bound:
                    continue
                bound = type_param.bound
                parsed_t = self.parsed_types.get(bound.name)
                if parsed_t is None:
                    continue
                if bound.is_parameterized():
                    bound.t_constructor.supertypes = parsed_t.supertypes
                else:
                    bound.supertypes = parsed_t.supertypes

    def build_topological_sort(self, docs: dict) -> List[str]:
        dep_graph = nx.DiGraph()
        for api_doc in docs.values():
            name = api_doc["name"]
            self.api_language = api_doc.get("language", self.api_language)
            super_types = {
                self.parse_type(st, build_class_node=True)
                for st in api_doc.get("implements", []) + api_doc.get(
                    "inherits", [])
            }
            dep_graph.add_node(name)
            parent = api_doc.get("parent")
            if parent:
                dep_graph.add_node(parent)
                dep_graph.add_edge(parent, name)
            for st in super_types:
                if st == self.bt_factory.get_any_type():
                    continue
                dep_graph.add_node(st.name)
                dep_graph.add_edge(st.name, name)
        return list(nx.topological_sort(dep_graph))

    def rename_class_type_parameters(self, docs: dict,
                                     classes: List[str]) -> Set[str]:
        excluded_cls = set()
        for cls_name in classes:
            api_doc = docs.get(cls_name)
            if not api_doc or not api_doc["type_parameters"]:
                continue
            self.api_language = api_doc.get("language", self.api_language)
            self.class_name = cls_name
            self._class_type_var_map[cls_name] = OrderedDict()
            try:
                self.rename_type_parameters(
                    cls_name, api_doc["type_parameters"],
                    self._class_type_var_map[cls_name]
                )
            except NotImplementedError:
                excluded_cls.add(cls_name)
                del self._class_type_var_map[cls_name]
        return excluded_cls

    def build(self, docs: dict) -> APIGraph:
        top_sort = self.build_topological_sort(docs)
        # First we make a pass to assign class type parameters a unique name.
        excluded_cls = self.rename_class_type_parameters(docs, top_sort)
        top_sort = [c for c in top_sort if c not in excluded_cls]
        self.graph = nx.DiGraph()
        self.subtyping_graph = nx.DiGraph()
        for cls_name in top_sort:
            api_doc = docs.get(cls_name)
            if api_doc:
                self.api_language = api_doc.get("language", self.api_language)
                self.class_name = api_doc["name"]
                if api_doc.get("is_class") is not False:
                    self.build_class_node(api_doc)
        # One more pass to handle recursive upper bounds.
        self._update_supertypes()
        self.rename_class_type_parameters(docs, top_sort)
        for cls_name in top_sort:
            api_doc = docs.get(cls_name)
            if api_doc:
                # Now we are actually processing the docs of each API and build
                # the corresponding API graph.
                self.process_class(api_doc)
        return APIGraph(self.graph, self.subtyping_graph,
                        self.functional_types, self.bt_factory,
                        **self.options)

    def process_class(self, class_api: dict):
        if class_api.get("access_mod", PUBLIC) == PROTECTED:
            return
        self.api_language = class_api.get("language", self.api_language)
        self.class_name = class_api["name"]
        class_node = self.build_class_node(class_api)
        self.graph.add_node(class_node, outer_class=self.parent_cls)
        self.class_nodes[self.class_name] = class_node
        self.subtyping_graph.add_node(class_node)
        self._is_func_interface = class_api.get("functional_interface", False)
        self.process_fields(class_api["fields"])
        self.process_methods(class_api["methods"])
        self.build_subtyping_relations(class_api)
        self.class_name = None
        self.parent_cls: tp.Type = None

    def process_fields(self, fields: List[dict]):
        for field_api in fields:
            if field_api.get("type_parameters", []):
                # TODO support parameterized fields
                continue
            receiver_name = self.get_receiver_name(field_api)
            receiver = self.get_api_incoming_node(field_api)
            prefix = receiver_name + "." if receiver_name else ""
            if field_api["access_mod"] == PROTECTED:
                continue
            field_type = self.parse_type(field_api["type"])
            if field_type is None:
                # Field type is unsupported
                continue
            if field_api["is_static"]:
                field_node = Field(prefix + field_api["name"], receiver_name)
            else:
                field_node = Field(field_api["name"], receiver_name)

            self.graph.add_node(field_node)
            if receiver and not field_api["is_static"]:
                # XXX: Maybe we also need to consider static fields called
                # by a receiver.
                self.graph.add_node(receiver)
                self.graph.add_edge(receiver, field_node, label=IN)
            if field_api["is_static"] and self.parent_cls:
                # Handle fields of non-static inner classes.
                self.graph.add_edge(self.parent_cls, field_node, label=IN)
            out_node, kwargs = self.get_api_outgoing_node(field_type)
            self.graph.add_edge(field_node, out_node, label=OUT, **kwargs)

    def process_methods(self, methods: List[dict]):
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue

            receiver_name = self.get_receiver_name(method_api)
            try:
                method_node = self.build_method_node(method_api, receiver_name)
                if method_node is None:
                    continue
            except NotImplementedError:
                self._current_func_type_var_map = {}
                continue
            receiver = self.get_api_incoming_node(method_api)
            is_constructor = method_api["is_constructor"]
            is_static = method_api["is_static"]
            output_type = None
            ret_type = method_api["return_type"]
            if not is_constructor:
                output_type = self.parse_type(ret_type)
                if output_type is None:
                    self.graph.remove_node(method_node)
                    # Unable to parse output type
                    continue
            else:
                output_type = self.class_nodes[self.class_name]
            if not (is_constructor or is_static or receiver is None):
                self.graph.add_edge(receiver, method_node, label=IN)

            if (is_static or is_constructor) and self.parent_cls:
                # Handle the members of non-static inner classes
                self.graph.add_edge(self.parent_cls, method_node, label=IN)

            out_node, kwargs = self.get_api_outgoing_node(output_type)
            self.graph.add_edge(method_node, out_node, label=OUT, **kwargs)
            self._current_func_type_var_map = {}
            self.build_functional_interface(
                method_api, getattr(method_node, "parameters", []),
                output_type)

    def rename_type_parameters(self, prefix: str,
                               type_parameters: List[str],
                               type_name_map: OrderedDict):
        # We use an OrderedDict because we need to store type parameters
        # in the order they appear in the corresponding definitions.
        for i, type_param_str in enumerate(type_parameters):
            type_param = self.get_type_parser().parse_type_parameter(
                type_param_str, keep=True)
            if not type_param:
                msg = "{str!r} is a type, not currently supported"
                msg = msg.format(str=type_param_str)
                raise NotImplementedError(msg)

            # We use this auxiliarry type parameter to handle the renaming
            # of recursive bounds.
            type_param_no_bounds = [tp.TypeParameter(type_param.name)]
            if type_param.is_type_constructor():
                type_param_no_bounds.append(tp.TypeParameterConstructor(
                    type_param.name, type_param.type_parameters,
                    type_param.variance))
            copied_t = deepcopy(type_param)
            new_name = prefix + ".T" + str(i + 1)
            copied_t.name = new_name
            copied_t.bound = None
            type_var_map = {k: copied_t for k in type_param_no_bounds}

            bound = None
            if type_param.bound:
                bound = tp.substitute_type(type_param.bound, type_var_map)
                # Dirty solution: upper bounds should not be nullable types.
                if (self.api_language == "java" and
                        bound.is_parameterized() and
                        isinstance(bound.t_constructor, kt.NullableType)):
                    bound = bound.type_args[0]

            renamed = deepcopy(copied_t)
            renamed.bound = bound
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
        # One more pass to handle cases like the following:
        # class Foo<T extends Foo<Y>, Y>
        self._update_recursive_type_parameters(type_name_map.values(),
                                               type_name_map)

    def _update_recursive_type_parameters(self, type_parameters, type_name_map):
        for type_param in type_parameters:
            new_type_param = type_name_map.get(type_param.name)
            if new_type_param is not None:
                type_param.name = new_type_param.name
                type_param.bound = new_type_param.bound
            if not type_param.bound or not type_param.bound.is_parameterized():
                continue
            for type_var in type_param.bound.get_type_variables(
                    self.bt_factory):
                new_type_param = type_name_map.get(type_var.name)
                if new_type_param is not None:
                    type_var.name = new_type_param.name
                    type_var.bound = new_type_param.bound
                if type_param.bound.name == self.class_name:
                    type_param.bound.t_constructor.type_parameters = list(
                        type_name_map.values())

    def parse_type(self, str_t: str, **kwargs) -> tp.Type:
        return self.get_type_parser().parse_type(str_t)

    def get_api_outgoing_node(self, output_type: tp.Type):
        kwargs = {}
        if output_type.is_parameterized():
            primitive_array = (
                output_type.t_constructor == self.bt_factory.get_array_type()
                and output_type.type_args[0].is_primitive()
            )
            if primitive_array:
                # If we have a primitive array (e.g., boolean[]), the target
                # node is the primitive array itself.
                target_node = output_type
            else:
                target_node = self.class_nodes.get(output_type.name,
                                                   output_type.t_constructor)
                kwargs["constraint"] = \
                    output_type.get_type_variable_assignments()
        else:
            target_node = output_type

        self.graph.add_node(target_node)
        return target_node, kwargs

    def get_receiver_name(self, method_api: dict) -> str:
        if self.class_name:
            return self.class_name
        return method_api.get("receiver")

    def get_api_incoming_node(self, api_doc: dict) -> tp.Type:
        if self.class_name:
            return self.class_nodes[self.class_name]
        receiver = api_doc.get("receiver")
        if receiver is not None:
            receiver = self.parse_type(receiver)
            return receiver
        return None

    def build_method_type_parameters(
            self, method_api: dict,
            method_fqn: str) -> List[tp.TypeParameter]:
        self._current_func_type_var_map = OrderedDict()
        self.rename_type_parameters(
            method_fqn, method_api["type_parameters"],
            self._current_func_type_var_map
        )
        type_parameters = list(self._current_func_type_var_map.values())
        return type_parameters

    def build_method_node(self, method_api: dict,
                          receiver_name: str) -> Method:
        method_fqn = (
            receiver_name + "." + method_api["name"]
            if receiver_name
            else method_api["name"]
        )
        is_constructor = method_api["is_constructor"]
        is_static = method_api["is_static"]
        type_parameters = self.build_method_type_parameters(method_api,
                                                            method_fqn)
        if any(t is None for t in type_parameters):
            # Unable to parse type parameters
            return None
        parameters = [
            Parameter(self.parse_type(p),
                      self.get_type_parser().is_variable_argument(p))
            for p in method_api["parameters"]
        ]
        if any(p.t is None for p in parameters):
            # Unable to parse parameter types
            return None
        other_metadata = method_api.get("other_metadata", {})
        if is_constructor:
            method_node = Constructor(receiver_name, parameters,
                                      other_metadata)
        elif is_static:
            method_node = Method(method_fqn, receiver_name,
                                 parameters, type_parameters, other_metadata)
        else:
            method_node = Method(method_api["name"], receiver_name, parameters,
                                 type_parameters, other_metadata)
        self.graph.add_node(method_node)
        return method_node

    def build_functional_interface(self, method_api: dict,
                                   parameters: List[Parameter],
                                   ret_type: tp.Type):
        if not cfg.prob.sam_coercion:
            return
        is_abstract = not method_api.get("is_default", False) and not \
            method_api["is_static"]
        if self._is_func_interface and is_abstract:
            func_params = [
                (
                    self.bt_factory.get_array_type().new([param.t])
                    if param.variable
                    else param.t
                )
                for param in parameters
            ]
            func_type = self.bt_factory.get_function_type(
                len(func_params)).new(func_params + [ret_type])
            class_node = self.class_nodes.get(self.class_name)
            assert class_node, ("A functional interface detected. "
                                "This can be None")
            self.functional_types[class_node] = func_type

    def build_tentative_type(self, class_api):
        # We use this auxiliary type constructor for recursive cases in the
        # presence of hk types, such as class Foo extends Bar[Foo]
        if not class_api["type_parameters"]:
            return
        class_name = class_api["name"]
        class_node = tp.TypeConstructor(
            class_name,
            list(self._class_type_var_map[class_name].values())
        )
        self.parsed_types[class_name] = class_node

    def build_class_node(self, class_api: dict) -> tp.Type:
        self.parent_cls = self.class_nodes.get(class_api.get("parent"))
        self.build_tentative_type(class_api)
        super_types = {
            self.parse_type(st, build_class_node=True)
            for st in class_api["implements"] + class_api["inherits"]
        }

        if not super_types:
            super_types.add(self.parse_type(ROOT_CLASSES[self.api_language]))
        class_name = class_api["name"]
        super_types = list(super_types)
        if self.parent_cls is None or not self.parent_cls.is_type_constructor():
            if class_api["type_parameters"]:
                class_node = tp.TypeConstructor(
                    class_name,
                    list(self._class_type_var_map[class_name].values()),
                    super_types
                )
            else:
                class_node = self.parse_type(class_name, build_class_node=True)
            if type(class_node) is tp.SimpleClassifier:
                class_node = tp.SimpleClassifier(class_node.name, super_types)
        else:
            type_params = (
                list(self._class_type_var_map[class_name].values())
                if class_api["type_parameters"]
                else []
            )
            basename = class_name.rsplit(".")[-1]
            class_node = tp.InstanceTypeConstructor(
                class_name, self.parent_cls, basename, type_params,
                super_types)

        self.parsed_types[class_node.name] = class_node
        return class_node

    def build_subtyping_relations(self, class_api: dict):
        super_types = {
            self.parse_type(st, build_class_node=True)
            for st in class_api["implements"] + class_api["inherits"]
        }
        if not super_types:
            super_types.add(self.bt_factory.get_any_type())
        for st in super_types:
            kwargs = {}
            source = st
            if st.is_parameterized():
                source = st.t_constructor
                kwargs["constraint"] = st.get_type_variable_assignments()
            self.subtyping_graph.add_node(source)
            # Do not connect a node with itself.
            class_node = self.class_nodes[self.class_name]
            if class_node != source:
                self.subtyping_graph.add_edge(source, class_node, **kwargs)


class JavaAPIGraphBuilder(APIGraphBuilder):

    def __init__(self, target_language, **kwargs):
        super().__init__(target_language, **kwargs)
        self.api_language = "java"

    def get_type_parser(self):
        return JavaTypeParser(
            self.target_language,
            self.type_var_mappings,
            self._current_func_type_var_map,
            self._class_type_var_map,
            self.parsed_types
        )


class KotlinAPIGraphBuilder(APIGraphBuilder):

    # From https://kotlinlang.org/docs/java-interop.html#mapped-types
    MAPPED_TYPES = {
        "java.lang.Object": "kotlin.Any",
        "java.lang.Cloneable": "kotlin.Cloneable",
        "java.lang.Comparable": "kotlin.Comparable",
        "java.lang.Enum": "kotlin.Enum",
        "java.lang.annotation.Annotation": "kotlin.Annotation",
        "java.lang.CharSequence": "kotlin.CharSequence",
        "java.lang.String": "kotlin.String",
        "java.lang.Number": "kotlin.Number",
        "java.lang.Throwable": "kotlin.Throwable",
        "java.lang.Byte": "kotlin.Byte",
        "java.lang.Short": "kotlin.Short",
        "java.lang.Integer": "kotlin.Int",
        "java.lang.Long": "kotlin.Long",
        "java.lang.Character": "kotlin.Char",
        "java.lang.Float": "kotlin.Float",
        "java.lang.Double": "kotlin.Double",
        "java.lang.Boolean": "kotlin.Boolean",
        "java.util.Iterator": "kotlin.collections.Iterator",
        "java.lang.Iterable": "kotlin.collections.Iterable",
        "java.util.Collection": "kotlin.collections.MutableCollection",
        "java.util.Set": "kotlin.collections.MutableSet",
        "java.util.List": "kotlin.collections.MutableList",
        "java.util.ListIterator": "kotlin.collections.MutableListIterator",
        "java.util.Map": "kotlin.collections.MutableMap",
        "java.util.Map.Entry": "kotlin.collections.MutableMap.MutableEntry"
    }

    PRIMITIVE_TYPES = {
        "char",
        "byte",
        "short",
        "int",
        "long",
        "float",
        "double",
        "boolean"
    }

    def __init__(self, target_language="kotlin", **kwargs):
        super().__init__(target_language, **kwargs)

    def get_type_parser(self, **kwargs):
        parsers = {
            "java": JavaTypeParser,
            "kotlin": KotlinTypeParser
        }
        mapped_types = {
            k: (v, lambda str_t, parser: self.parse_type(
                str_t, type_var_mappings=parser.class_type_name_map,
                build_class_node=kwargs.get("build_class_node")
            ))
            for k, v in self.MAPPED_TYPES.items()
        }
        args = [kwargs.get("type_var_mappings") or self.type_var_mappings,
                self._current_func_type_var_map, self._class_type_var_map,
                self.parsed_types, mapped_types]
        if self.api_language == "java":
            args = ["kotlin"] + args

        return parsers[self.api_language](*args)

    def parse_type(self, str_t: str, build_class_node=False,
                   type_var_mappings=None) -> tp.Type:
        parsed_t = self.get_type_parser(
            type_var_mappings=type_var_mappings,
            build_class_node=build_class_node
        ).parse_type(str_t)
        return parsed_t

    def build_method_node(self, method_api: dict,
                          receiver_name: str) -> Method:
        if not self.api_language == "java":
            return super().build_method_node(method_api, receiver_name)

        # If this method corresponds to a getter (e.g., getValue()), then
        # treat this method as a property (e.g., value).
        regex = re.compile("^get([A-Z].*)$")
        excluded_set = {
            "getOrElse"
        }
        name = method_api["name"]
        match = regex.match(name)
        parameters = method_api["parameters"]
        is_static = method_api["is_static"]
        if not match or name in excluded_set or parameters or is_static:
            return super().build_method_node(method_api, receiver_name)

        field_name = match.group(1)[0].lower() + match.group(1)[1:]
        field_node = Field(field_name, receiver_name)
        self.graph.add_node(field_node)
        return field_node

    def process_class(self, class_api):
        self.api_language = class_api["language"]
        if class_api.get("is_class", True):
            super().process_class(class_api)
        else:
            self._is_func_interface = False
            self.class_name = None
            self.process_methods(class_api["methods"])
            self.process_fields(class_api["fields"])


class ScalaAPIGraphBuilder(APIGraphBuilder):
    MAPPED_TYPES = {
        "java.lang.Object": "scala.AnyRef",
        "java.lang.Byte": "java.lang.Byte",
        "java.lang.Short": "java.lang.Short",
        "java.lang.Integer": "java.lang.Integer",
        "java.lang.Long": "java.lang.Long",
        "java.lang.Float": "java.lang.Float",
        "java.lang.Double": "java.lang.Double",
        "java.lang.Character": "java.lang.Character",
        "java.lang.Boolean": "java.lang.Boolean",
    }
    LANGUAGE = "scala"

    def __init__(self, target_language="scala", **kwargs):
        super().__init__(target_language, **kwargs)

    def get_type_parser(self):
        parsers = {
            "java": JavaTypeParser,
            "scala": ScalaTypeParser
        }
        args = [self.type_var_mappings,
                self._current_func_type_var_map, self._class_type_var_map,
                self.parsed_types, {}]
        scala_parser = ScalaTypeParser(*list(args))
        mapped_types = {
            k: (v, lambda str_t, _: scala_parser.parse_type(str_t))
            for k, v in self.MAPPED_TYPES.items()
        }
        args[-1] = mapped_types
        if self.api_language == "java":
            args = ["scala"] + args

        return parsers[self.api_language](*args)

    def build(self, docs: dict) -> APIGraph:
        # XXX Filter nested classes / objects.
        filtered_docs = {}
        for k, v in docs.items():
            segs = v["name"].split(".")
            parent = v.get("parent")
            lang = v["language"]
            if (parent is not None or lang == self.LANGUAGE) and \
                    len(segs) >= 3 and segs[-2][0].isupper():
                continue
            filtered_docs[k] = v
        return super().build(filtered_docs)
