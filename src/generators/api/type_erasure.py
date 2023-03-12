from collections import defaultdict
from typing import Iterable, Dict, Set, List

from src.ir import types as tp, type_utils as tu, ast
from src.ir.builtins import BuiltinFactory
from src.generators.api import api_graph as ag


def get_type_variables(t: tp.Type,
                       bt_factory: BuiltinFactory) -> Iterable[tp.TypeParameter]:
    if t.is_type_var():
        return [t]
    if t.is_wildcard() or t.is_parameterized():
        return t.get_type_variables(bt_factory).keys()
    return []


def get_arg_api(arg):
    if isinstance(arg.expr, ast.Lambda):
        # The argument is a lambda expression. We need its signature.
        return arg.expr.signature
    return arg.path[-2]


class TypeEraser():
    OUT = -1

    def __init__(self, api_graph: ag.APIGraph, expected_type: tp.Type,
                 bt_factory: BuiltinFactory):
        self.api_graph = api_graph
        self.expected_type = expected_type
        self.bt_factory = bt_factory

    def get_api_output_type(self, api: ag.APINode) -> tp.Type:
        if isinstance(api, tp.Type):
            # Fill parameterized type with type parameters.
            new_type_args = api.t_constructor.type_parameters
            return self.bt_factory.get_function_type(
                len(new_type_args) - 1).new(new_type_args)
        return self.api_graph.get_concrete_output_type(api)

    def get_type_parameters(self, api: ag.APINode) -> List[tp.TypeParameter]:
        if isinstance(api, ag.Constructor):
            t = self.api_graph.get_type_by_name(api.get_class_name())
            if t.is_type_constructor():
                return t.type_parameters
            else:
                return []
        if isinstance(api, tp.Type):
            # In case of lambda we exclude the last type parameter which can
            # be inferred by its body.
            return api.t_constructor.type_parameters[:-1]
        return api.type_parameters

    def compute_markings(self,
                         api: ag.APINode) -> Dict[tp.TypeParameter, Set[int]]:
        markings = defaultdict(set)
        ret_type = self.get_api_output_type(api)
        for type_param in self.get_type_parameters(api):
            if isinstance(api, (ag.Constructor, tp.Type)):
                # All type parameters of a constructor or a function type are
                # in out position.
                markings[type_param].add(self.OUT)
            else:
                # Check the return type of polymorphic function.
                type_variables = get_type_variables(ret_type, self.bt_factory)
                if type_param in type_variables:
                    markings[type_param].add(self.OUT)

            for i, param in enumerate(getattr(api, "parameters", [])):
                type_variables = get_type_variables(param.t, self.bt_factory)
                if type_param in type_variables:
                    markings[type_param].add(i)
        return markings

    def can_infer_out_position(self, type_param: tp.TypeParameter,
                               marks: Set[int], api_out_type: tp.Type) -> bool:
        if self.OUT not in marks or self.expected_type is None:
            return False
        return self.expected_type == api_out_type or bool(
            tu.unify_types(self.expected_type, api_out_type, self.bt_factory,
                           same_type=False, subtype_on_left=False))

    def can_infer_in_position(self, type_param: tp.TypeParameter,
                              marks: Set[int], api_params: List[tp.Type],
                              api_args: List[ag.APIPath]) -> bool:
        can_infer = False
        for mark in marks.difference({self.OUT}):
            arg = api_args[mark]
            if len(arg.path) == 1 and not isinstance(arg.expr, ast.Lambda):
                # This means that we have a concrete type.
                return True

            arg_api = get_arg_api(arg)
            type_parameters = self.get_type_parameters(arg_api)
            if not type_parameters:
                # The argument is not a polymorphic call. We can infer
                # the argument type without a problem.
                return True

            arg_type = self.get_api_output_type(arg_api)
            type_variables = get_type_variables(arg_type, self.bt_factory)
            method_type_params = {
                tpa for tpa in type_parameters
                if tpa in type_variables
            }
            expected_param_type = \
                self.api_graph.get_functional_type_instantiated(
                    api_params[mark].t) or api_params[mark].t
            sub = tu.unify_types(expected_param_type, arg_type,
                                 self.bt_factory, same_type=False)
            if not sub:
                continue
            for mtpa in method_type_params:
                if any(mtpa in get_type_variables(p.t, self.bt_factory)
                       for p in getattr(arg_api, "parameters", [])):
                    # Type variable of API is in "in" position.
                    continue
                if not sub[mtpa].is_type_var():
                    can_infer = True
        return can_infer

    def erase_types(self, expr: ast.Expr, api: ag.APINode,
                    args: List[ag.APIPath]):
        markings = self.compute_markings(api)
        omittable_type_params = set()
        ret_type = self.get_api_output_type(api)
        for type_param, marks in markings.items():
            if self.can_infer_out_position(type_param, marks, ret_type):
                omittable_type_params.add(type_param)
                continue
            if self.can_infer_in_position(type_param, marks,
                                          getattr(api, "parameters", []),
                                          args):
                omittable_type_params.add(type_param)
        if len(omittable_type_params) == len(self.get_type_parameters(api)):
            expr.omit_types()
