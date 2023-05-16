from collections import OrderedDict, defaultdict
from typing import NamedTuple, List, Set, Dict, Union

import networkx as nx

from src import utils
from src.ir import types as tp, type_utils as tu


class UpperBoundConstraint(NamedTuple):
    bound: tp.Type


class EqualityConstraint(NamedTuple):
    t: tp.Type


Constraint = Union[UpperBoundConstraint, EqualityConstraint]


def compute_assignment_graph(api_graph: nx.DiGraph, path: list) -> OrderedDict:
    assignment_graph = OrderedDict()
    for source, target in path:
        constraint = api_graph[source][target].get("constraint")
        if not constraint:
            continue
        for type_k, type_v in constraint.items():
            sub_t = tp.substitute_type(type_v, assignment_graph,
                                       substitute_bound=False)
            if sub_t.has_type_variables():
                assigned_t = sub_t
            else:
                assigned_t = type_v
            if type_k != assigned_t:
                assignment_graph[type_k] = assigned_t
    return assignment_graph


def build_equality_constraints(
    assignments: dict,
    assignment_graph: dict,
    bt_factory
) -> Dict[tp.TypeParameter, Set[EqualityConstraint]]:
    constraints = defaultdict(set)
    for k, v in assignments.items():
        t = tp.substitute_type(k, assignment_graph, substitute_bound=False)
        if t.has_type_variables():
            sub = tu.unify_types(v, t, bt_factory, same_type=False,
                                 strict_mode=False, subtype_on_left=False)
            if not sub:
                constraints[k].add(EqualityConstraint(v))
                constraints[k].add(EqualityConstraint(t))
                continue
            for k, v in sub.items():
                if not v.is_wildcard():
                    constraints[k].add(EqualityConstraint(v))
                    continue
                if v.bound:
                    constraints[k].add(EqualityConstraint(v.bound))
        else:
            constraints[k].add(EqualityConstraint(v))
            constraints[k].add(EqualityConstraint(t))
    return constraints


def collect_constraints(target: tp.Type,
                        type_variables: List[tp.TypeParameter],
                        assignment_graph: dict,
                        with_constraints: dict = None,
                        bt_factory=None):
    constraints = defaultdict(set)
    if target.is_parameterized():
        # Gather equality constraints that stem from target type (i.e.,
        # type variable assignments of the target paremeterized type).
        eq_constraints = build_equality_constraints(
            target.get_type_variable_assignments(),
            assignment_graph, bt_factory)
        if eq_constraints is None:
            return eq_constraints
        constraints.update(eq_constraints)
    if with_constraints:
        # Gather equality constraints from any other given constraint.
        eq_constraints = build_equality_constraints(with_constraints,
                                                    assignment_graph,
                                                    bt_factory)
        if eq_constraints is None:
            return eq_constraints
        constraints.update(eq_constraints)
    for node in type_variables:
        constraints[node]
        t = tp.substitute_type(node, assignment_graph, substitute_bound=False)
        if t.is_parameterized() and t.has_type_variables():
            if node.bound is None:
                continue
            sub = tu.unify_types(node.bound, t, bt_factory,
                                 same_type=False,
                                 strict_mode=False, subtype_on_left=False)
            if not sub:
                constraints[node].add(EqualityConstraint(node.bound))
                constraints[node].add(EqualityConstraint(t))
                continue
            for k, v in sub.items():
                constraint = (
                    UpperBoundConstraint(node.bound)
                    if t.is_type_var()
                    else (
                        EqualityConstraint(v)
                        if not v.is_wildcard()
                        else EqualityConstraint(v.bound) if v.bound else None
                    )
                )
                if constraint:
                    constraints[k].add(constraint)
        else:
            if t.name != node.name:
                constraints[node].add(EqualityConstraint(t))
            if node.bound:
                constraints[node].add(UpperBoundConstraint(
                    tp.substitute_type(node.bound, assignment_graph,
                                       substitute_bound=False)))

    ordered_constraints = OrderedDict()
    for node in type_variables:
        ordered_constraints[node] = constraints[node]
    return ordered_constraints


def _assign_type_unconstrained(api_graph, type_var,
                               assignment_graph,
                               type_var_assignments):
    # Try to assign variable from the assignment graph
    t = assignment_graph.get(type_var)
    if t is None:
        # It's a free variable. Assign a random type to it.
        if type_var.is_type_constructor():
            t = api_graph.get_matching_type_constructor(type_var)
            print(t, type_var)
        else:
            t = api_graph.get_random_type()
    return {type_var: tp.substitute_type(t, type_var_assignments)}


def _instantiate_type_variable_no_constraints(
    type_var: tp.TypeParameter,
    constraints: Set[Constraint]
) -> tp.Type:
    upper_bounds = [c.bound for c in constraints
                    if isinstance(c, UpperBoundConstraint)]
    eqs = [c.t for c in constraints
           if isinstance(c, EqualityConstraint)]
    if len(eqs) > 1:
        return utils.random.choice(eqs)
    if len(upper_bounds) > 1:
        return utils.random.choice(upper_bounds)
    return utils.random.choice(eqs + upper_bounds)


def merge_type_wildcards(eqs: List[tp.Type]) -> List[tp.Type]:
    bounds = set()
    for eq in eqs:
        if eq.is_wildcard() and eq.bound:
            bounds.add(eq.bound)
        else:
            bounds.add(eq)
    return list(eqs)


def _instantiate_type_variable_with_constraints(
    type_var: tp.TypeParameter,
    constraints: Set[Constraint],
    api_graph
) -> tp.Type:
    upper_bounds = [c.bound for c in constraints
                    if isinstance(c, UpperBoundConstraint)]
    eqs = [c.t for c in constraints
           if isinstance(c, EqualityConstraint)]
    new_bounds = upper_bounds
    if len(upper_bounds) > 2:
        new_bounds = {upper_bounds[0]}
        for bound in set(upper_bounds[1:]):
            supers = api_graph.supertypes(bound)
            if any(s in upper_bounds for s in supers):
                new_bounds.append(bound)
        new_bounds = list(new_bounds)

    # Merge equality constraints of the form {out Integer, Integer}.
    eqs = merge_type_wildcards(eqs)
    if len(new_bounds) > 1 or len(eqs) > 1:
        return None
    if len(eqs) == 1:
        if new_bounds and not eqs[0].is_subtype(new_bounds[0]):
            return None
        if eqs[0].is_primitive():
            return None
        return eqs[0]

    if len(new_bounds) == 1:
        return new_bounds[0]
    return None


def _instantiate_type_variables_unconstrained(api_graph, constraints,
                                              assignment_graph):
    if constraints is None:
        # Unable to build constraints. This means that type unifation failed.
        return None
    type_var_assignments = {}
    for type_var in constraints.keys():
        type_var_constraints = constraints[type_var]
        if not type_var_constraints:
            type_var_assignments.update(_assign_type_unconstrained(
                api_graph, type_var, assignment_graph,
                type_var_assignments))
            continue

        upper_bounds = [c.bound for c in type_var_constraints
                        if isinstance(c, UpperBoundConstraint)]
        eqs = [c.t for c in type_var_constraints
               if isinstance(c, EqualityConstraint)]
        if len(eqs) > 1:
            type_var_assignments[type_var] = utils.random.choice(eqs)
            continue
        if len(upper_bounds) > 1:
            type_var_assignments[type_var] = utils.random.choice(upper_bounds)
            continue
        type_var_assignments[type_var] = utils.random.choice(
            eqs + upper_bounds)
    return type_var_assignments


def instantiate_type_variables(api_graph, constraints,
                               assignment_graph,
                               respect_constraints: bool = True):
    if constraints is None:
        # Unable to build constraints. This means that type unifation failed.
        return None
    type_var_assignments = {}
    for type_var in constraints.keys():
        type_var_constraints = constraints[type_var]
        if not type_var_constraints:
            type_var_assignments.update(_assign_type_unconstrained(
                api_graph, type_var, assignment_graph,
                type_var_assignments))
            continue

        if respect_constraints:
            t = _instantiate_type_variable_with_constraints(
                type_var, type_var_constraints, api_graph)
        else:
            t = _instantiate_type_variable_no_constraints(type_var,
                                                          type_var_constraints)
        if t is None:
            return None
        # An upper bound might depend on other variables. Therefore,
        # substitute all type variable occurences that appear in the upper
        # bound of 'type_var'.
        if type_var.has_recursive_bound():
            # Case 1: recursive bounds
            assigned_t = api_graph.get_instantiations_of_recursive_bound(
                type_var, type_var_assignments, api_graph.get_reg_types())
            if not assigned_t and respect_constraints:
                # We were not able to find a suitable instantiation of
                # this recursive bound. We need to respect the constraints
                # and thus we return None.
                return None
            if not assigned_t:
                # We were not able to find a suitable instantiation of
                # this recursive bound. However, we are in a mode where
                # we are free to disregard constraints. So we pick a random
                # type. TODO: Create an invalid instantiation of the
                # upper bound type.
                assigned_t = api_graph.get_reg_types()
            assigned_t = tu.select_random_type(list(assigned_t), uniform=True)
        else:
            # Case 2: regular bounds
            assigned_t = tp.substitute_type(t, type_var_assignments)
            if assigned_t.is_type_constructor() and not type_var.is_type_constructor():
                assigned_t, _ = tu.instantiate_type_constructor(
                    assigned_t, api_graph.get_reg_types(),
                    rec_bound_handler=api_graph.get_instantiations_of_recursive_bound
                )
        if assigned_t.is_parameterized() and \
                assigned_t.has_invariant_wildcards():
            # We substitute invariant wildcard with concrete type.
            assigned_t = tu.substitute_invariant_wildcard_with(
                assigned_t, [t for t in api_graph.get_reg_types()
                             if not t.is_type_constructor()])
        type_var_assignments[type_var] = assigned_t
    return type_var_assignments


def check_validity_api_parameters(api, type_var_assignments: dict) -> bool:
    """
    Checks whether the parameter types of the API (with the respect) to the
    given type variable assignments are valid (e.g., they are not wildcard
    types).
    """
    for param in getattr(api, "parameters", []):
        param_type = tp.substitute_type(param.t, type_var_assignments)
        if param_type.is_wildcard() and not param_type.is_contravariant():
            return False
    return True
