from copy import deepcopy
import itertools
from typing import List, Set, NamedTuple, Union

import networkx as nx

from src import utils
from src.ir import ast, types as tp
from src.ir.context import Context
from src.generators import api_graph as ag, generators as gens, utils as gu
from src.generators.config import cfg
from src.generators.generator import Generator


def _reachable_with_inheritance(graph: nx.DiGraph,
                                source: ag.TypeNode) -> list:
    visited = {k: False for k in graph.nodes()}

    def _dfs(n):
        visited[n] = True
        if n not in graph:
            return
        for target, attrs in graph[n].items():
            if attrs["label"] != ag.WIDENING:
                continue
            if not visited.get(target, False):
                _dfs(target)
    _dfs(source)
    return {
        n
        for n, is_visited in visited.items()
        if is_visited
    }


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


EMPTY = 0


class APIEncoding(NamedTuple):
    api: Union[ag.Field, ag.Method, ag.Constructor]
    receivers: Set[ag.TypeNode]
    parameters: Set[ag.TypeNode]
    returns: Set[ag.TypeNode]


class APIGenerator(Generator):
    API_GRAPH_BUILDERS = {
        "java": ag.JavaAPIGraphBuilder,
        "kotlin": ag.JavaAPIGraphBuilder,
        "groovy": ag.JavaAPIGraphBuilder,
    }

    def __init__(self, api_docs, options={}, language=None, logger=None):
        super().__init__(language=language, logger=logger)
        self.api_docs = api_docs
        self.api_graph: nx.DiGraph = self.API_GRAPH_BUILDERS[language](
            language).build(api_docs)
        self.encodings = self.encode_api_components(self.api_graph)
        self.visited = set()
        self.visited_exprs = {}
        self.programs_gen = self.compute_programs()
        self._has_next = True
        self.start_index = options.get("start-index", 0)

    def encode_api_components(self, api_graph: nx.DiGraph) -> List[APIEncoding]:
        api_components = (ag.Field, ag.Constructor, ag.Method)
        api_nodes = [
            n
            for n in api_graph.nodes()
            if isinstance(n, api_components)
        ]
        encodings = []
        reversed_graph = api_graph.reverse()
        for node in api_nodes:
            view = api_graph.in_edges(node)
            if not view:
                receivers = {EMPTY}
            else:
                assert len(view) == 1
                receiver = list(view)[0][0]
                receivers = {receiver}
                if receiver.t != self.bt_factory.get_any_type():
                    receivers.update(_reachable_with_inheritance(
                        reversed_graph, receiver))
            parameters = set(getattr(node, "parameters", []))
            for param in set(parameters):
                if param.t != self.bt_factory.get_any_type():
                    parameters.update(_reachable_with_inheritance(
                        reversed_graph, param))
            if not parameters:
                parameters.add(EMPTY)
            view = api_graph.out_edges(node)
            assert len(view) == 1
            ret_type = list(view)[0][1]
            ret_types = _reachable_with_inheritance(api_graph, ret_type)
            encodings.append(APIEncoding(node, frozenset(receivers),
                                         frozenset(parameters),
                                         frozenset(ret_types)))
        return encodings

    def compute_programs(self):
        func_name = "test"
        test_namespace = ast.GLOBAL_NAMESPACE + (func_name,)
        program_index = 0
        for api, receivers, parameters, returns in self.encodings:
            types = (receivers, parameters, returns)
            if types in self.visited:
                continue
            self.visited.add(types)
            for combination in itertools.product(*types):
                if program_index < self.start_index:
                    program_index += 1
                    continue
                receiver, parameter, return_type = combination
                self.context = Context()
                self.namespace = test_namespace
                expr = self.generate_from_type_combination(api, receiver,
                                                           parameter,
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
                yield ast.Program(deepcopy(self.context), self.language)

    def generate_from_type_combination(self, api, receiver, parameter,
                                       return_type) -> ast.Expr:
        receiver = self._generate_expr_from_node(receiver)
        args = self._generate_args(getattr(api, "parameters", []), parameter,
                                   depth=1)
        var_type = return_type
        if isinstance(api, ag.Method):
            args = [ast.CallArgument(arg) for arg in args]
            expr = ast.FunctionCall(api.name, args=args, receiver=receiver)
        elif isinstance(api, ag.Constructor):
            expr = ast.New(tp.Classifier(api.name), args=args)
        else:
            assert isinstance(api, ag.Field)
            expr = ast.FieldAccess(expr=receiver, field=api.name)

        if not var_type or var_type.t == self.bt_factory.get_void_type():
            return expr
        var_decl = ast.VariableDeclaration(
            gu.gen_identifier('lower'),
            expr=expr,
            is_final=True,
            var_type=var_type.t,
            inferred_type=var_type.t)
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

    def reset_state(self):
        pass

    def _generate_expr_from_node(self, node, depth=1):
        expr = self.visited_exprs.get(node)
        if expr:
            return expr
        if node == EMPTY:
            return None
        if depth == cfg.limits.max_depth:
            return self.generate_expr(node.t)
        path = _find_path_of_target(self.api_graph, node)
        if not path:
            return self.generate_expr(node.t)
        expr = self._generate_expression_from_path(path, depth=depth)
        self.visited_exprs[node] = expr
        return expr

    def _generate_args(self, parameters, param_type, depth):
        if not parameters:
            return []
        args = []
        for param in parameters:
            if param_type and param in _reachable_with_inheritance(
                    self.api_graph, param_type):
                t = param_type
            else:
                t = param
            args.append(self._generate_expr_from_node(t, depth))
        return args

    def _generate_expression_from_path(self, path: list,
                                       depth: int) -> ast.Expr:
        elem = path[-1]
        receiver_path = path[:-1]
        if not receiver_path:
            receiver = None
        else:
            receiver = self._generate_expression_from_path(receiver_path,
                                                           depth)
        if isinstance(elem, ag.Method):
            args = [ast.CallArgument(pe)
                    for pe in self._generate_args(elem.parameters, None,
                                                  depth + 1)]
            expr = ast.FunctionCall(elem.name, args=args, receiver=receiver)
        elif isinstance(elem, ag.Field):
            expr = ast.FieldAccess(receiver, elem.name)
        elif isinstance(elem, ag.Constructor):
            args = self._generate_args(elem.parameters, None, depth + 1)
            expr = ast.New(tp.Classifier(elem.name), args)
        else:
            expr = self.generate_expr(elem.t)
        return expr
