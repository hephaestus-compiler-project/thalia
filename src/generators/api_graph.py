from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from typing import NamedTuple, List, Union, Set
import re

import networkx as nx

from src import utils
from src.ir import (
    BUILTIN_FACTORIES, types as tp, kotlin_types as kt,
    type_utils as tu)
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


class UpperBoundConstraint(NamedTuple):
    bound: tp.Type


class EqualityConstraint(NamedTuple):
    t: tp.Type


UNSATISFIABLE = object()


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


class APIGraph():
    # TODO

    EMPTY = 0

    def __init__(self, api_graph, subtyping_graph):
        self.api_graph = api_graph
        self.subtyping_graph = subtyping_graph
        self._types = [node.t for node in self.subtyping_graph.nodes()
                       if not node.t.is_type_constructor()]

    def solve_constraint(self, constraint, type_var_map):
        for type_k, type_v in constraint.items():
            if not type_k.is_type_var():
                continue
            assignment = tp.substitute_type(type_k, type_var_map)
            sub = tu.unify_types(assignment, type_v, None, same_type=False)
            is_invalid = (
                assignment != type_v and
                (not sub or any(type_var_map.get(k, v) != v
                                for k, v in sub.items()))
            )
            if is_invalid:
                return None
            type_var_map[type_v] = assignment
        return type_var_map

    def subtypes(self, node: TypeNode):
        subtypes = {node}
        if node.t.is_type_var():
            return subtypes
        if node.t.is_parameterized() and node.t.has_wildcards():
            # TODO Handle wildcards
            return subtypes
        if not node.t.is_parameterized():
            subtypes.update(nx.descendants(self.subtyping_graph, node))
            return subtypes
        type_var_map = node.t.get_type_variable_assignments()
        excluded_nodes = set()
        for k, v in nx.dfs_edges(self.subtyping_graph,
                                 TypeNode(node.t.t_constructor)):
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
                    v.t, self._types, type_var_map=type_var_map)[0]))
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
            type_var_map = self._compute_type_var_map(path)
            constraints = self._collect_constraints(path, origin, type_var_map)
            assignments = self.instantiate_type_variables(constraints,
                                                          type_var_map)
            if assignments is None:
                continue
            node_path = OrderedDict()
            for source, target in path:
                node_path[source] = True
                node_path[target] = True
            return list(node_path.keys()), assignments
        return None

    def _collect_constraints(self, path: list, target: TypeNode,
                             type_var_map: dict):
        constraints = defaultdict(set)
        if target.t.is_parameterized():
            for k, v in target.t.get_type_variable_assignments().items():
                t = tp.substitute_type(k, type_var_map)
                if t.has_type_variables():
                    sub = tu.unify_types(v, t, None, same_type=False)
                    assert sub is not None
                    for k, v in sub.items():
                        constraints[k].add(EqualityConstraint(v))
                else:
                    constraints[k].add(EqualityConstraint(v))
                    constraints[k].add(EqualityConstraint(t))
        nodes = OrderedDict()
        for source, target in path:
            if isinstance(source, TypeNode):
                if source.t.is_type_constructor():
                    nodes.update({k: True for k in source.t.type_parameters})
            if isinstance(target, TypeNode):
                if target.t.is_type_constructor():
                    nodes.update({k: True for k in target.t.type_parameters})

        for node in nodes:
            constraints[node]
            if node.is_type_var() and node.bound:
                t = tp.substitute_type(node, type_var_map)
                if t.has_type_variables():
                    sub = tu.unify_types(v, t, None, same_type=False)
                    for k, v in sub.items():
                        constraint = (
                            UpperBoundConstraint(node.bound)
                            if t.is_type_var()
                            else EqualityConstraint(v)
                        )
                        constraints[k].add(constraint)
                else:
                    constraints[node].add(EqualityConstraint(t))
                    constraints[node].add(UpperBoundConstraint(
                        tp.substitute_type(node.bound, type_var_map)))
        ordered_constraints = OrderedDict()
        for node in nodes:
            ordered_constraints[node] = constraints[node]
        return ordered_constraints

    def instantiate_type_variables(self, constraints, type_var_map):
        type_var_assignments = {}
        free_variables = {
            k
            for k in constraints.keys()
            if k not in type_var_map
        }
        for type_var in list(free_variables) + list(type_var_map.keys()):
            type_var_constraints = constraints[type_var]
            if not type_var_constraints:
                t = type_var_map.get(type_var)
                if t is None:
                    t = utils.random.choice(self._types)
                type_var_assignments[type_var] = tp.substitute_type(
                    t, type_var_assignments)
                continue

            upper_bounds = [c.bound for c in type_var_constraints
                            if isinstance(c, UpperBoundConstraint)]
            eqs = [c.t for c in type_var_constraints
                   if isinstance(c, EqualityConstraint)]
            if len(eqs) > 1:
                return None
            if len(eqs) == 1:
                type_var_assignments[type_var] = eqs[0]
                continue

            if len(upper_bounds) > 1:
                type_var_assignments[type_var] = upper_bounds[0]
                continue

            new_bounds = set()
            for bound in set(upper_bounds):
                supers = self.supertypes()
                if any(s.t in upper_bounds
                       for s in supers):
                    new_bounds.append(bound)
            if len(new_bounds) > 1:
                return None
            if len(new_bounds) == 1:
                type_var_assignments[type_var] = new_bounds[0]
            return None

        return type_var_assignments

    def _compute_type_var_map(self, path: list):
        type_var_map = OrderedDict()
        for source, target in path:
            constraint = self.api_graph[source][target].get("constraint")
            if not constraint:
                continue
            for type_k, type_v in constraint.items():
                sub_t = tp.substitute_type(type_v, type_var_map)
                if sub_t.has_type_variables():
                    type_var_map[type_k] = sub_t
                else:
                    type_var_map[type_k] = type_v
        return type_var_map

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
            if not view:
                receivers = {self.EMPTY}
            else:
                assert len(view) == 1
                receiver = list(view)[0][0]
                receivers = {receiver}
                if receiver.t != self.bt_factory.get_any_type():
                    receivers.update(self.subtypes(receiver))
            parameters = [{p} for p in getattr(node, "parameters", [])]
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
            ret_types = self.supertypes(ret_type)
            ret_types.add(ret_type)
            encodings.append(APIEncoding(node, frozenset(receivers),
                                         parameters,
                                         frozenset(ret_types)))
        return encodings


class APIGraphBuilder(ABC):
    def __init__(self):
        self.graph: nx.DiGraph = None
        self.subtyping_graph: nx.DiGraph = None

    def build(self, docs: dict) -> APIGraph:
        self.graph = nx.DiGraph()
        self.subtyping_graph = nx.DiGraph()
        for api_doc in docs.values():
            self.process_class(api_doc)
        return APIGraph(self.graph, self.subtyping_graph)

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

    def build(self, docs: dict) -> APIGraph:
        for api_doc in docs.values():
            if not api_doc["type_parameters"]:
                continue
            cls_name = api_doc["name"]
            type_param_map = OrderedDict()
            for i, type_param_str in enumerate(api_doc["type_parameters"]):
                type_param = self.parse_type_parameter(type_param_str)
                bound = None
                if type_param.bound:
                    bound = type_param_map.get(type_param.bound.name,
                                               type_param.bound)
                type_param_map[type_param.name] = tp.TypeParameter(
                    cls_name + ".T" + str(i), bound=bound)
            self._class_type_var_map[cls_name] = type_param_map
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

    def parse_type_parameter(self, str_t: str) -> tp.TypeParameter:
        segs = str_t.split(" extends ")
        type_var_map = self._class_type_var_map.get(self._class_name, {})
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
            self.subtyping_graph.add_node(field_type)
            self.graph.add_edge(field_node, field_type, label=OUT)

    def _build_api_output_type(self, source_node, output_type,
                               is_constructor=False):
        if is_constructor:
            if self._class_node.t.is_type_constructor():
                output_type = self._class_name.t.new(
                    self._class_node.t.type_parameters)
            else:
                output_type = self._class_node

        if output_type.is_parameterized():
            target_node = TypeNode(output_type.t_constructor)
            self.graph.add_node(target_node)
            self.subtyping_graph.add_node(target_node)
            kwargs = {
                "constraint": output_type.get_type_variable_assignments()
            }
            self.graph.add_edge(source_node, target_node, label=OUT,
                                **kwargs)
        else:
            target_node = TypeNode(output_type)
            self.graph.add_node(target_node)
            self.subtyping_graph.add_node(target_node)
            self.graph.add_edge(source_node, target_node, label=OUT)

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
            output_type = None
            if not is_constructor:
                output_type = self.parse_type(method_api["return_type"])
            self._build_api_output_type(method_node, output_type,
                                        is_constructor)

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
        self.graph.add_node(class_node)
        self.subtyping_graph.add_node(class_node)
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
