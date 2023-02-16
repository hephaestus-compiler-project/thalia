from collections import OrderedDict
import itertools
from typing import NamedTuple, List, Union, Set, Dict, Tuple

import networkx as nx

from src import utils
from src.ir import types as tp, type_utils as tu
from src.generators.api import utils as au


IN = 0
OUT = 1
WIDENING = 2
PROTECTED = "protected"


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

    def get_class_name(self):
        return self.cls

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()


class Method(NamedTuple):
    name: str
    cls: str
    parameters: List[tp.Type]
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

    def get_class_name(self):
        return self.cls

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()


class Constructor(NamedTuple):
    name: str
    parameters: List[tp.Type]

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

    def get_class_name(self):
        return self.name

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()


class APIEncoding(NamedTuple):
    api: Union[Field, Method, Constructor]
    receivers: Set[tp.Type]
    parameters: Set[tp.Type]
    returns: Set[tp.Type]
    type_var_map: dict


def _get_type_variables(path: list) -> List[tp.TypeParameter]:
    node_path = OrderedDict()
    for source, target in path:
        node_path[source] = True
        node_path[target] = True

    nodes = []
    for node in node_path.keys():
        if isinstance(node, tp.Type):
            if node.is_type_constructor():
                nodes.extend(node.type_parameters)
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
        self._types = {node
                       for node in self.subtyping_graph.nodes()
                       if not node.is_type_constructor()}
        self._all_types = {node.name: node
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

    def get_incoming_node(self, node):
        view = self.api_graph.in_edges(node)
        assert len(view) == 1
        return list(view)[0][0]

    def _subtypes_of_wildcards(self, node):
        possible_type_args = []
        subtypes = set()
        for t_arg in node.type_args:
            if not t_arg.is_wildcard():
                possible_type_args.append([t_arg])
                continue
            if t_arg.is_invariant():
                possible_type_args.append(self.get_reg_types())
            elif t_arg.is_covariant():
                possible_type_args.append({
                    n for n in self.subtypes(t_arg.bound)
                    if not n.is_type_constructor()})
            else:
                possible_type_args.append({n for n in self.supertypes(
                    t_arg.bound)})
        for combination in itertools.product(*possible_type_args):
            new_sub = node.t_constructor.new(list(combination))
            subtypes.add(new_sub)
            subtypes.update(self.subtypes(new_sub))
        return subtypes

    def subtypes(self, node: tp.Type):
        subtypes = {node}
        if node.is_type_var():
            return subtypes
        if node.is_parameterized() and any(t_arg.is_wildcard()
                                           for t_arg in node.type_args):
            subtypes.update(self._subtypes_of_wildcards(node))
            return subtypes
        if not node.is_parameterized() and not node.is_type_constructor():
            if node not in self.subtyping_graph:
                return subtypes
            subtypes.update(nx.descendants(self.subtyping_graph, node))
            return subtypes

        if node.is_type_constructor():
            # FIXME type constructor subtypes
            return subtypes

        type_var_map = node.get_type_variable_assignments()
        node = node.t_constructor
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
            if v.is_type_constructor():
                handler = self.get_instantiations_of_recursive_bound
                inst_t = tu.instantiate_type_constructor(
                    v, self.get_reg_types(), type_var_map=type_var_map,
                    rec_bound_handler=handler)
                if inst_t:
                    subtypes.add(inst_t[0])
            else:
                subtypes.add(v)
        return subtypes

    def supertypes(self, node: tp.Type):
        reverse_graph = self.subtyping_graph.reverse()
        supertypes = set()
        constraints = {}
        if node.is_parameterized():
            constraints.update(node.get_type_variable_assignments())
            node = node.t_constructor
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
                handler = self.get_instantiations_of_recursive_bound
                supertypes.add(tu.instantiate_type_constructor(
                    v, {}, type_var_map=constraints,
                    rec_bound_handler=handler)[0])
        return supertypes

    def find_API_path(self, target: tp.Type) -> list:
        origin = target
        if target.is_parameterized():
            target = target.t_constructor
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
            constraints = au.collect_constraints(origin, type_variables,
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
                           if i == 0 or not isinstance(n, tp.Type)]
            return pruned_path, assignments
        return None

    def get_instantiations_of_recursive_bound(
            self, type_param: tp.TypeParameter,
            type_var_map: dict,
            types: Set[tp.Type] = None
    ) -> Set[tp.Type]:
        possibles_types = set()
        bound = type_param.bound
        if not bound or not bound.is_parameterized():
            return possibles_types

        subtypes = nx.descendants(self.subtyping_graph, bound.t_constructor)
        for st in subtypes:
            # This is a quick and dirty solution. For every subtype of the
            # given bound, we compute its supertypes, and then we try to
            # find the supertype S that has the same type constructor with
            # the given bound. After performing type unification and compa-
            # ring S with the computed substitution, we decide whether S
            # is a valid instantiation.
            supertype = [t for t in self.supertypes(st)
                         if bound.name == t.name][0]
            sub = tu.unify_types(supertype, bound, self.bt_factory)
            if not sub:
                continue
            sub_names = {k.name: v for k, v in sub.items()}
            bound_found = sub_names[type_param.name]
            reverse = {v: tp.substitute_type(k, type_var_map)
                       for k, v in sub.items()
                       if v.is_type_var()}
            t = st
            if any(v != tp.substitute_type(sub.get(k, k), reverse)
                   for k, v in type_var_map.items()):
                continue
            if st.is_type_constructor():
                t = st.new(st.type_parameters)
            if t == bound_found:
                if st.is_type_constructor():
                    handler = self.get_instantiations_of_recursive_bound
                    sub_t, _ = tu.instantiate_type_constructor(
                        st, types or self.get_reg_types(),
                        type_var_map=reverse,
                        rec_bound_handler=handler
                    )
                else:
                    sub_t = st
                possibles_types.add(sub_t)
        return possibles_types

    def get_functional_type(self, etype: tp.Type):
        if etype.is_parameterized():
            # Check if this the given type is a native function type, e.g.,
            # (Boolean) -> String.
            t_constructor = etype.t_constructor
            if t_constructor == self.bt_factory.get_function_type(
                    len(t_constructor.type_parameters) - 1):
                return etype
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
        if func_type is None:
            return []
        func_type = tp.substitute_type(func_type, type_var_map)
        candidate_functions = []
        for api in self.api_graph.nodes():
            if not isinstance(api, (Method, Constructor)):
                continue
            param_types = [p.box_type() for p in api.parameters]
            view = self.api_graph.out_edges(api)
            assert len(view) == 1
            out_type = list(view)[0][1]
            if out_type.is_type_constructor():
                constraint = self.api_graph[api][out_type].get("constraint",
                                                               {})
                out_type = out_type.new(
                    [constraint.get(tpa, tpa)
                     for tpa in out_type.type_parameters])
            api_type = self.bt_factory.get_function_type(
                len(param_types)).new(param_types + [out_type.box_type()])
            sub = tu.unify_types(func_type, api_type, self.bt_factory,
                                 same_type=True)
            if sub or func_type == api_type:
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
            func_type_parameters = getattr(node, "type_parameters", [])
            if not view:
                receivers = {self.EMPTY}
                if func_type_parameters:
                    type_var_map.update(
                        tu.instantiate_parameterized_function(
                            func_type_parameters, self.get_reg_types()))
            else:
                assert len(view) == 1
                receiver = list(view)[0][0]
                if receiver.is_type_constructor():
                    # TODO Revisit
                    handler = self.get_instantiations_of_recursive_bound
                    inst = tu.instantiate_type_constructor(
                        receiver, self.get_reg_types(),
                        rec_bound_handler=handler
                    )
                    if not inst:
                        # We were unable to instantiate the given type
                        # constructor.
                        continue
                    receiver_t, type_var_map = inst
                    receiver = receiver_t
                    func_type_parameters = [
                        tp.substitute_type(t, type_var_map)
                        for t in func_type_parameters
                    ]
                    if func_type_parameters:
                        type_var_map.update(
                            tu.instantiate_parameterized_function(
                                func_type_parameters, self.get_reg_types()))
                else:
                    if func_type_parameters:
                        type_var_map.update(
                            tu.instantiate_parameterized_function(
                                func_type_parameters, self.get_reg_types()))
                    receiver = tp.substitute_type(receiver, type_var_map)
                receivers = {receiver}
                if receiver != self.bt_factory.get_any_type():
                    receivers.update(self.subtypes(receiver))
            parameters = [{tp.substitute_type(p, type_var_map)}
                          for p in getattr(node, "parameters", [])]
            for param_set in parameters:
                param = list(param_set)[0]
                if param != self.bt_factory.get_any_type():
                    param_set.update(self.subtypes(param))
            if not parameters:
                parameters = ({self.EMPTY},)
            parameters = tuple([frozenset(s) for s in parameters])
            view = self.api_graph.out_edges(node)
            assert len(view) == 1
            ret_type = list(view)[0][1]
            constraint = self.api_graph[node][ret_type].get("constraint", {})
            if constraint:
                ret_type = ret_type.new(
                    [constraint[tpa] for tpa in ret_type.type_parameters]
                )
            ret_type = tp.substitute_type(ret_type, type_var_map)
            ret_types = self.supertypes(ret_type)
            ret_types.add(ret_type)
            encodings.append(APIEncoding(node, frozenset(receivers),
                                         parameters,
                                         frozenset(ret_types),
                                         type_var_map))
        return encodings
