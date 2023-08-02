from collections import defaultdict
from typing import Dict, Set, List

from src.ir import types as tp, type_utils as tu, ast
from src.ir.builtins import BuiltinFactory
from src.generators.api import api_graph as ag, utils as au


def get_arg_api(arg):
    if isinstance(arg.expr, ast.Lambda):
        # The argument is a lambda expression. We need its signature.
        return arg.expr.signature
    return arg.path[-2]


class TypeEraser():
    OUT = -1

    def __init__(self, api_graph: ag.APIGraph,
                 bt_factory: BuiltinFactory,
                 inject_error_mode: bool):
        self.api_graph = api_graph
        self.bt_factory = bt_factory
        self.inject_error_mode = inject_error_mode
        # This is used for maintaining a stack of expected types used for
        # determining the expected types of the generated expressions.
        # This is used for type erasure.
        self.expected_types = []

    @property
    def expected_type(self):
        if not self.expected_types:
            return None
        return self.expected_types[-1]

    def with_target(self, target_type, type_variables=None):
        self.expected_types.append((target_type, type_variables or []))

    def reset_target_type(self):
        if self.expected_types:
            self.expected_types = self.expected_types[:-1]

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
        if isinstance(api, ag.Method):
            return api.type_parameters
        return []

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
                type_variables = tu.get_type_variables_of_type(ret_type)
                if type_param in type_variables:
                    markings[type_param].add(self.OUT)

            for i, param in enumerate(getattr(api, "parameters", [])):
                type_variables = tu.get_type_variables_of_type(param.t)
                if type_param in type_variables:
                    markings[type_param].add(i)
        return markings

    def can_infer_out_position(self, type_param: tp.TypeParameter,
                               marks: Set[int], api_out_type: tp.Type) -> bool:
        target_type, type_vars = self.expected_type
        if self.OUT not in marks or target_type is None:
            return False

        if marks == {self.OUT} and self.inject_error_mode:
            return False

        return target_type == api_out_type or bool(
            tu.unify_types(target_type, api_out_type, self.bt_factory,
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
            type_variables = tu.get_type_variables_of_type(arg_type)
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
                if any(mtpa in tu.get_type_variables_of_type(p.t)
                       for p in getattr(arg_api, "parameters", [])):
                    # Type variable of API is in "in" position.
                    can_infer = True
                    continue
                if not sub[mtpa].is_type_var():
                    can_infer = True
        return can_infer

    def erase_var_type(self, var_decl, expr_res):
        def get_expr_type(expr_res):
            expr_type = expr_res.path[-1]
            if expr_type.is_type_constructor():
                return expr_type.new([expr_res.type_var_map[tpa]
                                      for tpa in expr_type.type_parameters])
            return tp.substitute_type(expr_type, expr_res.type_var_map)

        if (self.inject_error_mode and
                var_decl.get_type().is_parameterized() and
                var_decl.get_type().has_wildcards()):
            return

        expr = expr_res.expr
        if isinstance(expr, (ast.Lambda, ast.FunctionReference)):
            # We don't erase the target type of lambdas and function
            # references
            return

        path = expr_res.path
        expr_type = get_expr_type(expr_res)
        if expr_type.name != var_decl.get_type().name:
            # The type of the expression has a different type from the
            # explicit type of the variable. We are conservative; we cannot
            # erase.
            return

        if len(path) == 1:
            var_decl.omit_type()
            return

        api = get_arg_api(expr_res)
        type_parameters = self.get_type_parameters(api)
        if not type_parameters:
            # The API is not polymorphic, so we are free to omit the variable
            # type.
            var_decl.omit_type()
            return

        # Now, check if the output type of the API contains type variables
        # defined inside API, e.g., fun <T> m(): T
        expr_type = self.get_api_output_type(api)
        type_vars = tu.get_type_variables_of_type(expr_type)
        api_type_params = {
            tpa for tpa in type_parameters
            if tpa in type_vars
        }
        if not api_type_params or all(
                tpa in tu.get_type_variables_of_type(p.t)
                for tpa in api_type_params
                for p in getattr(api, "parameters", [])):
            var_decl.omit_type()

    def erase_types(self, expr: ast.Expr, api: ag.APINode,
                    args: List[ag.APIPath]):
        if isinstance(api, (ag.Method, ag.Constructor)):
            # Checks whether erasing type arguments from polymorphic call
            # creates ambiguity issues.
            overloaded_methods = self.api_graph.get_overloaded_methods(
                self.api_graph.get_input_type(api), api)
            typing_seq = [p.path[-1] for p in args]
            if any(au.is_typing_seq_ambiguous(api, m, typing_seq)
                   for m, _ in overloaded_methods):
                return

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
