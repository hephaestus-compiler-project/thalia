from collections import OrderedDict
import itertools
from typing import NamedTuple, List, Union, Set, Dict, Tuple

import networkx as nx

from src import utils
from src.ir import types as tp, type_utils as tu
from src.generators.config import cfg
from src.generators.api import utils as au
from src.generators.api.matcher import Matcher


IN = 0
OUT = 1
WIDENING = 2
PROTECTED = "protected"


class Field(NamedTuple):
    name: str
    cls: str

    def __str__(self):
        return self.get_class_name() + "." + self.get_name()

    def __hash__(self):
        return hash((self.name, self.cls))

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


class Variable(NamedTuple):
    name: str

    def __str__(self):
        return self.get_name()

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.name == other.name)

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def api_name(self):
        return self.get_name()


class Parameter(NamedTuple):
    t: tp.Type
    variable: bool

    def __str__(self):
        return "{t!s}{suffix!s}".format(
            t=str(self.t),
            suffix="*" if self.variable else ""
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.t, self.variable))


class Method(NamedTuple):
    name: str
    cls: str
    parameters: List[Parameter]
    type_parameters: List[tp.TypeParameter]

    def __str__(self):
        type_parameters_str = ""
        if self.type_parameters:
            type_parameters_str = "<{}>".format(",".join(
                [str(tpa) for tpa in self.type_parameters]))
        return "{cls!s}.{type_params!s}{name!s}({args!s})".format(
            cls=self.get_class_name(),
            type_params=type_parameters_str,
            name=self.get_name(),
            args=", ".join(str(p) for p in self.parameters)
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.name, self.cls, tuple(self.parameters),
                     tuple(self.type_parameters)))

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
    parameters: List[Parameter]

    def __str__(self):
        return "{cls!s}.{name!s}({args!s})".format(
            cls=self.get_class_name(),
            name=self.get_name(),
            args=", ".join(str(p) for p in self.parameters)
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.name, tuple(self.parameters)))

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


APINode = Union[Field, Method, Constructor, tp.Type, Variable]
APIPath = List[APINode]


class APIEncoding(NamedTuple):
    api: APINode
    receivers: Set[tp.Type]
    parameters: Set[tp.Type]
    returns: Set[tp.Type]
    type_var_map: dict
    type_parameters: List[tp.TypeParameter]


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
    EMPTY = 0

    def __init__(self, api_graph, subtyping_graph, functional_types,
                 bt_factory, **kwargs):
        self.api_graph: nx.DiGraph = api_graph
        self.subtyping_graph: nx.DiGraph = subtyping_graph
        self.functional_types: Dict[tp.Type, tp.ParameterizedType] = \
            functional_types
        self.bt_factory = bt_factory
        self._all_types = {node.name: node
                           for node in self.subtyping_graph.nodes()}
        self.source_nodes_of = {}
        self.disable_bounded_type_parameters = kwargs.get(
            "disable_bounded_type_parameters", False)

    def get_reg_types(self):
        types = [
            t
            for t in self.subtyping_graph.nodes()
            if (
                not (t.is_parameterized() and t.has_type_variables()) and
                not (t.name == self.bt_factory.get_void_type().name and
                     getattr(t, "primive", False))
            )
        ]
        return types

    def get_random_type(self):
        types = self.get_reg_types()
        t = tu.select_random_type(types)
        if t.is_type_constructor():
            inst = tu.instantiate_type_constructor(
                t, types, only_regular=True,
                rec_bound_handler=self.get_instantiations_of_recursive_bound)
            return inst[0]
        return t

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
            if type_v.is_type_var():
                type_var_map[type_v] = assignment
        return type_var_map

    def subtypes_of_parameterized(self, node):
        possible_type_args = []
        subtypes = set()
        for i, t_arg in enumerate(node.type_args):
            type_param = node.t_constructor.type_parameters[i]
            # Type argument not wildcard, type parameter invariant
            if not t_arg.is_wildcard() and type_param.is_invariant():
                possible_type_args.append([t_arg])
                continue

            # Type argument invariant
            if t_arg.is_wildcard() and t_arg.is_invariant():
                possible_type_args.append(
                    [t for t in self.get_reg_types()
                     if not t.is_type_constructor()])

            # Type argument covariant or type param covariant
            elif (t_arg.is_wildcard() and t_arg.is_covariant() or
                  type_param.is_covariant()):
                possible_type_args.append({
                    n for n in self.subtypes(getattr(t_arg, "bound", t_arg) or t_arg)
                    if not n.is_type_constructor()})
            # Type argument contravariant or type param contravariant
            else:
                possible_type_args.append({n for n in self.supertypes(
                    getattr(t_arg, "bound", t_arg) or t_arg)})
        for combination in itertools.product(*possible_type_args):
            t_constructor = self.get_type_by_name(
                node.name) or node.t_constructor
            new_sub = t_constructor.new(list(combination))
            subtypes.add(new_sub)
            subtypes.update(self.subtypes_of_parameterized_inheritance(
                new_sub))
        return subtypes

    def subtypes_of_parameterized_inheritance(
            self, node: tp.ParameterizedType) -> Set[tp.Type]:
        assert node.is_parameterized()

        subtypes = set()
        type_var_map = node.get_type_variable_assignments()
        node = self.get_type_by_name(node.name) or node.t_constructor
        if node not in self.subtyping_graph:
            return subtypes

        excluded_nodes = set()
        for k, v in nx.dfs_edges(self.subtyping_graph, node):
            if k in excluded_nodes:
                # Type k has been excluded, so due to transitivity, we also
                # exclude type v.
                excluded_nodes.add(v)
                continue
            constraint = self.subtyping_graph[k][v].get("constraint") or {}
            if not constraint:
                subtypes.add(v)
            solution = self.solve_constraint(constraint,
                                             dict(type_var_map))
            if not solution:
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

    def subtypes(self, node: tp.Type, include_self=True):
        subtypes = {node} if include_self else set()
        if node.is_type_var():
            return subtypes
        if node.is_parameterized() and any(
                t_arg.is_wildcard() or
                not node.t_constructor.type_parameters[i].is_invariant()
                for i, t_arg in enumerate(node.type_args)
        ):
            # Here the parameterized type either contains wildcards or the
            # type is derived from non-invariant type parameters.
            subtypes.update(self.subtypes_of_parameterized(node))
            return subtypes

        # Subtypes of simple classifiers.
        if not node.is_parameterized() and not node.is_type_constructor():
            if node not in self.subtyping_graph:
                return subtypes
            subtypes.update(nx.descendants(self.subtyping_graph, node))
            return subtypes

        if node.is_type_constructor():
            # FIXME type constructor subtypes
            return subtypes

        subtypes.update(self.subtypes_of_parameterized_inheritance(node))
        return subtypes

    def supertypes(self, node: tp.Type):
        reverse_graph = self.subtyping_graph.reverse()
        supertypes = set()
        constraints = {}
        if node.is_parameterized():
            constraints.update(node.get_type_variable_assignments())
            node = self.get_type_by_name(node.name) or node.t_constructor
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
                if t.is_wildcard():
                    if type_k.is_covariant() and t.is_contravariant():
                        t = t.bound
                    if type_k.is_contravariant() and t.is_covariant():
                        t = t.bound
                constraints[type_k] = t
            handler = self.get_instantiations_of_recursive_bound
            supertypes.add(tu.instantiate_type_constructor(
                v, {}, type_var_map=constraints,
                rec_bound_handler=handler)[0])
        return supertypes

    def add_variable_node(self, name: str, var_type: tp.Type):
        source = Variable(name)
        kwargs = {}
        target = var_type
        if var_type.is_parameterized():
            kwargs["constraint"] = var_type \
                .get_type_variable_assignments()
            target = self.get_type_by_name(var_type.name) or var_type
        self.api_graph.add_node(source)
        self.api_graph.add_node(target)
        self.api_graph.add_edge(source, target, **kwargs)

    def remove_variable_node(self, name: str):
        self.api_graph.remove_node(Variable(name))

    def add_types(self, nodes: List[tp.Type]):
        self.subtyping_graph.add_nodes_from(nodes)

    def remove_types(self, nodes: List[tp.Type]):
        self.subtyping_graph.remove_nodes_from(nodes)

    def get_sources_and_target(
            self, target: tp.Type,
            target_selection: str) -> (List[APINode], APINode):
        if target_selection not in ["concrete", "abstract", "all"]:
            msg = ("Target selection must be either one of 'concrete', "
                   "'abstract' and 'all', not {sel!r}")
            msg = msg.format(sel=target_selection)
            return Exception(msg)
        origin = target
        targets = []
        if target.is_parameterized():
            is_primitive = (
                origin.t_constructor == self.bt_factory.get_array_type() and
                origin.type_args[0].is_primitive()
            )
            target = (
                origin if is_primitive
                else self.get_type_by_name(target.name) or target.t_constructor
            )
        if target not in self.api_graph:
            target_selection = "abstract"
        if target_selection in ["all", "concrete"] or \
                target.is_type_constructor():
            targets.append(target)
        if target_selection in ["all", "abstract"]:
            # If this option is not enabled we also consider APIs that return
            # a type variable as targets.
            targets.extend(n for n in self.api_graph.nodes()
                           if isinstance(n, tp.TypeParameter)
                           and (not n.bound or origin.is_subtype(n.bound)))
        # Pick a random target
        target = utils.random.choice(targets)

        # Find all source nodes that reach the selected target.
        source_nodes = self.source_nodes_of.get(target)
        if source_nodes is None:
            source_nodes = [
                node
                for node, indegree in self.api_graph.in_degree(
                    self.api_graph.nodes())
                if indegree == 0 and nx.has_path(self.api_graph, node, target)
            ]
            self.source_nodes_of[target] = [s for s in source_nodes
                                            if not isinstance(s, Variable)]
        return source_nodes, target

    def find_API_path(self, target: tp.Type,
                      with_constraints: dict = None,
                      target_selection: str = "concrete",
                      infeasible: bool = False) -> (APIPath, dict, dict):
        origin = target
        source_nodes, target = self.get_sources_and_target(target,
                                                           target_selection)
        if target is None:
            return None

        with_constraints = with_constraints or {}
        if target.is_type_var():
            with_constraints[target] = origin.box_type()

        for source in utils.random.shuffle(source_nodes):
            if source == target:
                continue
            paths = nx.shortest_simple_paths(self.api_graph, source=source,
                                             target=target)
            for path in sorted(paths, key=len, reverse=True):
                node_path = path
                path = list(zip(path, path[1:]))
                assignment_graph = au.compute_assignment_graph(self.api_graph,
                                                               path)
                type_variables = _get_type_variables(path)
                constraints = au.collect_constraints(origin, type_variables,
                                                     assignment_graph,
                                                     with_constraints or {},
                                                     self.bt_factory)
                assignments = au.instantiate_type_variables(self, constraints,
                                                            assignment_graph)
                if not infeasible and assignments is not None:
                    if not au.check_validity_api_parameters(node_path[-2],
                                                            assignments):
                        return None
                    return node_path, assignments, assignment_graph
                elif infeasible and assignments is None:
                    assignments = au.instantiate_type_variables(
                        self, constraints, assignment_graph,
                        respect_constraints=False
                    )
                    assert assignments is not None
                    assignments = {
                        k: (v if v != tp.WildCardType()
                            else self.bt_factory.get_any_type())
                        for k, v in assignments.items()
                    }
                    if target.is_type_var():
                        assignments[target] = tu.find_irrelevant_type(
                            origin.box_type(), self.get_reg_types(),
                            self.bt_factory)
                    return node_path, assignments, assignment_graph

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

        t_constructor = self.get_type_by_name(
            bound.name) or bound.t_constructor
        if t_constructor not in self.subtyping_graph:
            return possibles_types

        subtypes = nx.descendants(self.subtyping_graph, t_constructor)
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
            for k, v in type_var_map.items():
                sub_t = tp.substitute_type(sub.get(k, v), reverse)
                if v != sub_t or not v.is_subtype(sub_t):
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

    def get_functional_type(self, etype: tp.Type) -> tp.ParameterizedType:
        if etype.is_parameterized():
            # Check if this the given type is a native function type, e.g.,
            # (Boolean) -> String.
            t_constructor = self.get_type_by_name(
                etype.name) or etype.t_constructor
            if t_constructor == self.bt_factory.get_function_type(
                    len(t_constructor.type_parameters) - 1):
                return etype
        class_type = etype
        if etype.is_parameterized():
            class_type = self.get_type_by_name(
                etype.name) or etype.t_constructor
        return self.functional_types.get(class_type)

    def get_functional_type_instantiated(
            self, etype: tp.Type) -> tp.ParameterizedType:
        type_var_map = {}
        if etype.is_parameterized():
            etype = etype.to_variance_free()
            type_var_map = etype.get_type_variable_assignments()
        func_type = self.get_functional_type(etype)
        if func_type is None:
            return None
        return tp.substitute_type(func_type, type_var_map)

    def get_function_refs_of(self, etype: tp.Type) -> List[Tuple[Method, dict]]:
        func_type = self.get_functional_type_instantiated(etype)
        if func_type is None:
            return []
        candidate_functions = []
        for api in self.api_graph.nodes():
            if not isinstance(api, (Method, Constructor)):
                continue
            param_types = [
                (
                    self.bt_factory.get_array_type().new([param.t.box_type()])
                    if param.variable
                    else param.t.box_type()
                )
                for param in api.parameters
            ]
            view = self.api_graph.out_edges(api)
            assert len(view) == 1
            out_type = list(view)[0][1]
            if out_type.is_type_constructor():
                constraint = self.api_graph[api][out_type].get("constraint",
                                                               {})
                out_type = out_type.new(
                    [constraint.get(tpa, tpa)
                     for tpa in out_type.type_parameters])
            if out_type != self.bt_factory.get_void_type():
                out_type = out_type.box_type()
            api_type = self.bt_factory.get_function_type(
                len(param_types)).new(param_types + [out_type])
            sub = tu.unify_types(func_type, api_type, self.bt_factory,
                                 same_type=True)
            if any(v == self.bt_factory.get_void_type()
                   for v in sub.values()):
                # We don't want to match something that is needed to be
                # instantiated with void, e.g.,
                # Consumer<Int> != Function<Int, void>
                continue
            if sub or func_type == api_type:
                candidate_functions.append((api, sub))
        return candidate_functions

    def instantiate_func_type_variables(self, api_node, func_type_parameters):
        if func_type_parameters:
            handler = self.get_instantiations_of_recursive_bound
            func_type_var_map = tu.instantiate_parameterized_function(
                    func_type_parameters, self.get_reg_types(),
                    rec_bound_handler=handler)
            if not func_type_var_map:
                return None
            return func_type_var_map
        return {}

    def generate_type_params(self):
        blacklist = []
        for i in range(cfg.limits.max_type_params):
            bound = None
            if utils.random.bool(cfg.prob.bounded_type_parameters):
                # Add a bound to the generated type parameter
                bound = self.get_random_type().box_type()
                source = bound
                kwargs = {}
                if bound.is_parameterized():
                    kwargs["constraint"] = \
                        bound.get_type_variable_assignments()
                    source = self.get_type_by_name(bound.name)
            type_param = tp.TypeParameter(utils.random.caps(
                blacklist=blacklist), bound=bound)
            blacklist.append(type_param.name)
            self.subtyping_graph.add_node(type_param)
            if bound:
                # Capture subtyping relationship in the subtyping graph.
                self.subtyping_graph.add_edge(source, type_param, **kwargs)

    def get_type_parameters(self):
        return [t for t in self.get_reg_types() if t.is_type_var()]

    def instantiate_receiver_type(self, receiver: tp.Type):
        type_var_map = {}
        outer_type = self.api_graph.nodes[receiver].get("outer_class")
        if outer_type:
            ret = self.instantiate_receiver_type(outer_type)
            if ret is None:
                return None
            _, type_var_map = ret
        if receiver.is_type_constructor():
            handler = self.get_instantiations_of_recursive_bound
            inst = tu.instantiate_type_constructor(
                receiver, self.get_reg_types(),
                rec_bound_handler=handler
            )
            if not inst:
                # We were unable to instantiate the given type
                # constructor.
                return None
            type_var_map.update(inst[1])
            return inst[0], type_var_map
        else:
            return receiver, type_var_map

    def encode_receiver(self, api_node):
        type_var_map = {}
        func_type_parameters = getattr(api_node, "type_parameters", [])
        receiver = self.get_input_type(api_node)
        if not receiver:
            # API is not associated with a receiver
            receivers = {self.EMPTY}
            if isinstance(api_node, Constructor):
                # If the API is a constructor, we treat it as a
                # parameterized function.
                func_type_parameters = getattr(self.get_type_by_name(
                    api_node.get_class_name()), "type_parameters", [])
            func_type_var_map = self.instantiate_func_type_variables(
                api_node, func_type_parameters)
            if func_type_var_map is None:
                return None
            type_var_map.update(func_type_var_map)
        else:
            # Check if receiver is a concrete type rather than a type
            # constructor, e.g., fun <T> Array<T>.all()
            parameterized_rec = receiver.is_parameterized()
            ret = self.instantiate_receiver_type(receiver)
            if ret is None:
                return None
            receiver, rec_var_map = ret
            type_var_map.update(rec_var_map)
            func_type_parameters = [
                tp.substitute_type(t, type_var_map)
                for t in func_type_parameters
            ]
            func_type_var_map = self.instantiate_func_type_variables(
                api_node, func_type_parameters)
            if func_type_var_map is None:
                return None
            type_var_map.update(func_type_var_map)
            if parameterized_rec:
                receiver = tp.substitute_type(receiver, type_var_map)
            receivers = {receiver}
            if receiver != self.bt_factory.get_any_type():
                include_self = not (receiver.is_parameterized() and
                                    receiver.has_wildcards())
                receivers.update(self.subtypes(receiver, include_self))
        return receivers, type_var_map

    def get_input_type(self, api) -> tp.Type:
        view = self.api_graph.in_edges(api)
        if not view:
            return None
        assert len(view) == 1
        return list(view)[0][0]

    def get_output_type(self, api) -> tp.Type:
        view = self.api_graph.out_edges(api)
        if not view:
            return None
        assert len(view) == 1
        return list(view)[0][1]

    def get_concrete_output_type(self, api):
        out_type = self.get_output_type(api)
        if isinstance(api, Constructor):
            if out_type.is_type_constructor():
                return out_type.new(out_type.type_parameters)
            else:
                return out_type

        constraint = self.api_graph[api][out_type].get("constraint")
        if constraint:
            out_type = out_type.new([constraint[tpa]
                                     for tpa in out_type.type_parameters])
        return out_type

    def encode_api_components(self,
                              matcher: Matcher = None) -> List[APIEncoding]:
        api_components = (Field, Constructor, Method)
        api_nodes = [
            n
            for n in self.api_graph.nodes()
            if isinstance(n, api_components)
        ]
        encodings = []
        for node in api_nodes:
            if matcher and not matcher.match(node):
                continue
            self.generate_type_params()
            ret = self.encode_receiver(node)
            if ret is None:
                self.remove_types(self.get_type_parameters())
                continue
            receivers, type_var_map = ret
            parameters = [{tp.substitute_type(p.t, type_var_map)}
                          for p in getattr(node, "parameters", [])]
            for param_set in parameters:
                param = list(param_set)[0]
                if param != self.bt_factory.get_any_type():
                    param_set.update(self.subtypes(param))
            if not parameters:
                parameters = ({self.EMPTY},)
            parameters = tuple([frozenset(s) for s in parameters])
            ret_type = self.get_output_type(node)
            constraint = self.api_graph[node][ret_type].get("constraint", {})
            if constraint:
                ret_type = ret_type.new(
                    [constraint[tpa] for tpa in ret_type.type_parameters]
                )
            if ret_type.is_type_constructor():
                ret_type = ret_type.new(ret_type.type_parameters)
            ret_type = tp.substitute_type(ret_type, type_var_map)
            ret_types = set(tu.find_supertypes(ret_type, self.get_reg_types(),
                                               concrete_only=True))
            ret_types.add(ret_type)
            encodings.append(APIEncoding(node, frozenset(receivers),
                                         parameters,
                                         frozenset(ret_types),
                                         type_var_map,
                                         self.get_type_parameters()))
            self.remove_types(self.get_type_parameters())
        return encodings
