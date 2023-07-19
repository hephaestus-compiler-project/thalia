from copy import deepcopy, copy
import functools
import itertools
from typing import List, NamedTuple, Union

from src import utils
from src.config import cfg
from src.ir import ast, types as tp, type_utils as tu
from src.ir.context import Context
from src.generators import generators as gens, utils as gu, Generator
from src.generators.api import (api_graph as ag, builder, matcher as match,
                                type_erasure as te, fault_injection as fi)
from src.generators.api import utils as au
from src.modules.logging import log
from src.translators import TRANSLATORS


def get_type_variables_of_callable(
        api_graph: ag.APIGraph,
        node: ag.APINode
) -> List[tp.TypeParameter]:
    if isinstance(node, ag.Method):
        return node.type_parameters
    elif isinstance(node, ag.Constructor):
        t = api_graph.get_type_by_name(node.name)
        if t is None:
            return []
        return getattr(t, "type_parameters", [])
    else:
        return []


class ExprRes(NamedTuple):
    expr: ast.Expr
    type_var_map: dict
    path: list

    def __hash__(self):
        return hash(str(self.expr) + str(self.type_var_map) +
                    str(self.path) + str(self.assignment_graph))


class APIGenerator(Generator):
    TEST_CASE_NAME = "test"

    TEST_NAMESPACE = ast.GLOBAL_NAMESPACE + (TEST_CASE_NAME,)

    API_GRAPH_BUILDERS = {
        "java": builder.JavaAPIGraphBuilder,
        "kotlin": builder.KotlinAPIGraphBuilder,
        "groovy": builder.JavaAPIGraphBuilder,
        "scala": builder.ScalaAPIGraphBuilder,
    }

    def __init__(self, api_docs, options={}, language=None, logger=None):
        super().__init__(language=language, logger=logger)
        if self.logger:
            self.logger.update_filename("api-generator")
        self.api_graph = self.API_GRAPH_BUILDERS[language](
            language, **options).build(api_docs)
        api_rules_file = options.get("api-rules")
        kwargs = {}
        if api_rules_file:
            kwargs["matcher"] = match.parse_rule_file(api_rules_file)
        self.log_api_graph_statistics(**kwargs)
        self.encodings = self.api_graph.encode_api_components(**kwargs)
        self.visited = set()
        self.visited_exprs = {}
        self.programs_gen = self.compute_programs()
        self._has_next = True

        self.inject_error_mode = options.get("inject-type-error", False)
        self.type_erasure_mode = options.get("erase-types", False)
        self.start_index = options.get("start-index", 0)
        self.max_conditional_depth = options.get("max-conditional-depth", 4)
        self.disable_expression_cache = options.get("disable-expression-cache",
                                                    False)

        self.translator = TRANSLATORS[language]()
        self.type_eraser: te.TypeEraser = te.TypeEraser(self.api_graph,
                                                        self.bt_factory,
                                                        self.inject_error_mode)
        self.error_injected = None
        self.test_case_type_params: List[tp.TypeParameter] = []

    def log_api_graph_statistics(self, matcher):
        if self.logger is None:
            return
        statistics = self.api_graph.statistics(matcher)
        log(self.logger, "Built API with the following statistics:")
        log(self.logger, f"\tNumber of nodes:{statistics.nodes}")
        log(self.logger, f"\tNumber of edges:{statistics.edges}")
        log(self.logger, f"\tNumber of methods:{statistics.methods}")
        log(self.logger,
            f"\tNumber of polymorphic methods:{statistics.polymorphic_methods}")
        log(self.logger, f"\tNumber of fields:{statistics.fields}")
        log(self.logger,
            f"\tNumber of constructors:{statistics.constructors}")
        log(self.logger, f"\tNumber of types:{statistics.types}")
        log(self.logger,
            f"\tNumber of type constructors:{statistics.type_constructors}")
        log(self.logger,
            f"\tAvg inheritance chain size:{statistics.inheritance_chain_size:.2f}")
        log(self.logger,
            f"\tAvg API signature size:{statistics.signature_length:.2f}\n")

    def parse_builtin_type(self, cls_name: str) -> tp.Type:
        api_language = "java" if cls_name.startswith("java") else self.language
        api_graph_builder = self.API_GRAPH_BUILDERS[self.language](
           self.language)
        api_graph_builder.api_language = api_language
        return api_graph_builder.parse_type(cls_name)

    def produce_test_case(self, expr: ast.Expr,
                          type_parameters) -> ast.Program:
        decls = list(self.context.get_declarations(
            self.namespace, True).values())
        decls = [d for d in decls
                 if not isinstance(d, ast.ParameterDeclaration)]
        body = decls + ([expr] if expr else [])
        type_parameters = list(type_parameters)
        type_parameters.extend(self.test_case_type_params)
        main_func = ast.FunctionDeclaration(
            self.TEST_CASE_NAME,
            params=[],
            type_parameters=type_parameters,
            ret_type=self.bt_factory.get_void_type(),
            body=ast.Block(body),
            func_type=ast.FunctionDeclaration.FUNCTION)
        self._add_node_to_parent(self.namespace[:-1], main_func)
        return ast.Program(deepcopy(self.context), self.language)

    def log_program_info(self, program_id, api, receivers, parameters,
                         return_type, type_var_map, is_incorrect):
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
        msg += "Correctness: {corr!s}".format(corr=not is_incorrect)
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
        if upper_bound.is_type_constructor():
            return types
        type_param = tp.TypeParameter(utils.random.caps(blacklist=blacklist),
                                      bound=upper_bound)
        self.test_case_type_params.append(type_param)
        new_types = [type_param]
        if len(types) > 1:
            new_types.extend(types)
        return new_types

    def prepare_and_generate_test_case(self, encoding: ag.APIEncoding,
                                       receivers: List[tp.Type],
                                       parameters: List[List[tp.Type]],
                                       return_type: tp.Type,
                                       pid: int,
                                       is_incorrect: bool) -> ast.Program:
        self.context = Context()
        self.namespace = self.TEST_NAMESPACE
        self.api_graph.add_types(encoding.type_parameters)
        expr = self.generate_from_type_combination(
            encoding.api, receivers, parameters,
            return_type, encoding.type_var_map)
        if is_incorrect:
            self.error_injected = "Incorrect api typing sequence"
        self.log_program_info(pid, encoding.api, receivers, parameters,
                              return_type, encoding.type_var_map,
                              is_incorrect)
        program = self.produce_test_case(expr, encoding.type_parameters)
        self.api_graph.remove_types(encoding.type_parameters)
        return program

    def generate_test_case_from_combination(self, combination,
                                            encoding: ag.APIEncoding,
                                            pid: int,
                                            is_incorrect: bool) -> ast.Program:
        receiver, parameters, return_type = (
            combination[0], combination[1:-1], combination[-1])
        params = [[p] for p in parameters]
        blacklist = [tpa.name for tpa in encoding.type_parameters]
        receivers = (
            self.wrap_types_with_type_parameter([receiver], blacklist)
            if utils.random.bool(cfg.prob.bounded_type_parameters)
            else [receiver]
        )
        if is_incorrect:
            self.error_injected = "Incorrect api typing sequence"
        return self.prepare_and_generate_test_case(encoding, receivers,
                                                   params, return_type, pid,
                                                   is_incorrect)

    def generate_test_case_conditional(self, encoding, return_type,
                                       pid, is_incorrect: bool) -> ast.Program:
        types = (encoding.receivers, *encoding.parameters,
                 encoding.returns)
        parameters = [
            utils.random.sample(t, min(self.max_conditional_depth + 1, len(t)))
            for t in types[1:-1]
        ]
        receivers = utils.random.sample(types[0], min(
            self.max_conditional_depth, len(types[0])))
        if all(len(p) == 1 for p in parameters) and len(receivers) == 1:
            # No conditinal can be created.
            return None
        return self.prepare_and_generate_test_case(encoding, receivers,
                                                   parameters, return_type,
                                                   pid, is_incorrect)

    def compute_typing_sequences(self, encoding, types):
        if not self.inject_error_mode:
            return itertools.product(*types), False

        self.api_graph.add_types(encoding.type_parameters)
        finj = fi.FaultInjection(self.api_graph, self.bt_factory)
        typing_seqs = finj.compute_incorrect_typing_sequences(encoding)
        self.api_graph.remove_types(encoding.type_parameters)
        return typing_seqs, True

    def compute_programs(self):
        program_index = 0
        i = 1
        for encoding in self.encodings:
            overloaded_methods = self.api_graph.get_overloaded_methods(
                self.api_graph.get_input_type(encoding.api),
                encoding.api,
            )
            types = (encoding.receivers, *encoding.parameters,
                     encoding.returns)
            if types in self.visited:
                continue
            self.visited.add(types)
            try:
                typing_seqs, is_incorrect = self.compute_typing_sequences(
                    encoding, types)
                for typing_seq in typing_seqs:
                    # There is a typing sequence that triggers overload
                    # ambiguity.
                    sub = {t: encoding.type_var_map[t]
                           for t in get_type_variables_of_callable(
                               self.api_graph, encoding.api)}
                    if any(au.is_typing_seq_ambiguous(encoding.api, m,
                                                      typing_seq[1:-1], sub)
                           for m in overloaded_methods):
                        program_index += 1
                        continue

                    # Generate a test case from the typing sequence:
                    # (receiver, parameters, return_type)
                    if program_index < self.start_index:
                        program_index += 1
                        continue
                    yield self.generate_test_case_from_combination(typing_seq,
                                                                   encoding, i,
                                                                   is_incorrect)
                    program_index += 1
                    i += 1
                for ret in types[-1]:
                    if program_index < self.start_index:
                        program_index += 1
                        continue
                    # Merge receivers and parameters, and generate a test
                    # case with conditionals
                    program = self.generate_test_case_conditional(encoding,
                                                                  ret, i,
                                                                  is_incorrect)
                    if program is None:
                        # No conditional can be created
                        continue
                    yield program
                    i += 1
                    program_index += 1
            except Exception as e:
                # Handle any exception in order to prevent the termination
                # of iteration.
                self.api_graph.remove_types(encoding.type_parameters)
                program_index += 1

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
            if node.is_type_constructor():
                node = node.new(node.type_parameters)
                node = tp.substitute_type(node, res.type_var_map)
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
            cls_name = api.get_class_name()
            con_type = self.api_graph.get_type_by_name(
                cls_name) or self.parse_builtin_type(cls_name)
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
            self.generate_func_ref(expr_type, type_var_map, depth)
            if utils.random.bool(prob=cfg.prob.func_ref)
            else self.generate_lambda(expr_type, depth)
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
        candidates = self.api_graph.get_function_refs_of(expr_type,
                                                         single=True)
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
        func_type = tp.substitute_type(
            self.api_graph.get_functional_type(expr_type), type_var_map)
        return ast.FunctionReference(api_name, receiver=rec,
                                     signature=expr_type,
                                     function_type=func_type)

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
        path = self.api_graph.find_API_path(
            node, with_constraints=constraints,
            target_selection=target_selection, infeasible=False)
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
        expr = self._generate_expression_from_path(path, depth=depth,
                                                   type_var_map=type_var_map)
        if not expr.has_variable() and not self.error_injected:
            # If the generated expression contains a variable, we don't store
            # this expression for later use because it refers to a variable
            # that is no longer valid.
            if not self.disable_expression_cache:
                self.visited_exprs[node] = ExprRes(expr, type_var_map, path)
        return ExprRes(expr, type_var_map, path)

    def _generate_args(self, parameters, actual_types, depth,
                       type_var_map):
        if not parameters:
            return []
        args = []
        for i, param in enumerate(parameters):
            arg_types = actual_types[i]
            param_types = self.substitute_types(arg_types, type_var_map)
            self.type_eraser.with_target(param, tu.get_type_variables_of_type(
                param))
            for i, param_t in enumerate(list(param_types)):
                # If encountering a raw type, instantiate the corresponding
                # type constructor.
                if param_t.is_type_constructor():
                    param_types[i] = tu.instantiate_type_constructor(
                        param_t, self.api_graph.get_reg_types(), True,
                        rec_bound_handler=self.api_graph.get_instantiations_of_recursive_bound)
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
            cls_name = elem.get_class_name()
            con_type = self.api_graph.get_type_by_name(
                cls_name) or self.parse_builtin_type(cls_name)
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
        return [tp.substitute_type(t, type_var_map) for t in types]
