from src.ir import ast, types as tp
from src.ir.context import Context
from src.generators import api_graph as ag, generators as gens
from src.generators.generator import Generator


class APIGenerator(Generator):
    API_GRAPH_BUILDERS = {
        "java": ag.JavaAPIGraphBuilder,
        "kotlin": ag.JavaAPIGraphBuilder,
        "groovy": ag.JavaAPIGraphBuilder,
    }

    def __init__(self, api_docs, language=None, logger=None):
        super().__init__(language=language, logger=logger)
        self.api_docs = api_docs
        self.api_graph = self.API_GRAPH_BUILDERS[language](language).build(
            api_docs)
        self.max_paths = 500
        self.path_cutoff = 11

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
        t = expr_type.name
        generator = constant_candidates.get(t.name.capitalize())
        if generator is not None:
            return generator(t)
        else:
            return ast.BottomConstant(t)

    def generate_expression_from_path(self, path: list) -> ast.Expr:
        elem = path[-1]
        receiver_path = path[:-1]
        if not receiver_path:
            receiver = None
        else:
            receiver = self.generate_expression_from_path(receiver_path)

        if isinstance(elem, ag.Method):
            args = [ast.CallArgument(self.generate_expr(pt))
                    for pt in elem.parameters]

            return ast.FunctionCall(elem.name, args=args, receiver=receiver)
        elif isinstance(elem, ag.Field):
            return ast.FieldAccess(receiver, elem.name)
        elif isinstance(elem, ag.Constructor):
            args = [self.generate_expr(pt) for pt in elem.parameters]
            return ast.New(tp.Classifier(elem.name), args)

        assert False, ("This is an unreachable code")

    def generate(self, context=None) -> ast.Program:
        self.context = context or Context()
        paths = ag.find_all_simple_paths(self.api_graph, self.path_cutoff,
                                         self.max_paths)
        exprs = []
        for path in paths:
            path = [n for n in path if not isinstance(n, ag.TypeNode)]
            expr = self.generate_expression_from_path(path)
            exprs.append(expr)

        func_name = "test"
        self.namespace += (func_name,)
        main_func = ast.FunctionDeclaration(
            func_name,
            params=[],
            ret_type=self.bt_factory.get_void_type(),
            body=ast.Block(exprs),
            func_type=ast.FunctionDeclaration.FUNCTION)
        self._add_node_to_parent(self.namespace[:-1], main_func)
        self.namespace = ast.GLOBAL_NAMESPACE
        return ast.Program(self.context, self.language)
