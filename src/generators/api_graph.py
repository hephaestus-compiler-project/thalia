from abc import ABC, abstractmethod
from collections import OrderedDict
from copy import deepcopy
import itertools
from typing import NamedTuple, List, Union, Set, Dict, Tuple
import re

import networkx as nx

from src import utils
from src.ir import (
    BUILTIN_FACTORIES, types as tp, kotlin_types as kt,
    type_utils as tu)
from src.ir.builtins import BuiltinFactory
from src.generators.api import utils as au


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
    type_parameters: List[tp.TypeParameter]

    def __str__(self):
        type_parameters_str = ""
        if self.type_parameters:
            type_parameters_str = "<{}>".format(",".join(
                [str(tpa) for tpa in self.type_parameters]))
        return "{}{}({})".format(type_parameters_str,
                                 self.name,
                                 ",".join(str(p) for p in self.parameters))

    __repr__ = __str__

    def __hash__(self):
        return hash(str(self.name) + str(self.cls) + str(
            self.parameters) + str(self.type_parameters))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.name == other.name and
            self.cls == other.cls and
            self.parameters == other.parameters and
            self.type_parameters == other.type_parameters
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


class APIEncoding(NamedTuple):
    api: Union[Field, Method, Constructor]
    receivers: Set[TypeNode]
    parameters: Set[TypeNode]
    returns: Set[TypeNode]
    type_var_map: dict


def _get_type_variables(path: list) -> List[tp.TypeParameter]:
    node_path = OrderedDict()
    for source, target in path:
        node_path[source] = True
        node_path[target] = True

    nodes = []
    for node in node_path.keys():
        if isinstance(node, TypeNode):
            if node.t.is_type_constructor():
                nodes.extend(node.t.type_parameters)
        if isinstance(node, Method):
            nodes.extend(node.type_parameters)
    return nodes


class APIGraph():
    # TODO

    EMPTY = 0

    def __init__(self, api_graph, subtyping_graph, functional_types,
                 bt_factory):
        self.api_graph: nx.DiGraph = api_graph
        self.subtyping_graph: nx.DiGraph = subtyping_graph
        self.functional_types: Dict[tp.Type, tp.ParameterizedType] = \
            functional_types
        self.bt_factory = bt_factory
        self._types = {node.t
                       for node in self.subtyping_graph.nodes()
                       if not node.t.is_type_constructor()}
        self._all_types = {node.t.name: node.t
                           for node in self.subtyping_graph.nodes()}

    def get_reg_types(self):
        types = [
            t
            for t in self._types
            if (
                not t.has_type_variables() and
                t != self.bt_factory.get_void_type() and
                not getattr(t, "primitive", False)
            )
        ]
        return types

    def get_random_type(self):
        types = self.get_reg_types()
        return utils.random.choice(types)

    def get_type_by_name(self, typename):
        return self._all_types.get(typename)

    def solve_constraint(self, constraint, type_var_map):
        for type_k, type_v in constraint.items():
            if not type_k.has_type_variables():
                continue
            assignment = tp.substitute_type(type_k, type_var_map)
            sub = tu.unify_types(assignment, type_v, self.bt_factory,
                                 same_type=False)
            is_invalid = (
                assignment != type_v and
                (not sub or any(type_var_map.get(k, v) != v
                                for k, v in sub.items()))
            )
            if is_invalid:
                return None
            type_var_map[type_v] = assignment
        return type_var_map

    def _subtypes_of_wildcards(self, node):
        possible_type_args = []
        subtypes = set()
        for t_arg in node.t.type_args:
            if not t_arg.is_wildcard():
                possible_type_args.append([t_arg])
                continue
            if t_arg.is_invariant():
                possible_type_args.append(self.get_reg_types())
            elif t_arg.is_covariant():
                possible_type_args.append({
                    n.t for n in self.subtypes(TypeNode(t_arg.bound))
                    if not n.t.is_type_constructor()})
            else:
                possible_type_args.append({n.t for n in self.supertypes(
                    TypeNode(t_arg.bound))})
        for combination in itertools.product(*possible_type_args):
            new_sub = node.t.t_constructor.new(list(combination))
            subtypes.add(TypeNode(new_sub))
            subtypes.update(self.subtypes(TypeNode(new_sub)))
        return subtypes

    def subtypes(self, node: TypeNode):
        subtypes = {node}
        if node.t.is_type_var():
            return subtypes
        if node.t.is_parameterized() and any(t_arg.is_wildcard()
                                             for t_arg in node.t.type_args):
            subtypes.update(self._subtypes_of_wildcards(node))
            return subtypes
        if not node.t.is_parameterized() and not node.t.is_type_constructor():
            if node not in self.subtyping_graph:
                return subtypes
            subtypes.update(nx.descendants(self.subtyping_graph, node))
            return subtypes

        node_t = node.t
        if node_t.is_type_constructor():
            # FIXME type constructor subtypes
            return subtypes

        type_var_map = node_t.get_type_variable_assignments()
        node = TypeNode(node_t.t_constructor)
        if node not in self.subtyping_graph:
            return subtypes
        excluded_nodes = set()
        for k, v in nx.dfs_edges(self.subtyping_graph, node):
            constraint = self.subtyping_graph[k][v].get("constraint") or {}
            if not constraint:
                subtypes.add(v)
            solution = self.solve_constraint(constraint,
                                             dict(type_var_map))
            if not solution or k in excluded_nodes:
                excluded_nodes.add(v)
                continue
            type_var_map = solution
            if v.t.is_type_constructor():
                subtypes.add(TypeNode(tu.instantiate_type_constructor(
                    v.t, self.get_reg_types(), type_var_map=type_var_map)[0]))
            else:
                subtypes.add(v)
        return subtypes

    def supertypes(self, node: TypeNode):
        reverse_graph = self.subtyping_graph.reverse()
        supertypes = set()
        constraints = {}
        if node.t.is_parameterized():
            constraints.update(node.t.get_type_variable_assignments())
            node = TypeNode(node.t.t_constructor)
        if node not in self.subtyping_graph:
            return supertypes
        if node not in reverse_graph:
            return supertypes
        for k, v in nx.dfs_edges(reverse_graph, node):
            constraint = reverse_graph[k][v].get("constraint") or {}
            if not constraint:
                supertypes.add(v)
                continue
            for type_k, type_v in constraint.items():
                if type_v.has_type_variables():
                    t = tp.substitute_type(type_v, constraints)
                else:
                    t = type_v
                constraints[type_k] = t
            else:
                supertypes.add(TypeNode(tu.instantiate_type_constructor(
                    v.t, {}, type_var_map=constraints)[0]))
        return supertypes

    def find_API_path(self, target: TypeNode) -> list:
        origin = target
        if target.t.is_parameterized():
            target = TypeNode(target.t.t_constructor)
        if target not in self.api_graph:
            return None
        source_nodes = [
            node
            for node, indegree in self.api_graph.in_degree(
                self.api_graph.nodes())
            if indegree == 0 and nx.has_path(self.api_graph, node, target)
        ]
        if not source_nodes:
            return None

        source = utils.random.choice(source_nodes)
        if source == target:
            return None
        for path in nx.all_simple_edge_paths(self.api_graph, source=source,
                                             target=target):
            assignment_graph = au.compute_assignment_graph(self.api_graph,
                                                           path)
            type_variables = _get_type_variables(path)
            constraints = au.collect_constraints(origin.t, type_variables,
                                                 assignment_graph,
                                                 self.bt_factory)
            assignments = au.instantiate_type_variables(self, constraints,
                                                        assignment_graph)
            if assignments is None:
                continue
            node_path = OrderedDict()
            for source, target in path:
                node_path[source] = True
                node_path[target] = True
            pruned_path = [n for i, n in enumerate(node_path.keys())
                           if i == 0 or not isinstance(n, TypeNode)]
            return pruned_path, assignments
        return None

    def get_functional_type(self, etype: tp.Type):
        class_type = etype
        if etype.is_parameterized():
            class_type = etype.t_constructor
        return self.functional_types.get(class_type)

    def get_function_refs_of(self, etype: tp.Type) -> List[Tuple[Method, dict]]:
        type_var_map = {}
        if etype.is_parameterized():
            etype = etype.to_variance_free()
            type_var_map = etype.get_type_variable_assignments()
        func_type = self.get_functional_type(etype)
        assert func_type is not None
        func_type = tp.substitute_type(func_type, type_var_map)
        candidate_functions = []
        for api in self.api_graph.nodes():
            if not isinstance(api, Method):
                continue
            param_types = [p.t.box_type() for p in api.parameters]
            view = self.api_graph.out_edges(api)
            assert len(view) == 1
            out_type = list(view)[0][1].t
            if out_type.is_type_constructor():
                constraint = self.api_graph[api][
                    TypeNode(out_type)].get("constraint")
                out_type = out_type.new(
                    [constraint[tpa] for tpa in out_type.type_parameters])
            api_type = self.bt_factory.get_function_type(
                len(param_types)).new(param_types + [out_type.box_type()])
            sub = tu.unify_types(func_type, api_type, self.bt_factory,
                                 same_type=True)
            if sub:
                candidate_functions.append((api, sub))
        return candidate_functions

    def encode_api_components(self) -> List[APIEncoding]:
        api_components = (Field, Constructor, Method)
        api_nodes = [
            n
            for n in self.api_graph.nodes()
            if isinstance(n, api_components)
        ]
        encodings = []
        for node in api_nodes:
            view = self.api_graph.in_edges(node)
            type_var_map = {}
            if not view:
                receivers = {self.EMPTY}
            else:
                assert len(view) == 1
                receiver = list(view)[0][0]
                if receiver.t.is_type_constructor():
                    # TODO Revisit
                    receiver_t, type_var_map = tu.instantiate_type_constructor(
                        receiver.t, self.get_reg_types()
                    )
                    receiver = TypeNode(receiver_t)
                receivers = {receiver}
                if receiver.t != self.bt_factory.get_any_type():
                    receivers.update(self.subtypes(receiver))
            type_parameters = getattr(node, "type_parameters", [])
            if type_parameters:
                type_var_map.update(
                    tu.instantiate_parameterized_function(
                        type_parameters, self.get_reg_types()))
            parameters = [{TypeNode(tp.substitute_type(p.t, type_var_map))}
                          for p in getattr(node, "parameters", [])]
            for param_set in parameters:
                param = list(param_set)[0]
                if param.t != self.bt_factory.get_any_type():
                    param_set.update(self.subtypes(param))
            if not parameters:
                parameters = ({self.EMPTY},)
            parameters = tuple([frozenset(s) for s in parameters])
            view = self.api_graph.out_edges(node)
            assert len(view) == 1
            ret_type = list(view)[0][1]
            constraint = self.api_graph[node][ret_type].get("constraint", {})
            if constraint:
                ret_type = TypeNode(
                    ret_type.t.new([constraint[tpa]
                                   for tpa in ret_type.t.type_parameters])
                )
            ret_type = TypeNode(tp.substitute_type(ret_type.t, type_var_map))
            ret_types = self.supertypes(ret_type)
            ret_types.add(ret_type)
            encodings.append(APIEncoding(node, frozenset(receivers),
                                         parameters,
                                         frozenset(ret_types),
                                         type_var_map))
        return encodings


class APIGraphBuilder(ABC):
    def __init__(self):
        self.graph: nx.DiGraph = None
        self.subtyping_graph: nx.DiGraph = None
        self.functional_types: Dict[tp.Type, tp.ParameterizedType] = {}
        self.bt_factory = None

    def build(self, docs: dict) -> APIGraph:
        self.graph = nx.DiGraph()
        self.subtyping_graph = nx.DiGraph()
        for api_doc in docs.values():
            self.process_class(api_doc)
        return APIGraph(self.graph, self.subtyping_graph,
                        self.functional_types, self.bt_factory)

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
        self._current_func_type_var_map: dict = {}
        self._is_func_interface: bool = False

    def build(self, docs: dict) -> APIGraph:
        for api_doc in docs.values():
            if not api_doc["type_parameters"]:
                continue
            cls_name = api_doc["name"]
            self._class_type_var_map[cls_name] = self._rename_type_parameters(
                cls_name, api_doc["type_parameters"]
            )
        return super().build(docs)

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

    def parse_type_parameter(self, str_t: str,
                             keep: bool = False) -> tp.TypeParameter:
        segs = str_t.split(" extends ")
        type_var_map = deepcopy(
            self._class_type_var_map.get(self._class_name, {}))
        type_var_map.update(self._current_func_type_var_map)
        if keep:
            type_var_map = {}

        if len(segs) == 1:
            return type_var_map.get(str_t, tp.TypeParameter(str_t))
        bound = self.parse_type(segs[1])
        return type_var_map.get(segs[0],
                                tp.TypeParameter(segs[0], bound=bound))

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
        type_var_map = self._class_type_var_map.get(base)
        if type_var_map:
            type_vars = list(type_var_map.values())
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
            # self.subtyping_graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def _rename_type_parameters(self, prefix: str,
                                type_parameters: List[str]) -> OrderedDict:
        # We use an OrderedDict because we need to store type parameters
        # in the order they appear in the corresponding definitions.
        type_param_map = OrderedDict()
        for i, type_param_str in enumerate(type_parameters):
            type_param = self.parse_type_parameter(type_param_str,
                                                   keep=True)
            bound = None
            if type_param.bound:
                bound = type_param_map.get(type_param.bound.name,
                                           type_param.bound)
            type_param_map[type_param.name] = tp.TypeParameter(
                prefix + ".T" + str(i), bound=bound)
        return type_param_map

    def _build_api_output_type(self, source_node, output_type,
                               is_constructor=False):
        if is_constructor:
            output_type = self._class_node.t

        is_array = output_type.name == self.bt_factory.get_array_type().name
        if output_type.is_parameterized() and not is_array:
            target_node = TypeNode(output_type.t_constructor)
            self.graph.add_node(target_node)
            # self.subtyping_graph.add_node(target_node)
            kwargs = {
                "constraint": output_type.get_type_variable_assignments()
            }
            self.graph.add_edge(source_node, target_node, label=OUT,
                                **kwargs)
        else:
            target_node = TypeNode(output_type)
            self.graph.add_node(target_node)
            # self.subtyping_graph.add_node(target_node)
            self.graph.add_edge(source_node, target_node, label=OUT)

    def process_methods(self, class_node, methods):
        for method_api in methods:
            if method_api["access_mod"] == PROTECTED:
                continue
            name = method_api["name"]
            self._current_func_type_var_map = self._rename_type_parameters(
                self._class_name + "." + name, method_api["type_parameters"])
            type_parameters = list(self._current_func_type_var_map.values())
            is_constructor = method_api["is_constructor"]
            is_static = method_api["is_static"]
            parameters = [
                TypeNode(self.parse_type(p))
                for p in method_api["parameters"]
            ]
            for param in parameters:
                self.graph.add_node(param)
                # self.subtyping_graph.add_node(param)
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
                func_params = [param.t.box_type() for param in parameters]
                ret_type = self.parse_type(ret_type)
                func_type = self.bt_factory.get_function_type(
                    len(func_params)).new(func_params + [ret_type.box_type()])
                self.functional_types[class_node.t] = func_type

    def construct_class_type(self, class_api):
        self._class_name = class_api["name"]
        if class_api["type_parameters"]:
            class_node = TypeNode(tp.TypeConstructor(
                self._class_name,
                list(self._class_type_var_map[self._class_name].values())))
        else:
            class_node = TypeNode(self.parse_type(self._class_name))
        return class_node

    def process_class(self, class_api):
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
            source = TypeNode(st)
            if st.is_parameterized():
                source = TypeNode(st.t_constructor)
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
                method_node = Method(name, self._class_name, parameters,
                                     method_api["type_parameters"])
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
