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
                assignment_graph[type_k] = sub_t
            else:
                assignment_graph[type_k] = type_v
    return assignment_graph


def _collect_constraints_from_target_type(target: tp.Type,
                                          assignment_graph: dict) -> dict:
    constraints = defaultdict(set)
    if not target.is_parameterized():
        return constraints
    if target.is_parameterized():
        for k, v in target.get_type_variable_assignments().items():
            t = tp.substitute_type(k, assignment_graph)
            if t.has_type_variables():
                sub = tu.unify_types(v, t, None, same_type=False,
                                     strict_mode=False)
                if not sub:
                    return None
                for k, v in sub.items():
                    constraints[k].add(EqualityConstraint(v))
            else:
                constraints[k].add(EqualityConstraint(v))
                constraints[k].add(EqualityConstraint(t))
    return constraints


def collect_constraints(target: tp.Type,
                        type_variables: List[tp.TypeParameter],
                        assignment_graph: dict):
    constraints = _collect_constraints_from_target_type(target,
                                                        assignment_graph)
    if constraints is None:
        return constraints
    for node in type_variables:
        constraints[node]
        t = tp.substitute_type(node, assignment_graph)
        if t.has_type_variables():
            if node.bound is None:
                continue
            sub = tu.unify_types(node.bound, t, None, same_type=False,
                                 strict_mode=False)
            if not sub:
                return None
            for k, v in sub.items():
                constraint = (
                    UpperBoundConstraint(node.bound)
                    if t.is_type_var()
                    else EqualityConstraint(v)
                )
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
