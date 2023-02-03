from copy import deepcopy
import itertools
from typing import List, Set, NamedTuple, Union

import networkx as nx

from src import utils
from src.ir import ast, types as tp, type_utils as tu
from src.ir.context import Context
from src.generators import api_graph as ag, generators as gens, utils as gu
from src.generators.config import cfg
from src.generators.generator import Generator
from src.modules.logging import log


def _find_path_of_target(graph: nx.DiGraph, target: ag.TypeNode) -> list:
    if target not in graph:
        return None
    source_nodes = [
        node
        for node, indegree in graph.in_degree(graph.nodes())
        if indegree == 0 and nx.has_path(graph, node, target)
    ]
    if not source_nodes:
        return None
    source = utils.random.choice(source_nodes)
    if source == target:
        return None
    path = next(nx.all_simple_paths(graph, source=source, target=target))
    pruned_path = [n for i, n in enumerate(path)
                   if i == 0 or not isinstance(n, ag.TypeNode)]
    return pruned_path


class APIGenerator(Generator):
    API_GRAPH_BUILDERS = {
        "java": ag.JavaAPIGraphBuilder,
        "kotlin": ag.KotlinAPIGraphBuilder,
        "groovy": ag.JavaAPIGraphBuilder,
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

    def compute_programs(self):
        func_name = "test"
        test_namespace = ast.GLOBAL_NAMESPACE + (func_name,)
        program_index = 0
        for api, receivers, parameters, returns in self.encodings:
            if isinstance(api, ag.Constructor):
                # TODO
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
                                                           return_type)
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
                msg = ("Generating program of combination: (receiver: {}, "
                       "parameters: {}, return: {}")
                msg = msg.format(str(receiver),
                                 ",".join([str(p) for p in parameters]),
                                 str(return_type))
                log(self.logger, msg)
                yield ast.Program(deepcopy(self.context), self.language)

    def generate_from_type_combination(self, api, receiver, parameters,
                                       return_type) -> ast.Expr:
        receiver, type_var_map = self._generate_expr_from_node(receiver)
        args = self._generate_args(getattr(api, "parameters", []), parameters,
                                   depth=1, type_var_map=type_var_map)
        var_type = tp.substitute_type(return_type.t, type_var_map)
        if isinstance(api, ag.Method):
            args = [ast.CallArgument(arg) for arg in args]
            expr = ast.FunctionCall(api.name, args=args, receiver=receiver)
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
            stored_expr
        if node == self.api_graph.EMPTY:
            return None, {}
        if depth == cfg.limits.max_depth:
            if node.t.is_type_constructor():
                t, type_var_map = tu.instantiate_type_constructor(
                    node.t, self.api_graph._types)
            else:
                t, type_var_map = node.t, {}
            return self.generate_expr(t), type_var_map
        path = self.api_graph.find_API_path(node)
        if not path:
            type_var_map = (
                node.t.get_type_variable_assignments()
                if node.t.is_parameterized()
                else {}
            )
            return self.generate_expr(node.t), type_var_map
        path, type_var_map = path
        print(path, type_var_map)
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
            param_type = actual_types[i]
            if param_type and param_type in self.api_graph.subtypes(param):
                t = param_type
            else:
                t = param
            t = ag.TypeNode(tp.substitute_type(t.t, type_var_map))
            args.append(self._generate_expr_from_node(t, depth)[0])
        return args

    def _generate_expression_from_path(self, path: list,
                                       depth: int, type_var_map) -> ast.Expr:
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
            expr = ast.FunctionCall(elem.name, args=args, receiver=receiver)
        elif isinstance(elem, ag.Field):
            expr = ast.FieldAccess(receiver, elem.name)
        elif isinstance(elem, ag.Constructor):
            args = self._generate_args(elem.parameters, elem.parameters,
                                       depth + 1, type_var_map)
            con_type = self.api_graph.get_type_by_name(elem.name)
            if con_type.is_type_constructor():
                con_type = con_type.new([type_var_map[t]
                                         for t in con_type.type_parameters])
            expr = ast.New(con_type, args)
        else:
            expr = self.generate_expr(tp.substitute_type(elem.t, type_var_map))
        return expr
