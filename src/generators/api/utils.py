from collections import OrderedDict, defaultdict
from typing import NamedTuple, List

import networkx as nx

from src.ir import types as tp, type_utils as tu


class UpperBoundConstraint(NamedTuple):
    bound: tp.Type


class EqualityConstraint(NamedTuple):
    t: tp.Type


def compute_assignment_graph(api_graph: nx.DiGraph, path: list) -> OrderedDict:
    assignment_graph = OrderedDict()
    for source, target in path:
        constraint = api_graph[source][target].get("constraint")
        if not constraint:
            continue
        for type_k, type_v in constraint.items():
            sub_t = tp.substitute_type(type_v, assignment_graph)
            if sub_t.has_type_variables():
                assigned_t = sub_t
            else:
                assigned_t = type_v
            if type_k != assigned_t:
                assignment_graph[type_k] = assigned_t
    return assignment_graph


def _collect_constraints_from_target_type(target: tp.Type,
                                          assignment_graph: dict,
                                          bt_factory) -> dict:
    constraints = defaultdict(set)
    if not target.is_parameterized():
        return constraints
    if target.is_parameterized():
        for k, v in target.get_type_variable_assignments().items():
            t = tp.substitute_type(k, assignment_graph)
            if t.has_type_variables():
                sub = tu.unify_types(v, t, bt_factory, same_type=False,
                                     strict_mode=False)
                if not sub:
                    return None
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
                        bt_factory=None):
    constraints = _collect_constraints_from_target_type(target,
                                                        assignment_graph,
                                                        bt_factory)
    if constraints is None:
        return constraints
    for node in type_variables:
        constraints[node]
        t = tp.substitute_type(node, assignment_graph)
        if t.has_type_variables():
            if node.bound is None:
                continue
            sub = tu.unify_types(node.bound, t, bt_factory,
                                 same_type=False,
                                 strict_mode=False)
            if not sub:
                return None
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
            constraints[node].add(EqualityConstraint(t))
            if node.bound:
                constraints[node].add(UpperBoundConstraint(
                    tp.substitute_type(node.bound, assignment_graph)))

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
        t = api_graph.get_random_type()
    return {type_var: tp.substitute_type(t, type_var_assignments)}


def instantiate_type_variables(api_graph, constraints,
                               assignment_graph):
    if constraints is None:
        # Unable to build constraints. This means that type unifation failed.
        return None
    type_var_assignments = {}
    free_variables = {
        k
        for k in constraints.keys()
        if k not in assignment_graph
    }
    for type_var in list(free_variables) + list(assignment_graph.keys()):
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
            return None
        if len(eqs) == 1:
            type_var_assignments[type_var] = eqs[0]
            continue

        if len(upper_bounds) > 1:
            type_var_assignments[type_var] = upper_bounds[0]
            continue

        new_bounds = set()

        for bound in set(upper_bounds):
            supers = api_graph.supertypes(bound)
            if any(s.t in upper_bounds for s in supers):
                new_bounds.append(bound)
        if len(new_bounds) > 1:
            return None
        if len(new_bounds) == 1:
            type_var_assignments[type_var] = new_bounds[0]
        return None

    return type_var_assignments
