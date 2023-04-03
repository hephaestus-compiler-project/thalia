from copy import deepcopy, copy
import functools
import itertools
from typing import List, NamedTuple, Union, Iterable

from src import utils
from src.ir import ast, types as tp, type_utils as tu
from src.ir.context import Context
from src.generators import generators as gens, utils as gu, Generator
from src.generators.api import (api_graph as ag, builder, matcher as match,
                                type_erasure as te)
from src.generators.config import cfg
from src.modules.logging import log
from src.translators import TRANSLATORS


def get_type_variables(t: tp.Type, bt_factory) -> Iterable[tp.TypeParameter]:
    if t.is_type_var():
        return [t]
    if t.is_wildcard() or t.is_parameterized():
        return t.get_type_variables(bt_factory).keys()
    return []


class ExprRes(NamedTuple):
    expr: ast.Expr
    type_var_map: dict
    path: list

    def __hash__(self):
        return hash(str(self.expr) + str(self.type_var_map) +
                    str(self.path) + str(self.assignment_graph))


class APIGenerator(Generator):
    API_GRAPH_BUILDERS = {
        "java": builder.JavaAPIGraphBuilder,
        "kotlin": builder.KotlinAPIGraphBuilder,
        "groovy": builder.JavaAPIGraphBuilder,
        "scala": builder.ScalaAPIGraphBuilder,
    }

    def __init__(self, api_docs, options={}, language=None, logger=None):
        super().__init__(language=language, logger=logger)
        self.logger.update_filename("api-generator")
        self.api_graph = self.API_GRAPH_BUILDERS[language](
            language, **options).build(api_docs)
        api_rules_file = options.get("api-rules")
        kwargs = {}
        if api_rules_file:
            kwargs["matcher"] = match.parse_rule_file(api_rules_file)
        self.encodings = self.api_graph.encode_api_components(**kwargs)
        self.visited = set()
        self.visited_exprs = {}
        self.programs_gen = self.compute_programs()
        self._has_next = True

        self.inject_error_mode = options.get("inject-type-error", False)
        self.type_erasure_mode = options.get("erase-types", False)
        self.start_index = options.get("start-index", 0)
        self.max_conditional_depth = options.get("max-conditional-depth", 4)

        self.translator = TRANSLATORS[language]()
        self.type_eraser: te.TypeEraser = te.TypeEraser(self.api_graph,
                                                        self.bt_factory)
        self.error_injected = None
        self.test_case_type_params: List[tp.TypeParameter] = []

    def produce_test_case(self, expr: ast.Expr,
                          type_parameters) -> ast.Program:
        func_name = "test"
        decls = list(self.context.get_declarations(
            self.namespace, True).values())
        decls = [d for d in decls
                 if not isinstance(d, ast.ParameterDeclaration)]
        body = decls + ([expr] if expr else [])
        type_parameters = list(type_parameters)
        type_parameters.extend(self.test_case_type_params)
        main_func = ast.FunctionDeclaration(
            func_name,
            params=[],
            type_parameters=type_parameters,
            ret_type=self.bt_factory.get_void_type(),
            body=ast.Block(body),
            func_type=ast.FunctionDeclaration.FUNCTION)
        self._add_node_to_parent(self.namespace[:-1], main_func)
        return ast.Program(deepcopy(self.context), self.language)

    def log_program_info(self, program_id, api, receivers, parameters,
                         return_type, type_var_map):
        def to_str(t):
            if isinstance(t, int):
                return str(t)
            return self.translator.get_type_name(t)

        def log_types(types):
            if len(types) == 1:
                return to_str(types[0])
            return "Union[{}]".format(", ".join(to_str(t) for t in types))

        msg = "Generated program {id!s}\n".format(id=program_id)
        msg += "\tAPI: {api!r}\n".format(api=api)
        msg += "\tType variable assignments:\n"
        msg += "\n".join("\t\t" + k.name + " -> " + to_str(v)
                         for k, v in type_var_map.items())
        if type_var_map:
            msg += "\n"
        msg += "\treceiver: {receiver!s}\n".format(receiver=log_types(
            receivers))
        msg += "\tparameters {params!s}\n".format(params=", ".join(
            log_types(p) for p in parameters))
        msg += "\treturn: {ret!s}\n".format(ret=log_types([return_type]))
        log(self.logger, msg)

    def wrap_types_with_type_parameter(self, types: List[tp.TypeParameter],
                                       blacklist):
        if utils.random.bool() or types == [self.api_graph.EMPTY]:
            return types
        types = list(types)
        upper_bound = functools.reduce(
            lambda acc, x: acc if x.is_subtype(acc) else x,
            types,
            types[0]
        )
        type_param = tp.TypeParameter(utils.random.caps(blacklist=blacklist),
                                      bound=upper_bound)
        self.test_case_type_params.append(type_param)
        new_types = [type_param]
        if len(types) > 1:
            new_types.extend(types)
        return new_types

    def compute_programs(self):
        program_index = 0
        i = 1
        func_name = "test"
        test_namespace = ast.GLOBAL_NAMESPACE + (func_name,)
        for (api, receivers, parameters, returns,
             type_map, type_parameters) in self.encodings:
            types = (receivers, *parameters, returns)
            if types in self.visited:
                continue
            self.visited.add(types)
            for combination in itertools.product(*types):
                receiver, parameters, return_type = (
                    combination[0], combination[1:-1], combination[-1])
                if program_index < self.start_index:
                    program_index += 1
                    continue
                self.api_graph.add_types(type_parameters)
                self.context = Context()
                self.namespace = test_namespace
                params = [[p] for p in parameters]
                blacklist = [tpa.name for tpa in type_parameters]
                receivers = (
                    self.wrap_types_with_type_parameter([receiver], blacklist)
                    if utils.random.bool(cfg.prob.bounded_type_parameters)
                    else [receiver]
                )
                expr = self.generate_from_type_combination(
                    api, receivers, params, return_type, type_map)
                yield self.produce_test_case(expr, type_parameters)
                self.log_program_info(i, api, [receiver], params, return_type,
                                      type_map)
                program_index += 1
                i += 1
            parameters = [
                utils.random.sample(t, min(self.max_conditional_depth + 1,
                                           len(t)))
                for t in types[1:-1]
            ]
            receivers = utils.random.sample(types[0], min(
                self.max_conditional_depth, len(types[0])))
            if all(len(p) == 1 for p in parameters) and len(receivers) == 1:
                # No conditinal can be created.
                self.api_graph.remove_types(type_parameters)
                continue
            for ret in types[-1]:
                if program_index < self.start_index:
                    program_index += 1
                    self.api_graph.remove_types(type_parameters)
                    continue
                self.context = Context()
                self.namespace = test_namespace
                expr = self.generate_from_type_combination(api, receivers,
                                                           parameters, ret,
                                                           type_map)
                yield self.produce_test_case(expr, type_parameters)
                self.log_program_info(i, api, receivers, parameters,
                                      return_type, type_map)
                program_index += 1
                i += 1
                self.api_graph.remove_types(type_parameters)

    def generate_expr_from_node(self, node: tp.Type,
                                func_ref: bool,
                                constraints: dict = None,
                                depth: int = 1) -> ExprRes:
        is_func = func_ref and self.api_graph.get_functional_type(
            node) is not None
        res = (
            ExprRes(self.generate_function_expr(node, constraints or {},
                                                depth),
                    {}, [node])
            if is_func
            else self._generate_expr_from_node(
                node, depth, {} if func_ref else (constraints or {}))
        )
        if node and utils.random.bool():
            var_name = gu.gen_identifier("lower")
            var_decl = ast.VariableDeclaration(
                var_name,
                res.expr,
                is_final=True,
                var_type=node,
                inferred_type=node
            )
            self._add_node_to_parent(self.namespace, var_decl)
            if self.type_erasure_mode:
                self.type_eraser.erase_var_type(var_decl, res)
            return ExprRes(ast.Variable(var_name), res.type_var_map, res.path)
        return res

    def generate_expr_from_nodes(self, nodes: List[tp.Type],
                                 constraints: dict,
                                 func_ref: bool = False,
                                 depth: int = 1) -> ExprRes:
        if len(nodes) == 1:
            return self.generate_expr_from_node(
                nodes[0], func_ref=func_ref, constraints=constraints,
                depth=depth)
        cond = self.generate_expr(self.bt_factory.get_boolean_type())
        cond_type = functools.reduce(
            lambda acc, x: acc if x.is_subtype(acc) else x,
            nodes,
            nodes[0]
        )
        expr1, type_var_map1, _ = self.generate_expr_from_node(
            nodes[0], func_ref=func_ref, constraints=constraints, depth=depth)
        expr2, type_var_map2, _ = self.generate_expr_from_node(
            nodes[1], func_ref=func_ref, constraints=constraints, depth=depth)
        ret_type_var_map = {}
        ret_type_var_map.update(type_var_map1)
        ret_type_var_map.update(type_var_map2)
        cond = ast.Conditional(cond, expr1, expr2, cond_type)
        for node in nodes[2:]:
            expr1, type_var_map1, _ = self.generate_expr_from_node(
                node, func_ref=func_ref, constraints=constraints, depth=depth)
            cond = ast.Conditional(
                self.generate_expr(self.bt_factory.get_boolean_type()),
                expr1, cond, cond_type)
            ret_type_var_map.update(type_var_map1)
        return ExprRes(cond, ret_type_var_map, [cond_type])

    def generate_from_type_combination(self, api, receiver, parameters,
                                       return_type, type_map) -> ast.Expr:
        type_var_map = copy(type_map)
        receiver, _, _ = self.generate_expr_from_nodes(
            receiver, type_var_map, func_ref=False)
        exp_parameters = [p.t for p in getattr(api, "parameters", [])]
        args = self._generate_args(exp_parameters, parameters,
                                   depth=1, type_var_map=type_var_map)
        var_type = return_type
        if self.inject_error_mode:
            # We are in fault injection mode, but no error has been injected
            # so far. Therefore, compute an incompatible target type.
            var_type = self.api_graph.get_concrete_output_type(api)
            var_type = tp.substitute_type(var_type, type_map)
            if not self.error_injected:
                var_type = tu.find_irrelevant_type(
                    var_type, self.api_graph.get_reg_types(), self.bt_factory)
                msg = "Expecting variable of {left!s}, but {right!s} is given"
                self.error_injected = msg.format(left=var_type,
                                                 right=return_type)
        self.type_eraser.with_target(return_type)
        if isinstance(api, ag.Method):
            call_args = [ast.CallArgument(arg.expr) for arg in args]
            type_args = self.substitute_types(api.type_parameters,
                                              type_var_map)
            expr = ast.FunctionCall(api.name, args=call_args,
                                    receiver=receiver, type_args=type_args)
            if api.type_parameters and self.type_erasure_mode:
                self.type_eraser.erase_types(expr, api, args)
        elif isinstance(api, ag.Constructor):
            def _instantiate_type_con(t: tp.Type):
                if t.is_type_constructor():
                    return t.new(self.substitute_types(t.type_parameters,
                                                       type_var_map))
                return t
            con_type = self.api_graph.get_type_by_name(api.get_class_name())
            con_type = _instantiate_type_con(con_type)
            call_args = [arg.expr for arg in args]
            expr = ast.New(con_type, call_args, receiver=receiver)
            if con_type.is_parameterized() and self.type_erasure_mode:
                self.type_eraser.erase_types(expr, api, args)
        else:
            assert isinstance(api, ag.Field)
            expr = ast.FieldAccess(expr=receiver, field=api.name)
        if not var_type or var_type == self.bt_factory.get_void_type():
            return expr

        var_decl = ast.VariableDeclaration(
            gu.gen_identifier('lower'),
            expr=expr,
            is_final=True,
            var_type=var_type,
            inferred_type=var_type)
        self._add_node_to_parent(self.namespace, var_decl)
        return None

    def generate_function_expr(self, expr_type: tp.Type, type_var_map: dict,
                               depth: int) -> Union[ast.Lambda,
                                                    ast.FunctionReference]:
        return (
            self.generate_lambda(expr_type, depth)
            if utils.random.bool()
            else self.generate_func_ref(expr_type, type_var_map, depth)
        )

    def generate_lambda(self, expr_type: tp.Type, depth: int) -> ast.Lambda:
        func_type = self.api_graph.get_functional_type_instantiated(expr_type)
        shadow_name = "lambda_" + str(next(self.int_stream))
        prev_namespace = self.namespace
        self.namespace += (shadow_name,)

        params = [
            ast.ParameterDeclaration(name=gu.gen_identifier("lower"),
                                     param_type=param_type)
            for param_type in func_type.type_args[:-1]
        ]
        for param in params:
            self.api_graph.add_variable_node(param.name, param.get_type())
        ret_type = func_type.type_args[-1]
        for p in params:
            self.context.add_var(self.namespace, p.name, p)
        if self.type_eraser.expected_type:
            _, type_vars = self.type_eraser.expected_type
            self.type_eraser.reset_target_type()
            self.type_eraser.with_target(func_type, type_vars)
        self.type_eraser.with_target(ret_type)
        expr = self._generate_expr_from_node(ret_type, depth + 1)[0]
        decls = list(self.context.get_declarations(self.namespace,
                                                   True).values())
        var_decls = [d for d in decls
                     if not isinstance(d, ast.ParameterDeclaration)]
        body = expr if not var_decls else ast.Block(var_decls + [expr])
        lambda_expr = ast.Lambda(shadow_name, params, ret_type, body,
                                 func_type)
        self.namespace = prev_namespace
        self.type_eraser.reset_target_type()
        if self.type_erasure_mode:
            self.type_eraser.erase_types(lambda_expr, func_type, [])
        for param in params:
            self.api_graph.remove_variable_node(param.name)
        return lambda_expr

    def generate_func_ref(self, expr_type: tp.Type, type_var_map: dict,
                          depth: int) -> ast.FunctionReference:
        candidates = self.api_graph.get_function_refs_of(expr_type)
        if not candidates:
            return self.generate_lambda(expr_type, depth)
        api, sub = utils.random.choice(candidates)
        type_var_map.update(sub)
        segs = api.name.rsplit(".", 1)
        is_constructor = isinstance(api, ag.Constructor)
        if len(segs) > 1 and not is_constructor:
            rec = None
        else:
            rec_type = (
                self.api_graph.get_type_by_name(api.get_class_name())
                if is_constructor
                else self.api_graph.get_input_type(api)
            )
            handler = self.api_graph.get_instantiations_of_recursive_bound
            if rec_type.is_parameterized() and getattr(api, "type_parameters",
                                                       []):
                # Instantiate a parameterized function that involves a
                # receiver.
                sub = tu.instantiate_parameterized_function(
                    api.type_parameters, self.api_graph.get_reg_types(),
                    type_var_map=type_var_map, rec_bound_handler=handler)
                type_var_map.update(sub)
            if rec_type.is_type_constructor():
                rec_type, sub = tu.instantiate_type_constructor(
                    rec_type, self.api_graph.get_reg_types(),
                    type_var_map=type_var_map,
                    rec_bound_handler=handler
                )
                type_var_map.update(sub)
            rec_type = self.substitute_types([rec_type], type_var_map)[0]
            rec = (
                ast.New(rec_type, args=[])  # This is a constructor reference
                if isinstance(api, ag.Constructor)
                else self._generate_expr_from_node(rec_type, depth + 1)[0]
            )
        api_name = (
            ast.FunctionReference.NEW_REF
            if isinstance(api, ag.Constructor) else api.name)
        return ast.FunctionReference(api_name, receiver=rec,
                                     signature=expr_type)

    def generate_expr(self,
                      expr_type: tp.Type = None,
                      only_leaves=False,
                      subtype=True,
                      exclude_var=False,
                      gen_bottom=False,
                      sam_coercion=False) -> ast.Expr:
        if expr_type == self.bt_factory.get_void_type():
            # For primitive void we generate an empty block
            return ast.Block(body=[])
        assert expr_type is not None
        constant_candidates = {
            self.bt_factory.get_number_type().name: gens.gen_integer_constant,
            self.bt_factory.get_integer_type().name: gens.gen_integer_constant,
            self.bt_factory.get_big_integer_type().name: gens.gen_integer_constant,
            self.bt_factory.get_byte_type().name: gens.gen_integer_constant,
            self.bt_factory.get_short_type().name: gens.gen_integer_constant,
            self.bt_factory.get_long_type().name: gens.gen_integer_constant,
            self.bt_factory.get_float_type().name: gens.gen_real_constant,
            self.bt_factory.get_double_type().name: gens.gen_real_constant,
            self.bt_factory.get_big_decimal_type().name: gens.gen_real_constant,
            self.bt_factory.get_char_type().name: gens.gen_char_constant,
            self.bt_factory.get_string_type().name: gens.gen_string_constant,
            self.bt_factory.get_boolean_type().name: gens.gen_bool_constant,
            self.bt_factory.get_array_type().name: (
                lambda x: self.gen_array_expr(x, only_leaves=True,
                                              subtype=False)
            ),
        }
        generator = constant_candidates.get(expr_type.name.capitalize())
        if generator is not None:
            return generator(expr_type)
        else:
            return ast.BottomConstant(expr_type)

    def generate(self, context=None) -> ast.Program:
        program = next(self.programs_gen, None)
        if not program:
            self._has_next = False
            program = None

        return program

    def has_next(self):
        return self._has_next

    def prepare_next_program(self, program_id):
        self.error_injected = None
        self.test_case_type_params = []

    def _get_target_selection(self, target: tp.Type) -> str:
        if self.inject_error_mode:
            return "abstract"
        # In case of arrays we don't examine abstract output types because
        # we don't want to instantiate type variables with array types.
        is_array = target.name == self.bt_factory.get_array_type().name
        return "concrete" if is_array else "all"

    def _generate_expr_from_node(self, node, depth=1, constraints=None):
        if depth > cfg.limits.max_depth:
            if node.is_type_constructor():
                handler = self.api_graph.get_instantiations_of_recursive_bound
                t, type_var_map = tu.instantiate_type_constructor(
                    node, self.api_graph.get_reg_types(),
                    rec_bound_handler=handler, type_var_map=constraints
                )
            else:
                t, type_var_map = node, {}
            return ExprRes(self.generate_expr(t), type_var_map, [t])
        stored_expr = self.visited_exprs.get(node)
        if stored_expr:
            return stored_expr
        if node == self.api_graph.EMPTY:
            return ExprRes(None, {}, [])
        target_selection = self._get_target_selection(node)
        find_infeasible = self.inject_error_mode and not self.error_injected
        path = self.api_graph.find_API_path(
            node, with_constraints=constraints,
            target_selection=target_selection, infeasible=find_infeasible)
        if not path:
            if node.is_type_constructor():
                handler = self.api_graph.get_instantiations_of_recursive_bound
                t, type_var_map = tu.instantiate_type_constructor(
                    node, self.api_graph.get_reg_types(),
                    rec_bound_handler=handler,
                    type_var_map=constraints
                )
            else:
                t = node
                type_var_map = (
                    node.get_type_variable_assignments()
                    if node.is_parameterized()
                    else {}
                )
            return ExprRes(self.generate_expr(t), type_var_map, [t])
        path, type_var_map, assignment_graph = path
        if find_infeasible:
            msg = "\n".join(
                "Assigning an incompatible type {t!r} to {type_var!s}".format(
                    type_var=k, t=v
                )
                for k, v in type_var_map.items()
            )
            self.error_injected = msg
        self.type_eraser.with_assignment_graph(assignment_graph)
        expr = self._generate_expression_from_path(path, depth=depth,
                                                   type_var_map=type_var_map)
        if not expr.has_variable() and not self.error_injected:
            # If the generated expression contains a variable, we don't store
            # this expression for later use because it refers to a variable
            # that is no longer valid.
            self.visited_exprs[node] = ExprRes(expr, type_var_map, path)
        return ExprRes(expr, type_var_map, path)

    def _generate_args(self, parameters, actual_types, depth,
                       type_var_map):
        if not parameters:
            return []
        args = []
        for i, param in enumerate(parameters):
            arg_types = actual_types[i]
            if self.inject_error_mode:
                # If we are in a fault injection mode, we consider the
                # parameter types that actually contains all type variables.
                # e.g., we use A<T> instead of A<String>
                arg_types = [
                    t if t.name != param.name else param
                    for t in actual_types[i]
                ]
            param_types = self.substitute_types(arg_types, type_var_map)
            self.type_eraser.with_target(param, get_type_variables(
                param, self.bt_factory))
            param = tp.substitute_type(param, type_var_map)
            expr = self.generate_expr_from_nodes(param_types, {},
                                                 func_ref=True,
                                                 depth=depth)
            self.type_eraser.reset_target_type()
            args.append(expr)
        return args

    def _generate_expression_from_path(self, path: list,
                                       depth: int, type_var_map) -> ast.Expr:
        def _instantiate_type_con(t: tp.Type):
            if t.is_type_constructor():
                return t.new(self.substitute_types(t.type_parameters,
                                                   type_var_map))
            return t

        elem = path[-1]
        receiver_path = path[:-1]
        if not receiver_path:
            receiver = None
        else:
            self.type_eraser.with_target(target_type=None)
            receiver = self._generate_expression_from_path(receiver_path,
                                                           depth, type_var_map)
            self.type_eraser.reset_target_type()
        if isinstance(elem, ag.Method):
            parameters = [param.t for param in elem.parameters]
            args = self._generate_args(parameters,
                                       [[p] for p in parameters],
                                       depth + 1, type_var_map)
            call_args = [ast.CallArgument(arg.expr)
                         for arg in args]
            type_args = [type_var_map[tpa] for tpa in elem.type_parameters]
            expr = ast.FunctionCall(elem.name, args=call_args,
                                    receiver=receiver, type_args=type_args)
            if elem.type_parameters and self.type_erasure_mode:
                self.type_eraser.erase_types(expr, elem, args)
        elif isinstance(elem, ag.Field):
            expr = ast.FieldAccess(receiver, elem.name)
        elif isinstance(elem, ag.Constructor):
            con_type = self.api_graph.get_type_by_name(elem.get_class_name())
            con_type = _instantiate_type_con(con_type)
            parameters = [param.t for param in elem.parameters]
            args = self._generate_args(parameters, [[p] for p in parameters],
                                       depth + 1, type_var_map)
            call_args = [arg.expr for arg in args]
            expr = ast.New(con_type, call_args, receiver=receiver)
            if con_type.is_parameterized() and self.type_erasure_mode:
                self.type_eraser.erase_types(expr, elem, args)
        elif isinstance(elem, ag.Variable):
            return ast.Variable(elem.name)
        elif len(path) == 1:
            t = _instantiate_type_con(elem)
            expr = self.generate_expr(self.substitute_types([t],
                                                            type_var_map)[0])
        else:
            return receiver
        return expr

    def substitute_types(self, types: List[tp.Type],
                         type_var_map: dict) -> List[tp.Type]:
        if not self.inject_error_mode or self.error_injected:
            return [tp.substitute_type(t, type_var_map) for t in types]
        if utils.random.bool():
            # With a probability decide if it's time to inject a type error
            # now or later.
            return [tp.substitute_type(t, type_var_map) for t in types]
        type_variables = set()
        for t in types:
            type_variables.update(get_type_variables(t, self.bt_factory))
        for type_var in type_variables:
            old_t = type_var_map[type_var]
            new_t = tu.find_irrelevant_type(old_t,
                                            self.api_graph.get_reg_types(),
                                            self.bt_factory)
            if new_t:
                msg = ("Changing assignment of {type_var!s} from {t1!r} to "
                       "{t2!r}")
                msg = msg.format(type_var=type_var.name,
                                 t1=self.translator.get_type_name(old_t),
                                 t2=self.translator.get_type_name(new_t))
                self.error_injected = (msg if not self.error_injected
                                       else self.error_injected + "\n" + msg)
                type_var_map[type_var] = new_t
                self.type_eraser.required_type_parameters.add(type_var)
        return [tp.substitute_type(t, type_var_map) for t in types]
