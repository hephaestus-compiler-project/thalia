from copy import deepcopy
import itertools

from src import utils
from src.ir import ast, types as tp, type_utils as tu
from src.ir.context import Context
from src.generators import generators as gens, utils as gu, Generator
from src.generators.api import api_graph as ag, builder, matcher as match
from src.generators.config import cfg
from src.modules.logging import log


class APIGenerator(Generator):
    API_GRAPH_BUILDERS = {
        "java": builder.JavaAPIGraphBuilder,
        "kotlin": builder.KotlinAPIGraphBuilder,
        "groovy": builder.JavaAPIGraphBuilder,
    }

    def __init__(self, api_docs, options={}, language=None, logger=None):
        super().__init__(language=language, logger=logger)
        self.logger.update_filename("api-generator")
        self.api_docs = api_docs
        self.api_graph = self.API_GRAPH_BUILDERS[language](language).build(
            api_docs)
        self.encodings = self.api_graph.encode_api_components()
        self.visited = set()
        self.visited_exprs = {}
        self.programs_gen = self.compute_programs()
        self._has_next = True
        self.start_index = options.get("start-index", 0)
        self.api_matcher = None
        api_rules_file = options.get("api-rules")
        if api_rules_file:
            self.api_matcher = match.parse_rule_file(api_rules_file)

    def compute_programs(self):
        func_name = "test"
        test_namespace = ast.GLOBAL_NAMESPACE + (func_name,)
        program_index = 0
        for api, receivers, parameters, returns, type_map in self.encodings:
            if isinstance(api, ag.Constructor):
                # TODO
                continue
            if self.api_matcher and not self.api_matcher.match(api):
                continue
            types = (receivers, *parameters, returns)
            if types in self.visited:
                continue
            self.visited.add(types)
            for combination in itertools.product(*types):
                if program_index < self.start_index:
                    program_index += 1
                    continue
                receiver, parameters, return_type = (
                    combination[0], combination[1:-1], combination[-1])
                self.context = Context()
                self.namespace = test_namespace
                expr = self.generate_from_type_combination(api, receiver,
                                                           parameters,
                                                           return_type,
                                                           type_map)
                decls = list(self.context.get_declarations(
                    self.namespace, True).values())
                decls = [d for d in decls
                         if not isinstance(d, ast.ParameterDeclaration)]
                body = decls + ([expr] if expr else [])
                main_func = ast.FunctionDeclaration(
                    func_name,
                    params=[],
                    ret_type=self.bt_factory.get_void_type(),
                    body=ast.Block(body),
                    func_type=ast.FunctionDeclaration.FUNCTION)
                self._add_node_to_parent(self.namespace[:-1], main_func)
                program_index += 1
                msg = ("API: {}; Generating program of combination: "
                       "(receiver: {}, parameters: {}, return: {}")
                msg = msg.format(str(api), str(receiver),
                                 ",".join([str(p) for p in parameters]),
                                 str(return_type))
                log(self.logger, msg)
                yield ast.Program(deepcopy(self.context), self.language)

    def generate_from_type_combination(self, api, receiver, parameters,
                                       return_type, type_map) -> ast.Expr:
        receiver, type_var_map = self._generate_expr_from_node(receiver)
        type_var_map.update(type_map)
        args = self._generate_args(getattr(api, "parameters", []), parameters,
                                   depth=1, type_var_map=type_var_map)
        var_type = tp.substitute_type(return_type, type_var_map)
        if isinstance(api, ag.Method):
            args = [ast.CallArgument(arg) for arg in args]
            type_args = [type_var_map[tpa] for tpa in api.type_parameters]
            expr = ast.FunctionCall(api.name, args=args, receiver=receiver,
                                    type_args=type_args)
        elif isinstance(api, ag.Constructor):
            expr = ast.New(tp.Classifier(api.name), args=args)
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

    def generate_func_ref(self, expr_type: tp.Type, type_var_map: dict,
                          depth: int):
        candidates = self.api_graph.get_function_refs_of(expr_type)
        if not candidates:
            return ast.BottomConstant(expr_type)
        api, sub = utils.random.choice(candidates)
        type_var_map.update(sub)
        segs = api.name.rsplit(".", 1)
        if len(segs) > 1:
            rec = None
        else:
            rec_type = self.api_graph.get_type_by_name(api.get_class_name())
            if rec_type.is_type_constructor():
                handler = self.api_graph.get_instantiations_of_recursive_bound
                try:
                    rec_type, sub = tu.instantiate_type_constructor(
                        rec_type, self.api_graph.get_reg_types(),
                        type_var_map=type_var_map,
                        rec_bound_handler=handler
                    )
                except:
                    import pdb; pdb.set_trace()
                type_var_map.update(sub)
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
        pass

    def _generate_expr_from_node(self, node, depth=1):
        stored_expr = self.visited_exprs.get(node)
        if stored_expr:
            return stored_expr
        if node == self.api_graph.EMPTY:
            return None, {}
        if depth >= cfg.limits.max_depth:
            if node.is_type_constructor():
                handler = self.api_graph.get_instantiations_of_recursive_bound
                t, type_var_map = tu.instantiate_type_constructor(
                    node, self.api_graph.get_reg_types(),
                    rec_bound_handler=handler
                )
            else:
                t, type_var_map = node, {}
            return self.generate_expr(t), type_var_map
        path = self.api_graph.find_API_path(node)
        if not path:
            if node.is_type_constructor():
                handler = self.api_graph.get_instantiations_of_recursive_bound
                t, type_var_map = tu.instantiate_type_constructor(
                    node, self.api_graph.get_reg_types(),
                    rec_bound_handler=handler
                )
            else:
                t = node
                type_var_map = (
                    node.get_type_variable_assignments()
                    if node.is_parameterized()
                    else {}
                )
            return self.generate_expr(t), type_var_map
        path, type_var_map = path
        expr = self._generate_expression_from_path(path, depth=depth,
                                                   type_var_map=type_var_map)
        self.visited_exprs[node] = (expr, type_var_map)
        return expr, type_var_map

    def _generate_args(self, parameters, actual_types, depth,
                       type_var_map):
        if not parameters:
            return []
        args = []
        for i, param in enumerate(parameters):
            param_type = tp.substitute_type(actual_types[i], type_var_map)
            param = tp.substitute_type(param, type_var_map)
            if param_type and param_type in self.api_graph.subtypes(param):
                t = param_type
            else:
                t = param
            t = tp.substitute_type(t, type_var_map)
            is_func = self.api_graph.get_functional_type(t) is not None
            expr = (
                self.generate_func_ref(t, type_var_map, depth)
                if is_func
                else self._generate_expr_from_node(t, depth)[0]
            )
            args.append(expr)
        return args

    def _generate_expression_from_path(self, path: list,
                                       depth: int, type_var_map) -> ast.Expr:
        def _instantiate_type_con(t: tp.Type):
            if t.is_type_constructor():
                return t.new([type_var_map[tpa]
                              for tpa in t.type_parameters])
            return t

        elem = path[-1]
        receiver_path = path[:-1]
        if not receiver_path:
            receiver = None
        else:
            receiver = self._generate_expression_from_path(receiver_path,
                                                           depth, type_var_map)
        if isinstance(elem, ag.Method):
            args = [ast.CallArgument(pe)
                    for pe in self._generate_args(elem.parameters,
                                                  elem.parameters,
                                                  depth + 1, type_var_map)]
            type_args = [type_var_map[tpa] for tpa in elem.type_parameters]
            expr = ast.FunctionCall(elem.name, args=args, receiver=receiver,
                                    type_args=type_args)
        elif isinstance(elem, ag.Field):
            expr = ast.FieldAccess(receiver, elem.name)
        elif isinstance(elem, ag.Constructor):
            args = self._generate_args(elem.parameters, elem.parameters,
                                       depth + 1, type_var_map)
            con_type = self.api_graph.get_type_by_name(elem.name)
            con_type = _instantiate_type_con(con_type)
            expr = ast.New(con_type, args)
        else:
            t = _instantiate_type_con(elem)
            expr = self.generate_expr(tp.substitute_type(t, type_var_map))
        return expr
