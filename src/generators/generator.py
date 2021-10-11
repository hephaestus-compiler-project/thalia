"""
This file includes the program generator.
TODO: describe the generation steps.

TODOs:
    * Use a probabilities table.
"""
# pylint: disable=too-many-instance-attributes,too-many-arguments,dangerous-default-value
import functools
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Tuple, List, Callable

from src import utils as ut
from src.generators import generators as gens
from src.generators import utils as gu
from src.generators.config import GenConfig
from src.ir import ast, types as tp, type_utils as tu, kotlin_types as kt
from src.ir.context import Context
from src.ir.builtins import BuiltinFactory
from src.ir import BUILTIN_FACTORIES


class Generator():
    # TODO document
    def __init__(self,
                 language=None,
                 options={},
                 logger=None,
                 context=None):
        assert language is not None, "You must specify the language"
        self.language = language
        self.logger = logger
        self.context = context or Context()
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[language]
        self.cfg = GenConfig()
        self.disable_inference_in_closures = options.get(
            "disable_inference_in_closures", False)
        self.disable_var_type_inference = options.get(
            "disable_var_type_inference", False
        )
        self.depth = 1
        self._vars_in_context = defaultdict(lambda: 0)
        self._new_from_class = None
        self.namespace = ('global',)
        self.enable_pecs = not language == 'kotlin'
        self.disable_variance_functions = language == 'kotlin'

        # This flag is used for Java lambdas where local variables references
        # must be final.
        self._inside_java_lambda = False

        self.function_type = type(self.bt_factory.get_function_type())
        self.function_types = self.bt_factory.get_function_types(
            self.cfg.limits.max_functional_params)

        self.ret_builtin_types = self.bt_factory.get_non_nothing_types()
        self.builtin_types = self.ret_builtin_types + \
            [self.bt_factory.get_void_type()]

        # In some case we need to use two namespaces. One for having access
        # to variables from scope, and one for adding new declarations.
        # In most cases one namespace is enough, but in cases like
        # `generate_expr` in `_gen_func_params_with_default` we need both
        # namespaces. To use one namespace we must model scope better.
        # Almost always declaration_namespace is set to None to be ignored
        self.declaration_namespace = None

    ### Entry Point Generators ###

    def generate(self) -> ast.Program:
        """Generate a program.

        It first generates a number `n` top-level declarations,
        and then it generates the main function.
        """
        for _ in ut.random.range(self.cfg.limits.min_top_level,
                                 self.cfg.limits.max_top_level):
            self.gen_top_level_declaration()
        main_func = self.generate_main_func()
        self.namespace = ('global',)
        self.context.add_func(self.namespace, 'main', main_func)
        return ast.Program(self.context, self.language)

    def gen_top_level_declaration(self):
        """Generate a top-level declaration and add it in the context.

        Top-level declarations are defined in the global scope.
        Top-level declarations can be:

        * Variable Declarations
        * Class Declarations
        * Function Declarations

        NOTE that a top-level declaration can generate more top-level
        declarations.
        """
        candidates = [
            (self.gen_variable_decl, self.context.add_var),
            (self.gen_class_decl, self.context.add_class),
            (self.gen_func_decl, self.context.add_func)
        ]
        gen_func, upd_context = ut.random.choice(candidates)
        decl = gen_func()
        upd_context(self.namespace, decl.name, decl)

    def generate_main_func(self) -> ast.FunctionDeclaration:
        """Generate the main function.
        """
        initial_namespace = self.namespace
        self.namespace += ('main', )
        initial_depth = self.depth
        self.depth += 1
        expr = self.generate_expr()
        decls = list(self.context.get_declarations(
            self.namespace, True).values())
        decls = [d for d in decls
                 if not isinstance(d, ast.ParameterDeclaration)]
        body = ast.Block(decls + [expr])
        self.depth = initial_depth
        main_func = ast.FunctionDeclaration(
            "main",
            params=[],
            ret_type=self.bt_factory.get_void_type(),
            body=body,
            func_type=ast.FunctionDeclaration.FUNCTION)
        self.namespace = initial_namespace
        return main_func

    ### Generators ###

    ##### Declarations #####
    # FunctionDeclaration, ParameterDeclaration, ClassDeclaration,
    # FieldDeclaration, and VariableDeclaration

    def gen_func_decl(self,
                      etype:tp.Type=None,
                      not_void=False,
                      class_is_final=False,
                      func_name:str=None,
                      params:List[ast.ParameterDeclaration]=None,
                      abstract=False,
                      is_interface=False,
                      type_params:List[tp.TypeParameter]=None,
                      namespace=None) -> ast.FunctionDeclaration:
        """Generate a function declaration.

        This method is responsible for generating all types of function/methods,
        i.e. functions, class methods, nested functions. Furthermore, it also
        generates parameterized functions.

        Args:
            etype: expected return type.
            not_void: do not return void.
            class_is_final: function of a final class.
            func_name: function name.
            params: list of parameter declarations.
            abstract: function of an abstract class.
            is_interface: function of an interface.
            type_params: list of type parameters for parameterized function.
            namespace: set explicit namespace.

        Returns:
            A function declaration node.
        """
        func_name = func_name or gu.gen_identifier('lower')
        initial_namespace = self.namespace
        if namespace:
            self.namespace = namespace + (func_name,)
        else:
            self.namespace += (func_name,)
        initial_depth = self.depth
        self.depth += 1
        # Check if this function we want to generate is a class method, by
        # checking the name of the outer namespace. If we are in class then
        # the outer namespace begins with capital letter.
        class_method = self.namespace[-2][0].isupper()
        class_method = (False if len(self.namespace) < 2 else
                        self.namespace[-2][0].isupper())
        can_override = abstract or is_interface or (class_method and not
                                    class_is_final and ut.random.bool())
        # Check if this function we want to generate is a nested functions.
        # To do so, we want to find if the function is directly inside the
        # namespace of another function.
        nested_function = (len(self.namespace) > 1 and
                           self.namespace[-2] != 'global' and
                           self.namespace[-2][0].islower())

        prev_inside_java_lamdba = self._inside_java_lambda
        self._inside_java_lambda = nested_function and self.language == "java"
        # Type parameters of functions cannot be variant.
        # Also note that at this point, we do not allow a conflict between
        # type variable names of class and type variable names of functions.
        # TODO consider being less conservative.
        if not nested_function:
            if type_params is not None:
                for t_p in type_params:
                    # We add the types to the context.
                    self.context.add_type(self.namespace, t_p.name, t_p)
            else:
                # Type parameters of parameterized functions can be neither
                # covariant nor contravariant.
                type_params = self.gen_type_params(
                    with_variance=False,
                    blacklist=self._get_type_variable_names(),
                    for_function=True
                ) if ut.random.bool(prob=0.3) else []

        else:
            # Nested functions cannot be parameterized (
            # at least in Groovy, Java), because they are modeled as lambdas.
            type_params = []
        if params is not None:
            for p in params:
                self.context.add_var(self.namespace, p.name, p)
        else:
            params = (
                self._gen_func_params()
                if (
                    ut.random.bool(prob=0.25) or
                    self.language == 'java' or
                    self.language == 'groovy' and is_interface
                )
                else self._gen_func_params_with_default()
            )
        ret_type = self._get_func_ret_type(params, etype, not_void=not_void)
        if is_interface or (abstract and ut.random.bool()):
            body, inferred_type = None, None
        else:
            body, inferred_type = self._gen_func_body(ret_type)
        self._inside_java_lambda = prev_inside_java_lamdba
        self.depth = initial_depth
        self.namespace = initial_namespace
        return ast.FunctionDeclaration(
            func_name, params, ret_type, body,
            func_type=(ast.FunctionDeclaration.CLASS_METHOD
                       if class_method
                       else ast.FunctionDeclaration.FUNCTION),
            is_final=not can_override,
            inferred_type=inferred_type,
            type_parameters=type_params,
        )

    # Where

    def _gen_func_params_with_default(self) -> List[ast.ParameterDeclaration]:
        """Generate function parameters that may include one with default.

        It will generate at most one parameter with a default value.
        """
        has_default = False
        params = []
        for _ in range(ut.random.integer(0, self.cfg.limits.fn.max_params)):
            param = self.gen_param_decl()
            if not has_default:
                has_default = ut.random.bool()
            if has_default:
                prev_decl_namespace = self.declaration_namespace
                self.declaration_namespace = self.namespace
                prev_namespace = self.namespace
                self.namespace = self.namespace[:-1]
                expr = self.generate_expr(param.get_type(), only_leaves=True)
                self.namespace = prev_namespace
                self.declaration_namespace = prev_decl_namespace
                param.default = expr
            params.append(param)
            self.context.add_var(self.namespace, param.name, param)
        return params

    def gen_param_decl(self, etype=None) -> ast.ParameterDeclaration:
        """Generate a function Parameter Declaration.

        Args:
            etype: Parameter type.
        """
        name = gu.gen_identifier('lower')
        param_type = etype or self.select_type(exclude_covariants=True)
        return ast.ParameterDeclaration(name, param_type)

    def gen_class_decl(self,
                       field_type: tp.Type=None,
                       fret_type: tp.Type=None,
                       not_void: bool=False,
                       type_params: List[tp.TypeParameter]=None,
                       class_name: str=None) -> ast.ClassDeclaration:
        """Generate a class declaration.

        It generates all type of classes (regular, abstract, interface),
        and it can also generate parameterized classes.

        Args:
            field_type: At least one field will have this type.
            fret_type: At least one function will return this type.
            not_void: Do not generate functions that return void.
            type_params: List with type parameters.
            class_name: Class name.

        Returns:
            A class declaration node.
        """
        class_name = class_name or gu.gen_identifier('capitalize')
        initial_namespace = self.namespace
        self.namespace += (class_name,)
        initial_depth = self.depth
        self.depth += 1
        class_type = gu.select_class_type(field_type is not None)
        is_final = ut.random.bool() and class_type == \
            ast.ClassDeclaration.REGULAR
        type_params = type_params or self.gen_type_params(
            with_variance=self.language == 'kotlin')
        super_cls_info = self._select_superclass(
            class_type == ast.ClassDeclaration.INTERFACE)
        cls = ast.ClassDeclaration(
            class_name,
            class_type=class_type,
            superclasses=[super_cls_info.super_inst] if super_cls_info else [],
            type_parameters=type_params,
            is_final=is_final
        )
        fields = (
            self.gen_class_fields(cls, super_cls_info, field_type)
            if not cls.is_interface()
            else []
        )
        funcs = self.gen_class_functions(cls, super_cls_info,
                                         not_void, fret_type)
        self.namespace = initial_namespace
        self.depth = initial_depth
        cls.fields = fields
        cls.functions = funcs
        return cls

    # Where

    def _select_superclass(self, only_interfaces: bool) -> gu.SuperClassInfo:
        """
        Select a superclass for a class.

        Args:
            only_interfaces: select an interface.

        Returns:
            SuperClassInfo object which includes: the super class declaration,
                its TypeVarMap, and a SuperClassInstantiation for the selected
                class.
        """
        class_decls = [
            c for c in self.context.get_classes(self.namespace).values()
            if not c.is_final and (c.is_interface() if only_interfaces else True)
        ]
        if not class_decls:
            return None
        class_decl = ut.random.choice(class_decls)
        if class_decl.is_parameterized():
            cls_type, type_var_map = tu.instantiate_type_constructor(
                class_decl.get_type(),
                self.get_types(exclude_covariants=True,
                               exclude_contravariants=True),
                enable_pecs=self.enable_pecs,
                disable_variance_functions=self.disable_variance_functions,
                only_regular=True,
            )
        else:
            cls_type, type_var_map = class_decl.get_type(), {}
        con_args = None if class_decl.is_interface() else []
        for f in class_decl.fields:
            field_type = tp.substitute_type(f.get_type(), type_var_map)
            con_args.append(self.generate_expr(field_type,
                                               only_leaves=True))
        return gu.SuperClassInfo(
            class_decl,
            type_var_map,
            ast.SuperClassInstantiation(cls_type, con_args)
        )

    # And

    def gen_class_fields(self,
                         curr_cls: ast.ClassDeclaration,
                         super_cls_info: gu.SuperClassInfo,
                         field_type: tp.Type=None
                        ) -> List[ast.FieldDeclaration]:
        """Generate fields for a class.

        It also adds the fields in the context.

        Args:
            curr_cls: Current class declaration.
            super_cls_info: SuperClassInstantiation for curr_cls
            field_type: At least one field will have this type.

        Returns:
            A list of field declarations
        """
        max_fields = self.cfg.limits.cls.max_fields - 1 if field_type \
            else self.cfg.limits.cls.max_fields
        fields = []
        if field_type:
            self._add_field_to_class(
                self.gen_field_decl(field_type, curr_cls.is_final), fields)
        if not super_cls_info:
            for _ in range(ut.random.integer(0, max_fields)):
                self._add_field_to_class(
                    self.gen_field_decl(class_is_final=curr_cls.is_final),
                    fields)
        else:
            overridable_fields = super_cls_info.super_cls \
                .get_overridable_fields()
            k = ut.random.integer(0, min(max_fields, len(overridable_fields)))
            if overridable_fields:
                chosen_fields = ut.random.sample(overridable_fields, k=k)
                for f in chosen_fields:
                    field_type = tp.substitute_type(
                        f.get_type(), super_cls_info.type_var_map)
                    new_f = self.gen_field_decl(field_type, curr_cls.is_final)
                    new_f.name = f.name
                    new_f.override = True
                    new_f.is_final = f.is_final
                    self._add_field_to_class(new_f, fields)
                max_fields = max_fields - len(chosen_fields)
            if max_fields < 0:
                return fields
            for _ in range(ut.random.integer(0, max_fields)):
                self._add_field_to_class(
                    self.gen_field_decl(class_is_final=curr_cls.is_final),
                    fields)
        return fields

    # Where

    def _add_field_to_class(self, field, fields):
        """Add a field to context and fields.
        """
        fields.append(field)
        self.context.add_var(self.namespace, field.name, field)

    # And

    def gen_class_functions(self,
                            curr_cls, super_cls_info,
                            not_void=False,
                            fret_type=None) -> List[ast.FunctionDeclaration]:
        """Generate methods for a class.

        If the method has a superclass, then it will try to implement any
        method that must be implemented (e.g., abstract methods in regular
        classes).

        Args:
            curr_cls: Current Class declaration
            super_cls_info: SuperClassInstantiation for curr_cls
            not_void: Do not create methods that return void.
            fret_type: At least one method will return this type.
        """
        funcs = []
        max_funcs = self.cfg.limits.cls.max_funcs - 1 if fret_type \
            else self.cfg.limits.cls.max_funcs
        abstract = not curr_cls.is_regular()
        if fret_type:
            self._add_func_to_class(
                self.gen_func_decl(fret_type, not_void=not_void,
                                   class_is_final=curr_cls.is_final,
                                   abstract=abstract,
                                   is_interface=curr_cls.is_interface()),
                funcs)
        if not super_cls_info:
            for _ in range(ut.random.integer(0, max_funcs)):
                self._add_func_to_class(
                    self.gen_func_decl(not_void=not_void,
                                       class_is_final=curr_cls.is_final,
                                       abstract=abstract,
                                       is_interface=curr_cls.is_interface()),
                    funcs)
        else:
            abstract_funcs = []
            class_decls = self.context.get_classes(self.namespace).values()
            if curr_cls.is_regular():
                abstract_funcs = super_cls_info.super_cls\
                    .get_abstract_functions(class_decls)
                for f in abstract_funcs:
                    self._add_func_to_class(
                        self._gen_func_from_existing(
                            f,
                            super_cls_info.type_var_map,
                            curr_cls.is_final,
                            curr_cls.is_interface()
                        ),
                        funcs
                    )
                max_funcs = max_funcs - len(abstract_funcs)
            overridable_funcs = super_cls_info.super_cls \
                .get_overridable_functions()
            abstract_funcs = {f.name for f in abstract_funcs}
            overridable_funcs = [f for f in overridable_funcs
                                 if f.name not in abstract_funcs]
            len_over_f = len(overridable_funcs)
            if len_over_f > max_funcs:
                return funcs
            k = ut.random.integer(0, min(max_funcs, len_over_f))
            chosen_funcs = (
                []
                if not max_funcs or curr_cls.is_interface()
                else ut.random.sample(overridable_funcs, k=k)
            )
            for f in chosen_funcs:
                self._add_func_to_class(
                    self._gen_func_from_existing(f,
                                                 super_cls_info.type_var_map,
                                                 curr_cls.is_final,
                                                 curr_cls.is_interface()),
                    funcs)
            max_funcs = max_funcs - len(chosen_funcs)
            if max_funcs < 0:
                return funcs
            for _ in range(ut.random.integer(0, max_funcs)):
                self._add_func_to_class(
                    self.gen_func_decl(not_void=not_void,
                                       class_is_final=curr_cls.is_final,
                                       abstract=abstract,
                                       is_interface=curr_cls.is_interface()),
                    funcs)
        return funcs

    # Where

    def _add_func_to_class(self, func, funcs):
        """Add a function to context and to funcs (list of class methods).
        """
        funcs.append(func)
        self.context.add_func(self.namespace, func.name, func)

    # And

    def _gen_func_from_existing(self,
                                func: ast.FunctionDeclaration,
                                type_var_map: tu.TypeVarMap,
                                class_is_final: bool,
                                is_interface: bool) -> ast.FunctionDeclaration:
        """Generate a method that overrides an existing method.

        Args:
            func: Method to override.
            type_var_map: TypeVarMap of func
            class_is_final: is current class final.
            is_interface: is current class an interface.

        Returns:
            A function declaration.
        """
        params = deepcopy(func.params)
        type_params, substituted_type_params = \
            self._gen_type_params_from_existing(func, type_var_map)
        type_param_names = [t.name for t in type_params]
        ret_type = func.ret_type
        for p in params:
            sub = False
            sub_type_map = {
                k: v for k, v in type_var_map.items()
                if k.name not in type_param_names
            }
            old = p.get_type()
            p.param_type = tp.substitute_type(p.get_type(), sub_type_map)
            sub = old != p.get_type()
            if not sub:
                p.param_type = tp.substitute_type(p.get_type(),
                                                  substituted_type_params)
            p.default = None
        sub = False
        sub_type_map = {
            k: v for k, v in type_var_map.items()
            if k.name not in type_param_names
        }
        old = ret_type
        ret_type = tp.substitute_type(ret_type, sub_type_map)
        sub = old != ret_type
        if not sub:
            ret_type = tp.substitute_type(ret_type, substituted_type_params)
        new_func = self.gen_func_decl(func_name=func.name, etype=ret_type,
                                      not_void=False,
                                      class_is_final=class_is_final,
                                      params=params,
                                      is_interface=is_interface,
                                      type_params=type_params)
        if func.body is None:
            new_func.is_final = False
        new_func.override = True
        return new_func

    # Where

    def _gen_type_params_from_existing(self,
                                       func: ast.FunctionDeclaration,
                                       type_var_map
                                      ) -> (List[tp.TypeParameter], tu.TypeVarMap):
        """Gen type parameters for a function that overrides a parameterized
            function.

        Args:
            func: Function to override.
            type_var_map: TypeVarMap of func.

        Returns:
            A list of available type parameters, and TypeVarMap for the type
            parameters of func
        """
        if not func.type_parameters:
            return [], {}
        substituted_type_params = {}
        curr_type_vars = self._get_type_variable_names()
        func_type_vars = [t.name for t in func.type_parameters]
        class_type_vars = [t for t in curr_type_vars
                           if t not in func_type_vars]
        blacklist = func_type_vars + curr_type_vars + list(type_var_map.keys())
        new_type_params = []
        for t_param in func.type_parameters:
            # Here, we substitute the bound of an overriden parameterized
            # function based on the type arguments of the superclass.
            new_type_param = deepcopy(t_param)
            if t_param.name in curr_type_vars:
                # The child class contains a type variable that has the
                # same name with a type variable of the overriden function.
                # So we change the name of the function's type variable to
                # avoid the conflict.
                new_name = ut.random.caps(blacklist=blacklist)
                func_type_vars.append(new_name)
                blacklist.append(new_name)
                new_type_param.name = new_name
                substituted_type_params[t_param] = new_type_param

            if new_type_param.bound is not None:
                sub = False
                sub_type_map = {
                    k: v for k, v in type_var_map.items()
                    if k.name not in func_type_vars \
                    or k.name not in class_type_vars
                }
                old = new_type_param.bound
                bound = tp.substitute_type(new_type_param.bound,
                                           sub_type_map)
                sub = old != bound

                if not sub:
                    bound = tp.substitute_type(bound, substituted_type_params)
                new_type_param.bound = bound
            new_type_params.append(new_type_param)
        return new_type_params, substituted_type_params

    def gen_field_decl(self, etype=None,
                       class_is_final=True) -> ast.FieldDeclaration:
        """Generate a class Field Declaration.

        Args:
            etype: Field type.
            class_is_final: Is the class final.
        """
        name = gu.gen_identifier('lower')
        can_override = not class_is_final and ut.random.bool()
        is_final = ut.random.bool()
        field_type = etype or self.select_type(exclude_contravariants=True,
                                               exclude_covariants=not is_final)
        return ast.FieldDeclaration(name, field_type, is_final=is_final,
                                    can_override=can_override)

    def gen_variable_decl(self,
                          etype=None,
                          only_leaves=False,
                          expr=None) -> ast.VariableDeclaration:
        """Generate a Variable Declaration.

        Args:
            etype: the type of the variable.
            only_leaves: do not generate new leaves except from `expr`.
            expr: an expression to assign to the variable.

        Returns:
            A Variable Declaration
        """
        var_type = etype if etype else self.select_type()
        initial_depth = self.depth
        self.depth += 1
        # NOTE maybe we should disable sam coercion for Kotlin
        # the following code does not compile
        # fun interface FI { fun foo(p: Int): Long }
        # var v: FI = {x: Int -> x.toLong()}
        expr = expr or self.generate_expr(var_type, only_leaves,
                                          sam_coercion=True)
        self.depth = initial_depth
        is_final = ut.random.bool()
        # We cannot set ? extends X as the type of a variable.
        vtype = var_type.get_bound_rec() if var_type.is_wildcard() else \
            var_type
        return ast.VariableDeclaration(
            gu.gen_identifier('lower'),
            expr=expr,
            is_final=is_final,
            var_type=vtype,
            inferred_type=var_type)

    ##### Expressions #####

    def generate_expr(self,
                      expr_type: tp.Type=None,
                      only_leaves=False,
                      subtype=True,
                      exclude_var=False,
                      gen_bottom=False,
                      sam_coercion=False) -> ast.Expr:
        """Generate an expression.

        This function could produce new nodes external to the generated
        expression as a side effect. For instance, it could generate new
        variable declarations.

        Args:
            expr_type: The type that the expression should have.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated expression could be a subtype
                of `expr_type`.
            exclude_var: if this option is false, then it could assign the
                generated expression into a variable, and return that
                variable reference.
            gen_bottom: Generate a bottom constant.
            sam_coercion: Enable sam coercion.

        Returns:
            The generated expression.
        """
        if gen_bottom:
            return ast.BottomConstant(None)
        find_subtype = (
            expr_type and
            subtype and expr_type != self.bt_factory.get_void_type()
            and ut.random.bool()
        )
        expr_type = expr_type or self.select_type()
        if find_subtype:
            subtypes = tu.find_subtypes(expr_type, self.get_types(),
                                        include_self=True, concrete_only=True)
            expr_type = ut.random.choice(subtypes)
        generators = self.get_generators(expr_type, only_leaves, subtype,
                                         exclude_var, sam_coercion=sam_coercion)
        expr = ut.random.choice(generators)(expr_type)
        # Make a probablistic choice, and assign the generated expr
        # into a variable, and return that variable reference.
        gen_var = (
            not only_leaves and
            expr_type != self.bt_factory.get_void_type() and
            self._vars_in_context[self.namespace] < self.cfg.limits.max_var_decls and
            ut.random.bool()
        )
        if gen_var:
            self._vars_in_context[self.namespace] += 1
            var_decl = self.gen_variable_decl(expr_type, only_leaves,
                                              expr=expr)
            self.context.add_var(self.namespace, var_decl.name, var_decl)
            expr = ast.Variable(var_decl.name)
        return expr

    # pylint: disable=unused-argument
    def gen_assignment(self,
                       expr_type: tp.Type,
                       only_leaves=False,
                       subtype=True) -> ast.Assignment:
        """Generate an assignment expressions.

        Args:
            expr_type: The value that the assignment expression should hold.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated expression could be a subtype
                of `expr_type`.
        """
        # Get all all non-final variables for performing the assignment.
        variables = self._get_assignable_vars()
        initial_depth = self.depth
        self.depth += 1
        if not variables:
            # Ok, it's time to find a class with non-final fields,
            # generate an object of this class, and perform the assignment.
            res = self._get_classes_with_assignable_fields()
            if res:
                expr_type, field = res
                variables = [(self.generate_expr(expr_type,
                                                 only_leaves, subtype), field)]
        if not variables:
            # Nothing of the above worked, so generate a 'var' variable,
            # and perform the assignment
            etype = self.select_type(exclude_covariants=True,
                                     exclude_contravariants=True)
            self._vars_in_context[self.namespace] += 1
            # If there are not variable declarations that match our criteria,
            # we have to create a new variable declaration.
            var_decl = self.gen_variable_decl(etype, only_leaves)
            var_decl.is_final = False
            var_decl.var_type = var_decl.get_type()
            self.context.add_var(self.namespace, var_decl.name, var_decl)
            self.depth = initial_depth
            return ast.Assignment(var_decl.name,
                                  self.generate_expr(var_decl.get_type(),
                                                     only_leaves, subtype))
        receiver, variable = ut.random.choice(variables)
        self.depth = initial_depth
        gen_bottom = (
            variable.get_type().is_wildcard() or
            (
                variable.get_type().is_parameterized() and
                variable.get_type().has_wildcards()
            )
        )
        return ast.Assignment(variable.name, self.generate_expr(
            variable.get_type(), only_leaves, subtype, gen_bottom=gen_bottom),
                              receiver=receiver,)

    # Where

    def _get_assignable_vars(self) -> List[ast.Variable]:
        """Get all non-final variables in context.

        Note that variables inside lambdas in Java should be either final, or
        effectively final.
        """
        variables = []
        for var in self.context.get_vars(self.namespace).values():
            if self._inside_java_lambda:
                continue
            if not getattr(var, 'is_final', True):
                variables.append((None, var))
                continue
            var_type = self._get_var_type_to_search(var.get_type())
            if not var_type:
                continue
            if isinstance(getattr(var_type, 't_constructor', None),
                          self.function_type):
                continue
            cls, type_var_map = self._get_class(var_type)
            for field in cls.fields:
                # Ok here we create a new field whose type corresponds
                # to the type argument with which the class 'c' is
                # instantiated.
                field_sub = ast.FieldDeclaration(
                    field.name,
                    field_type=tp.substitute_type(field.get_type(),
                                                  type_var_map)
                )
                if not field.is_final:
                    variables.append((ast.Variable(var.name), field_sub))
        return variables

    # And

    def _get_classes_with_assignable_fields(self):
        """Get classes with non-final fields.

        Returns:
            A list that contains tuples of expressions that produce objects
            of a class, and field declarations.
        """
        classes = []
        class_decls = self.context.get_classes(self.namespace).values()
        for c in class_decls:
            for field in c.fields:
                if not field.is_final:
                    classes.append((c, field))
        assignable_types = []
        for c, f in classes:
            t, type_var_map = c.get_type(), {}
            if t.is_type_constructor():
                variance_choices = {
                    t_param: (False, True)
                    for t_param in t.type_parameters
                }
                t, type_var_map = tu.instantiate_type_constructor(
                    t, self.get_types(exclude_arrays=True),
                    variance_choices=variance_choices,
                    disable_variance_functions=self.disable_variance_functions,
                    enable_pecs=self.enable_pecs)
                # Ok here we create a new field whose type corresponds
                # to the type argument with which the class 'c' is
                # instantiated.
                f = ast.FieldDeclaration(
                    f.name,
                    field_type=tp.substitute_type(f.get_type(),
                                                  type_var_map)
                )
            assignable_types.append((t, f))

        if not assignable_types:
            return None
        return ut.random.choice(assignable_types)

    def gen_field_access(self,
                         etype: tp.Type,
                         only_leaves=False,
                         subtype=True) -> ast.FieldAccess:
        """Generate a field access expression.

        Args:
            expr_type: The value that the field access should return.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated expression could be a subtype
                of `expr_type`.
        """
        initial_depth = self.depth
        self.depth += 1
        objs = self._get_matching_objects(etype, subtype, 'fields')
        if not objs:
            type_f = self._get_matching_class(etype, subtype, 'fields')
            if type_f is None:
                type_f = self._gen_matching_class(
                    etype, 'fields', not_void=True,
                )
            receiver = self.generate_expr(type_f.receiver_t, only_leaves)
            objs.append((receiver, None, type_f.attr_decl))
        objs = [(r, f) for r, _, f in objs]
        receiver, attr = ut.random.choice(objs)
        self.depth = initial_depth
        return ast.FieldAccess(receiver, attr.name)

    def gen_variable(self,
                     etype: tp.Type,
                     only_leaves=False,
                     subtype=True) -> ast.Variable:
        """Generate a variable.

        First, it searches for all variables in the scope. In case it doesn't
        find any variable of etype, then it generates one.

        Args:
            expr_type: The type that the variable should have.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated variable could be a subtype
                of `expr_type`.
        """
        # Get all variables declared in the current namespace or
        # the outer namespace.
        variables = self.context.get_vars(self.namespace).values()
        # Case where we want only final variables
        # Or variables declared in the nested function
        if self._inside_java_lambda:
            variables = list(filter(
                lambda v: (getattr(v, 'is_final', False) or v not in
                    self.context.get_vars(self.namespace[:-1]).values()),
                variables))
        # If we need to use a variable of a specific types, then filter
        # all variables that match this specific type.
        if subtype:
            fun = lambda v, t: v.get_type().is_assignable(t)
        else:
            fun = lambda v, t: v.get_type() == t
        variables = [v for v in variables if fun(v, etype)]
        if not variables:
            return self.generate_expr(etype, only_leaves=only_leaves,
                                      subtype=subtype, exclude_var=True)
        varia = ut.random.choice([v.name for v in variables])
        return ast.Variable(varia)

    def gen_array_expr(self,
                       expr_type: tp.Type,
                       only_leaves=False,
                       subtype=True) -> ast.ArrayExpr:
        """Generate an array expression

        Args:
            expr_type: The type of the array
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated array could be a subtype
                of `expr_type`.
        """
        arr_len = ut.random.integer(0, 3)
        etype = expr_type.type_args[0]
        exprs = [
            self.generate_expr(etype, only_leaves=only_leaves, subtype=subtype)
            for _ in range(arr_len)
        ]
        return ast.ArrayExpr(expr_type, arr_len, exprs)

    # pylint: disable=unused-argument
    def gen_equality_expr(self,
                          expr_type=None,
                          only_leaves=False) -> ast.EqualityExpr:
        """Generate an equality expression

        It generates two additional expression for performing the comparison
        between them.

        Args:
            expr_type: exists for compatibility reasons.
            only_leaves: do not generate new leaves except from `expr`.
        """
        initial_depth = self.depth
        self.depth += 1
        exclude_function_types = self.language == 'java'
        etype = self.select_type(exclude_function_types=exclude_function_types)
        op = ut.random.choice(ast.EqualityExpr.VALID_OPERATORS[self.language])
        e1 = self.generate_expr(etype, only_leaves, subtype=False)
        e2 = self.generate_expr(etype, only_leaves, subtype=False)
        self.depth = initial_depth
        return ast.EqualityExpr(e1, e2, op)

    # pylint: disable=unused-argument
    def gen_logical_expr(self,
                         expr_type=None,
                         only_leaves=False) -> ast.LogicalExpr:
        """Generate a logical expression

        It generates two additional expression for the logical expression.

        Args:
            expr_type: exists for compatibility reasons.
            only_leaves: do not generate new leaves except from `expr`.
        """
        initial_depth = self.depth
        self.depth += 1
        op = ut.random.choice(ast.LogicalExpr.VALID_OPERATORS[self.language])
        e1 = self.generate_expr(self.bt_factory.get_boolean_type(),
                                only_leaves)
        e2 = self.generate_expr(self.bt_factory.get_boolean_type(),
                                only_leaves)
        self.depth = initial_depth
        return ast.LogicalExpr(e1, e2, op)

    # pylint: disable=unused-argument
    def gen_comparison_expr(self,
                            expr_type=None,
                            only_leaves=False) -> ast.ComparisonExpr:
        """Generate a comparison expression

        It generates two additional expression for performing the comparison
        between them.
        It supports only built-in types.

        Args:
            expr_type: exists for compatibility reasons.
            only_leaves: do not generate new leaves except from `expr`.
        """
        valid_types = [
            self.bt_factory.get_string_type(),
            self.bt_factory.get_boolean_type(),
            self.bt_factory.get_double_type(),
            self.bt_factory.get_char_type(),
            self.bt_factory.get_float_type(),
            self.bt_factory.get_integer_type(),
            self.bt_factory.get_byte_type(),
            self.bt_factory.get_short_type(),
            self.bt_factory.get_long_type(),
            self.bt_factory.get_big_decimal_type(),
            self.bt_factory.get_big_integer_type(),
        ]
        number_types = self.bt_factory.get_number_types()
        e2_types = {
            self.bt_factory.get_string_type(): [
                self.bt_factory.get_string_type()
            ],
            self.bt_factory.get_boolean_type(): [
                self.bt_factory.get_boolean_type()
            ],
            self.bt_factory.get_double_type(): number_types,
            self.bt_factory.get_big_decimal_type(): number_types,
            self.bt_factory.get_char_type(): [
                self.bt_factory.get_char_type()
            ],
            self.bt_factory.get_float_type(): number_types,
            self.bt_factory.get_integer_type(): number_types,
            self.bt_factory.get_big_integer_type(): number_types,
            self.bt_factory.get_byte_type(): number_types,
            self.bt_factory.get_short_type(): number_types,
            self.bt_factory.get_long_type(): number_types
        }
        initial_depth = self.depth
        self.depth += 1
        op = ut.random.choice(
            ast.ComparisonExpr.VALID_OPERATORS[self.language])
        e1_type = ut.random.choice(valid_types)
        e2_type = ut.random.choice(e2_types[e1_type])
        e1 = self.generate_expr(e1_type, only_leaves)
        e2 = self.generate_expr(e2_type, only_leaves)
        self.depth = initial_depth
        if self.language == 'java' and e1_type.name in ('Boolean', 'String'):
            op = ut.random.choice(
                ast.EqualityExpr.VALID_OPERATORS[self.language])
            return ast.EqualityExpr(e1, e2, op)
        return ast.ComparisonExpr(e1, e2, op)

    def gen_conditional(self,
                        etype: tp.Type,
                        only_leaves=False,
                        subtype=True) -> ast.Conditional:
        """Generate a conditional expression.

        It generates 3 sub expressions, one for each branch, and one for
        the conditional.

        Args:
            etype: type for each sub expression.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the sub expressions could be a subtype of
                `etype`.
        """
        initial_depth = self.depth
        self.depth += 3
        cond = self.generate_expr(self.bt_factory.get_boolean_type(),
                                  only_leaves)
        true_expr = self.generate_expr(etype, only_leaves, subtype)
        false_expr = self.generate_expr(etype, only_leaves, subtype)
        self.depth = initial_depth
        return ast.Conditional(cond, true_expr, false_expr)

    def gen_is_expr(self,
                    expr_type: tp.Type,
                    only_leaves=False,
                    subtype=True) -> ast.Conditional:
        """Generate an is expression.

        If it cannot detect a subtype for the expr_type, then it just generates
        a new expression of expr_type.

        Args:
            expr_type: type to smart cast.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the sub expressions could be a subtype of
                `expr_type`.

        Returns:
            A conditional with is.
        """
        def _get_extra_decls(namespace):
            return [
                v
                for v in self.context.get_declarations(
                    namespace, only_current=True).values()
                if (isinstance(v, (ast.VariableDeclaration,
                                  ast.FunctionDeclaration)))
            ]

        final_vars = [
            v
            for v in self.context.get_vars(self.namespace).values()
            if (
                # We can smart cast variable that are final, have explicit
                # types, and are not overridable.
                getattr(v, 'is_final', True) and
                not v.is_type_inferred and
                not getattr(v, 'can_override', True)
            )
        ]
        if not final_vars:
            return self.generate_expr(expr_type, only_leaves=True,
                                      subtype=subtype)
        prev_depth = self.depth
        self.depth += 3
        var = ut.random.choice(final_vars)
        var_type = var.get_type()
        subtypes = tu.find_subtypes(var_type, self.get_types(),
                                    include_self=False, concrete_only=True)
        subtypes = self._filter_subtypes(subtypes, var_type)
        if not subtypes:
            return self.generate_expr(expr_type, only_leaves=True,
                                      subtype=subtype)

        subtype = ut.random.choice(subtypes)
        initial_decls = _get_extra_decls(self.namespace)
        prev_namespace = self.namespace
        self.namespace += ('true_block',)
        # Here, we create a 'virtual' variable declaration inside the
        # namespace of the block corresponding to the true branch. This
        # variable has the same name with the variable that appears in
        # the left-hand side of the 'is' expression, but its type is the
        # selected subtype.
        self.context.add_var(self.namespace, var.name,
            ast.VariableDeclaration(
                var.name,
                ast.BottomConstant(var.get_type()),
                var_type=subtype))
        true_expr = self.generate_expr(expr_type)
        # We pop the variable from context. Because it's no longer used.
        self.context.remove_var(self.namespace, var.name)
        extra_decls_true = [v for v in _get_extra_decls(self.namespace)
                            if v not in initial_decls]
        if extra_decls_true:
            true_expr = ast.Block(extra_decls_true + [true_expr],
                                  is_func_block=False)
        self.namespace = prev_namespace + ('false_block',)
        false_expr = self.generate_expr(expr_type, only_leaves=only_leaves,
                                        subtype=subtype)
        extra_decls_false = [v for v in _get_extra_decls(self.namespace)
                             if v not in initial_decls]
        if extra_decls_false:
            false_expr = ast.Block(extra_decls_false + [false_expr],
                                   is_func_block=False)
        self.namespace = prev_namespace
        self.depth = prev_depth
        return ast.Conditional(
            ast.Is(ast.Variable(var.name), subtype),
            true_expr,
            false_expr
        )

    # Where

    def _filter_subtypes(self, subtypes, initial_type):
        """Filter out types that cannot be smart casted.

        The types that cannot be smart casted are Type Variables and
        Parameterized Types. The only exception is Kotlin in which we can
        smart cast parameterized types.
        """
        new_subtypes = []
        for t in subtypes:
            if t.is_type_var():
                continue
            if self.language != 'kotlin':
                # We can't check the instance of a parameterized type due
                # to type erasure. The only exception is Kotlin, see below.
                if not t.is_parameterized():
                    new_subtypes.append(t)
                continue

            # In Kotlin, you can smart cast a parameterized type like the
            # following.

            # class A<T>
            # class B<T> extends A<T>
            # fun test(x: A<String>) {
            #   if (x is B) {
            #      // the type of x is B<String> here.
            #   }
            # }
            if t.is_parameterized():
                t_con = t.t_constructor
                if t_con.is_subtype(initial_type):
                    continue
            new_subtypes.append(t)
        return new_subtypes

    def gen_lambda(self,
                   etype: tp.Type=None,
                   not_void=False,
                   shadow_name: str=None,
                   params: List[ast.ParameterDeclaration]=None
                  ) -> ast.Lambda:
        """Generate a lambda expression.

        Lambdas have shadow names that we can use them in the context to
        retrieve them.

        Args:
            etype: return type of the lambda.
            not_void: the lambda should not return void.
            shadow_name: give a specific shadow name.
            params: parameters for the lambda.
        """
        shadow_name = shadow_name or gu.gen_identifier('lower')
        initial_namespace = self.namespace
        self.namespace += (shadow_name,)
        initial_depth = self.depth
        self.depth += 1

        prev_inside_java_lamdba = self._inside_java_lambda
        self._inside_java_lambda = self.language == "java"

        params = params if params is not None else self._gen_func_params()
        ret_type = self._get_func_ret_type(params, etype, not_void=not_void)
        body, _ = self._gen_func_body(ret_type)
        param_types = [p.param_type for p in params]
        signature = tp.ParameterizedType(
            self.bt_factory.get_function_type(len(params)),
            param_types + [ret_type])

        res = ast.Lambda(shadow_name, params, ret_type, body, signature)

        self.depth = initial_depth
        self.namespace = initial_namespace
        self._inside_java_lambda = prev_inside_java_lamdba

        # Add to context
        if self.declaration_namespace:
            namespace = self.declaration_namespace
        else:
            namespace = self.namespace
        self.context.add_lambda(namespace, shadow_name, res)

        return res

    def gen_func_ref(self, etype):
        """Generate a function declaration and then a function reference for it.

        Args:
            etype: signature of the function to generate.
        """
        def check_targ(targ):
            """Return false if targ is TypeParameter or WildCardType.
            """
            if isinstance(targ, tp.ParameterizedType):
                return all(check_targ(t) for t in targ.type_args)
            if isinstance(targ, tp.TypeParameter):
                return False
            if (isinstance(targ, tp.WildCardType) and
                    isinstance(targ.bound, tp.TypeParameter)):
                return False
            return True
        # NOTE to handle the case where a type argument is a type parameter,
        # we can either create a parameterized function or create a method
        # to the current class.
        # In the second case, we can use `this` or we can create
        # a new object as a receiver.
        if any(not check_targ(targ) for targ in etype.type_args):
            return None
        params = [self.gen_param_decl(t) for t in etype.type_args[:-1]]
        ret_type = etype.type_args[-1]
        func_decl = self.gen_func_decl(
            etype=ret_type, params=params, namespace=('global',)
        )
        self.context.add_func(('global',), func_decl.name, func_decl)
        return ast.FunctionReference(func_decl.name, None)

    def gen_func_call(self,
                      etype: tp.Type,
                      only_leaves=False,
                      subtype=True) -> ast.FunctionCall:
        """Generate a function call.

        The function call could be either a normal function call, or a function
        call from a function reference.

        Args:
            etype: the type that the function call should return.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The returned type could be a subtype of `etype`.

        Returns:
            A function call.
        """
        if ut.random.bool():
            ref_call = self._gen_func_call_ref(etype, only_leaves, subtype)
            if ref_call:
                return ref_call
        return self._gen_func_call(etype, only_leaves, subtype)

    # gen_func_call Where

    def _gen_func_call(self,
                       etype: tp.Type,
                       only_leaves=False,
                       subtype=True) -> ast.FunctionCall:
        """Generate a function call.

        Args:
            etype: the type that the function call should return.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The returned type could be a subtype of `etype`.
        """
        funcs = self._get_function_declarations(etype, subtype)
        if not funcs:
            type_fun = self._get_matching_class(etype, subtype, 'functions')
            if type_fun is None:
                # Here, we generate a function or a class containing a function
                # whose return type is 'etype'.
                type_fun = self._gen_matching_func(etype, not_void=True)
            receiver = (
                None if type_fun.receiver_t is None
                else self.generate_expr(type_fun.receiver_t, only_leaves)
            )
            funcs.append((receiver, type_fun.receiver_inst,
                          type_fun.attr_decl, type_fun.attr_inst))
        receiver, params_map, func, func_type_map = ut.random.choice(funcs)
        params_map.update(func_type_map or {})
        args = []
        initial_depth = self.depth
        self.depth += 1
        for param in func.params:
            expr_type = tp.substitute_type(param.get_type(), params_map)
            gen_bottom = expr_type.is_wildcard() or (
                expr_type.is_parameterized() and expr_type.has_wildcards())
            if not param.vararg:
                arg = self.generate_expr(expr_type, only_leaves,
                                         gen_bottom=gen_bottom)
                if param.default:
                    if self.language == 'kotlin' and ut.random.bool():
                        # Randomly skip some default arguments.
                        args.append(ast.CallArgument(arg, name=param.name))
                else:
                    args.append(ast.CallArgument(arg))

            else:
                # This param is a vararg, so provide a random number of
                # arguments.
                for _ in range(ut.random.integer(0, 3)):
                    args.append(ast.CallArgument(
                        self.generate_expr(
                            expr_type.type_args[0],
                            only_leaves,
                            gen_bottom=gen_bottom)))
        self.depth = initial_depth
        type_args = (
            []
            if not func.is_parameterized()
            else [
                func_type_map[t_param]
                for t_param in func.type_parameters
            ]
        )
        return ast.FunctionCall(func.name, args, receiver,
                                type_args=type_args)

    # Where

    # TODO use AttrAccessInfo
    def _get_function_declarations(self, etype: tp.Type, subtype: bool) -> \
            List[Tuple[ast.Expr, ast.Declaration]]:
        """Get all available function declarations.

        This function searches functions in the current scope that return
        `etype`, and then it also searches for receivers whose class has a
        function that return `etype`.

        Args:
            etype: the return type for the function to find
                return that type.
            subtype: The return type of the function could be a subtype of
                `etype`.

        Returns:
            A list that contains tuples of receivers (Variable or None)
            and function declarations.
        """
        functions = []
        # First find all top-level functions or methods included
        # in the current class.
        for func in self.context.get_funcs(self.namespace).values():
            cond = (
                func.get_type() != self.bt_factory.get_void_type() and
                func.get_type().is_assignable(etype)
                if subtype else func.get_type() == etype
            )
            # The receiver object for this kind of functions is None.
            if not cond:
                continue

            if func.is_parameterized() and func.is_class_method():
                # TODO: Consider being less conservative.
                # The problem is when the class method is parameterized,
                # the receiver is parameterized, and the type parameters
                # of functions have bounds corresponding to the type parameters
                # of class.
                continue

            type_var_map = {}
            if func.is_parameterized():
                type_var_map = tu.instantiate_parameterized_function(
                    func.type_parameters, self.get_types(),
                    only_regular=True)

            # Nice to have:  add `this` explicitly as the receiver in methods
            # of current class.
            functions.append((None, {}, func, type_var_map))
        return functions + self._get_matching_objects(etype, subtype,
                                                      'functions')

    # And

    def _gen_matching_func(self,
                           etype: tp.Type,
                           not_void=False) -> gu.AttrAccessInfo:
        """ Generate a function or a class containing a function whose return
        type is 'etype'.

        Args:
            etype: the targeted return type.
            not_void: do not create functions that return void.
        """
        # Randomly choose to generate a function or a class method.
        if ut.random.bool():
            initial_namespace = self.namespace
            # If the given type 'etype' is a type parameter, then the
            # function we want to generate should be in the current namespace,
            # so that the type parameter is accessible.
            self.namespace = (
                self.namespace
                if ut.random.bool() or etype.has_type_variables()
                else ast.GLOBAL_NAMESPACE
            )
            # Generate a function
            func = self.gen_func_decl(etype, not_void=not_void)
            self.context.add_func(self.namespace, func.name, func)
            self.namespace = initial_namespace
            func_type_var_map = {}
            if func.is_parameterized():
                func_type_var_map = tu.instantiate_parameterized_function(
                    func.type_parameters, self.get_types(),
                    only_regular=True, type_var_map={})
            return gu.AttrAccessInfo(None, {}, func, func_type_var_map)
        # Generate a class containing the requested function
        return self._gen_matching_class(etype, 'functions')

    # gen_func_call And

    def _gen_func_call_ref(self,
                           etype: tp.Type,
                           only_leaves=False,
                           subtype=False) -> ast.FunctionCall:
        """Generate a function call from a reference.

        Args:
            etype: the type that the function call should return.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The returned type could be a subtype of `etype`.
        """
        # Tuple of signature and name
        refs = []
        # TODO using existing functions
        variables = self.context.get_vars(self.namespace).values()
        if self._inside_java_lambda:
            variables = list(filter(
                lambda v: (getattr(v, 'is_final', False) or (
                    v not in self.context.get_vars(self.namespace[:-1]).values())),
                variables))
        for var in variables:
            var_type = var.get_type()
            if not getattr(var_type, 'is_function_type', lambda: False)():
                continue
            ret_type = var_type.type_args[-1]
            # NOTE not very frequent (~4%), we could generate a function or
            # an appropriate lambda and use it directly.
            if (subtype and ret_type.is_subtype(etype)) or ret_type == etype:
                refs.append((var_type, var.name))
        if not refs:
            return None
        signature, name = ut.random.choice(refs)

        # Generate arguments
        args = []
        initial_depth = self.depth
        self.depth += 1
        for param_type in signature.type_args[:-1]:
            gen_bottom = param_type.is_wildcard() or (
                param_type.is_parameterized() and param_type.has_wildcards())
            arg = self.generate_expr(param_type, only_leaves,
                                     gen_bottom=gen_bottom, sam_coercion=False)
            args.append(ast.CallArgument(arg))
        self.depth = initial_depth

        return ast.FunctionCall(name, args, receiver=None, is_ref_call=True)

    # pylint: disable=unused-argument
    def gen_new(self,
                etype: tp.Type,
                only_leaves=False,
                subtype=True,
                sam_coercion=False) -> ast.New:
        """Create a new object of a given type.

        This could be:
            * Function type
            * SAM type
            * Parameterized Type
            * Simple Classifier Type

        Args:
            etype: the type for which we want to create an object
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type could be a subtype of `etype`.
            sam_coercion: Apply sam coercion if possible.
        """

        if getattr(etype, 'is_function_type', lambda: False)():
            return self._gen_func_ref_lambda(etype)

        # Apply SAM coercion
        if sam_coercion and tu.is_sam(self.context, etype):
            type_var_map = tu.get_type_var_map_from_ptype(etype)
            sam_sig_etype = tu.find_sam_fun_signature(
                    self.context,
                    etype,
                    self.bt_factory.get_function_type,
                    type_var_map=type_var_map
            )
            if sam_sig_etype:
                return self._gen_func_ref_lambda(sam_sig_etype)

        class_decl = self._get_subclass(etype, subtype)
        if isinstance(etype, tp.ParameterizedType):
            etype = etype.to_variance_free()
        news = {
            self.bt_factory.get_any_type(): ast.New(
                self.bt_factory.get_any_type(), args=[]),
            self.bt_factory.get_void_type(): ast.New(
                self.bt_factory.get_void_type(), args=[])
        }
        con = news.get(etype)
        if con is not None:
            return con

        # No class was found corresponding to the given type. Probably,
        # the given type is a type parameter. So, if this type parameter has
        # a bound, generate a value of this bound. Otherwise, generate a bottom
        # value.
        if class_decl is None:
            t = etype
            # If the etype corresponds to a type variable not belonging to
            # to the current namespace, then create a bottom constant
            # whose type is unknown. This means that the corresponding
            # translator won't perform cast on this constant.
            if etype.is_type_var() and (
                    etype.name not in self._get_type_variable_names()):
                t = None
            return ast.BottomConstant(t)

        if etype.is_type_constructor():
            etype, _ = tu.instantiate_type_constructor(
                etype, self.get_types(),
                disable_variance_functions=self.disable_variance_functions,
                enable_pecs=self.enable_pecs)
        if class_decl.is_parameterized() and (
              class_decl.get_type().name != etype.name):
            etype, _ = tu.instantiate_type_constructor(
                class_decl.get_type(), self.get_types(),
                disable_variance_functions=self.disable_variance_functions,
                enable_pecs=self.enable_pecs)
        # If the matching class is a parameterized one, we need to create
        # a map mapping the class's type parameters with the corresponding
        # type arguments as given by the `etype` variable.
        type_param_map = (
            {} if not class_decl.is_parameterized()
            else {t_p: etype.type_args[i]
                  for i, t_p in enumerate(class_decl.type_parameters)}
        )
        initial_depth = self.depth
        self.depth += 1
        args = []
        prev = self._new_from_class
        self._new_from_class = None
        for field in class_decl.fields:
            expr_type = tp.substitute_type(field.get_type(), type_param_map)
            # FIXME We set subtype=False to prevent infinite object
            # initialization.
            args.append(self.generate_expr(expr_type, only_leaves,
                                           subtype=False,
                                           sam_coercion=True))
        self._new_from_class = prev
        self.depth = initial_depth
        new_type = class_decl.get_type()
        if class_decl.is_parameterized():
            new_type = new_type.new(etype.type_args)
        return ast.New(new_type, args)

    # Where

    def _get_subclass(self,
                      etype: tp.Type,
                      subtype=True) -> ast.ClassDeclaration:
        """"Find a subclass that is a subtype of the given type and is a
        regular class.

        Args:
            etype: the type for which we are searching for subclasses.
            subtype: The type could be a subtype of `etype`.
        """
        class_decls = self.context.get_classes(self.namespace).values()
        # Get all classes that are subtype of the given type, and there
        # are regular classes (no interfaces or abstract classes).
        subclasses = []
        for c in class_decls:
            if c.class_type != ast.ClassDeclaration.REGULAR:
                continue
            if c.is_parameterized():
                t_con = getattr(etype, 't_constructor', None)
                if c.get_type() == t_con or (
                        subtype and c.get_type().is_subtype(etype)):
                    subclasses.append(c)
            else:
                if c.get_type() == etype or (
                        subtype and c.get_type().is_subtype(etype)):
                    subclasses.append(c)
        if not subclasses:
            return None
        # FIXME what happens if subclasses is empty?
        # it may happens due to ParameterizedType with TypeParameters as targs
        return ut.random.choice(
            [s for s in subclasses if s.name == etype.name] or subclasses)

    # And

    def _gen_func_ref_lambda(self, etype:tp.Type):
        """Generate a function reference or a lambda for a given signature.

        Args:
            etype: signature

        Returns:
            ast.Lambda or ast.FunctionReference
        """
        if ut.random.bool():
            func_refs = self._get_func_refs(etype)
            if len(func_refs) == 0:
                func_ref = self.gen_func_ref(etype)
                if func_ref:
                    return func_ref
            else:
                return ut.random.choice(func_refs)
        prev_inside_java_lamdba = self._inside_java_lambda
        self._inside_java_lambda = self.language == "java"
        params = [self.gen_param_decl(et) for et in etype.type_args[:-1]]
        self._inside_java_lambda = prev_inside_java_lamdba
        ret_type = etype.type_args[-1]
        return self.gen_lambda(etype=ret_type, params=params)

    # Where

    def _get_func_refs(self, etype: tp.Type) -> List[ast.FunctionReference]:
        """Get a list with all function references that can assigned to etype.

        Currently, we cannot handle parameterized types that include type
        parameters as type arguments.
        To compute this list we perform the following steps:

        1. We detect all declared functions and we create, if possible,
            function references to those that can be assigned to etype.
        2. We search for variables have been assigned values of etype.
        3. We find variables declared in the current scope that can be used
            as receivers of a function reference that can be assigned to etype.

        Args:
            etype: signature for function reference
        """
        refs = []

        # We cannot handle parameterized types with type params as type args.
        # To support them, they must be in the same type constructor (using this)
        if any(isinstance(targ, tp.TypeParameter)
               for targ in etype.type_args):
            return refs

        # When in top-level class declaration, we cannot generate a variable
        # because generate_expr won't generate it correctly.
        only_leaves = len(self.namespace) == 2 and self.namespace[1][0].isupper

        # Step 1: Find all functions that can be used as function references
        refs.extend(self._get_func_refs_from_functions(etype, only_leaves))

        # Step 2: Find existing function references
        variables = list(self.context.get_vars(self.namespace).values())
        if self._inside_java_lambda:
            variables = list(filter(
                lambda v: (getattr(v, 'is_final', False) or (
                    v not in self.context.get_vars(self.namespace[:-1]).values())),
                variables))
        variables += list(self.context.get_vars(
            ('global',), only_current=True).values())
        # Step 3: Find objects in scoped that can be used as receivers
        for var_decl in variables:
            var_type = var_decl.get_type()
            var = ast.Variable(var_decl.name)
            class_decls = self.context.get_classes(('global',), glob=True)
            if var_type == etype:
                refs.append(var)
            # Check for receivers. For example, in the following case we should
            # add the function reference a::foo if we are looking for function
            # references with signature: Function0<Integer>.
            #
            #  class A {
            #  	Integer foo() {return 1;}
            #  }
            #
            #  public static void main(String[] args) {
            #  	A a = new A();
            #  }
            elif isinstance(var_type, (tp.SimpleClassifier,
                                       tp.ParameterizedType)):
                class_decl = class_decls.get(var_type.name, None)
                if not class_decl:
                    continue
                funcs = class_decl.get_callable_functions(class_decls.values())
                for func in funcs:
                    signature = func.get_signature(
                        self.bt_factory.get_function_type(len(func.params))
                    )
                    if signature == etype:
                        refs.append(ast.FunctionReference(func.name, var))
        return refs

    # Where

    def _get_func_refs_from_functions(self,
                                      etype: tp.Type,
                                      only_leaves: bool
                                     ) -> List[ast.FunctionReference]:
        """Get function references to etype from function declarations.

        We filter out nested functions.
        For non-top-level functions we generate a receiver.

        Args:
            etpye: function signature
            only_leaves: do not generate new leaves except from `expr`.
        """
        refs = []
        # Search in all global functions
        for func in self.context.get_funcs(self.namespace, glob=True).values():

            namespace = self.context.get_namespace(func) + (func.name,)
            # Check if nested function
            if not namespace[-2] == "global" and not namespace[-2][0].isupper():
                continue

            signature = func.get_signature(
                self.bt_factory.get_function_type(len(func.params))
            )

            if signature == etype:
                if func.func_type == func.FUNCTION:
                    refs.append(ast.FunctionReference(func.name, None))
                else:
                    parent = self.context.get_parent(namespace)
                    parent_type = parent.get_type()
                    # if parent is a type constructor then initialize a
                    # ParameterizedType
                    if isinstance(parent_type, tp.TypeConstructor):
                        parent_type, _ = tu.instantiate_type_constructor(
                            parent_type, self.get_types(),
                            disable_variance_functions=self.disable_variance_functions,
                            enable_pecs=self.enable_pecs
                        )

                    receiver = self.generate_expr(parent_type,
                                                  subtype=False,
                                                  only_leaves=only_leaves,
                                                  sam_coercion=False)
                    refs.append(ast.FunctionReference(func.name, receiver))
            # Handle functions of parameterized classes
            else:
                func_ref = self._get_func_ref_from_func_in_param_cls(
                    only_leaves, etype, func, namespace
                )
                if func_ref:
                    refs.append(func_ref)
            # TODO handle parameterized functions
        return refs

    # Where

    def _get_func_ref_from_func_in_param_cls(self,
                                             only_leaves: bool,
                                             etype: tp.Type,
                                             func: ast.FunctionDeclaration,
                                             namespace
                                            ) -> ast.FunctionReference:
        """Get function reference from function in Parameterized Class

        Args:
            only_leaves: do not generate new leaves except from `expr`.
            etpye: function signature.
            func: Function declaration of the function.
            namespace: namespace of the function.
        """
        is_param_type_param = any(isinstance(param, tp.TypeParameter)
            for param in func.params)
        is_ret_type_param = isinstance(func.ret_type, tp.TypeParameter)

        if not is_param_type_param and not is_ret_type_param:
            return None

        def check_type(is_type_param , itype, etype):
            if not is_type_param and itype == etype:
                return True
            if is_type_param:
                if itype.bound and not etype.is_subtype(itype.bound):
                    return False
                return True
            return False

        etype_ret = etype.type_args[-1]
        etype_params = etype.type_args[:-1]
        type_var_map = {}

        # Check if return type can conform to etype's return type.
        if not check_type(is_ret_type_param, func.ret_type, etype_ret):
            return None
        if is_ret_type_param:
            type_var_map[func.ret_type] = etype_ret
        # Check if parameters can conform to etype's parameters.
        if len(func.params) != len(etype_params):
            return None
        for fparam, eparam in zip(func.params, etype_params):
            is_type_param = isinstance(fparam, tp.TypeParameter)
            if not check_type(is_type_param, fparam, eparam):
                return None
            if is_type_param:
                type_var_map[fparam] = eparam
        # Create a parameterized type with the correct type arguments
        parent = self.context.get_parent(namespace)
        parent_type = parent.get_type()
        if not isinstance(parent_type, tp.TypeConstructor):
            return None

        receiver_type, _ = tu.instantiate_type_constructor(
            parent_type, self.get_types(), type_var_map=type_var_map,
            disable_variance_functions=self.disable_variance_functions,
            enable_pecs=self.enable_pecs
        )
        receiver = self.generate_expr(receiver_type,
                                      subtype=False,
                                      only_leaves=only_leaves,
                                      sam_coercion=False)
        return ast.FunctionReference(func.name, receiver)

    ### Standard API of Generator ###

    def get_generators(self,
                       expr_type: tp.Type,
                       only_leaves: bool,
                       subtype: bool,
                       exclude_var: bool,
                       sam_coercion=False) -> List[Callable]:
        """Get candidate generators for the given type.

        Args:
            expr_type: targeted type.
            only_leaves: do not generate new leaves except from `expr`.
            subtype: The type of the generated expression could be a subtype
                of `expr_type`.
            exclude_var: if this option is false, then it could assign the
                generated expression into a variable, and return that
                variable reference.
            sam_coercion: Enable sam coercion.

        Returns:
            A list of generator functions
        """
        def gen_variable(etype):
            return self.gen_variable(etype, only_leaves, subtype)

        def gen_fun_call(etype):
            return self.gen_func_call(etype, only_leaves=only_leaves,
                                      subtype=subtype)

        # Do not generate new nodes in context.
        leaf_canidates = [
            lambda x: self.gen_new(x, only_leaves, subtype,
                                   sam_coercion=sam_coercion),
        ]
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
                lambda x: self.gen_array_expr(x, only_leaves, subtype=subtype)
            ),
        }
        binary_ops = {
            self.bt_factory.get_boolean_type(): [
                lambda x: self.gen_logical_expr(x, only_leaves),
                lambda x: self.gen_equality_expr(only_leaves),
                lambda x: self.gen_comparison_expr(only_leaves)
            ],
        }
        other_candidates = [
            lambda x: self.gen_field_access(x, only_leaves, subtype),
            lambda x: self.gen_conditional(x, only_leaves=only_leaves,
                                           subtype=subtype),
            lambda x: self.gen_is_expr(x, only_leaves=only_leaves,
                                       subtype=subtype),
            gen_fun_call,
            gen_variable
        ]

        if expr_type == self.bt_factory.get_void_type():
            # The assignment operator in Java evaluates to the assigned value.
            #if self.language == 'java':
            #    return [gen_fun_call]
            return [gen_fun_call,
                    lambda x: self.gen_assignment(x, only_leaves)]

        if self.depth >= self.cfg.limits.max_depth or only_leaves:
            gen_con = constant_candidates.get(expr_type.name)
            if gen_con is not None:
                return [gen_con]
            gen_var = (
                self._vars_in_context.get(
                    self.namespace, 0) < self.cfg.limits.max_var_decls and not
                only_leaves and not exclude_var)
            if gen_var:
                # Decide if we can generate a variable.
                # If the maximum numbers of variables in a specific context
                # has been reached, or we have previously declared a variable
                # of a specific type, then we should avoid variable creation.
                leaf_canidates.append(gen_variable)
            return leaf_canidates
        con_candidate = constant_candidates.get(expr_type.name)
        if con_candidate is not None:
            candidates = [con_candidate] + binary_ops.get(expr_type, [])
            if not exclude_var:
                candidates.append(gen_variable)
        else:
            candidates = leaf_canidates
        return other_candidates + candidates

    def get_types(self,
                  ret_types=True,
                  exclude_arrays=False,
                  exclude_covariants=False,
                  exclude_contravariants=False,
                  exclude_type_vars=False,
                  exclude_function_types=False) -> List[tp.Type]:
        """Get all available types.

        Including user-defined types, built-ins, and function types.
        Note that this may include Type Constructors.

        Args:
            ret_types: use non-nothing built-in types (use this option if you
                want to generate a return type).
            exclude_arrays: exclude array types.
            exclude_covariants: exclude covariant type parameters.
            exclude_contravariants: exclude contravariant type parameters.
            exclude_type_vars: exclude type variables.
            exclude_function_types: exclude function types.

        Returns:
            A list of available types.
        """
        usr_types = [
            c.get_type()
            for c in self.context.get_classes(self.namespace).values()
        ]
        type_params = []
        if not exclude_type_vars:
            for t_param in self.context.get_types(self.namespace).values():
                variance = getattr(t_param, 'variance', None)
                if exclude_covariants and variance == tp.Covariant:
                    continue
                if exclude_contravariants and variance == tp.Contravariant:
                    continue
                type_params.append(t_param)

        if type_params and ut.random.bool():
            return type_params

        builtins = list(self.ret_builtin_types
                        if ret_types
                        else self.builtin_types)
        if exclude_arrays:
            builtins = [
                t for t in builtins
                if t.name != self.bt_factory.get_array_type().name
            ]
        if exclude_function_types:
            return usr_types + builtins
        return usr_types + builtins + self.function_types

    def select_type(self,
                    ret_types=True,
                    exclude_arrays=False,
                    exclude_covariants=False,
                    exclude_contravariants=False,
                    exclude_function_types=False) -> tp.Type:
        """Select a type from the all available types.

        It will always instantiating type constructors to parameterized types.

        Args:
            ret_types: use non-nothing built-in types (use this option if you
                want to generate a return type).
            exclude_arrays: exclude array types.
            exclude_covariants: exclude covariant type parameters.
            exclude_contravariants: exclude contravariant type parameters.
            exclude_type_vars: exclude type variables.
            exclude_function_types: exclude function types.

        Returns:
            Returns a type.
        """
        types = self.get_types(ret_types=ret_types,
                               exclude_arrays=exclude_arrays,
                               exclude_covariants=exclude_covariants,
                               exclude_contravariants=exclude_contravariants,
                               exclude_function_types=exclude_function_types)
        stype = ut.random.choice(types)
        if stype.is_type_constructor():
            exclude_type_vars = stype.name == self.bt_factory.get_array_type().name
            stype, _ = tu.instantiate_type_constructor(
                stype, self.get_types(exclude_arrays=True,
                                      exclude_covariants=True,
                                      exclude_contravariants=True,
                                      exclude_type_vars=exclude_type_vars,
                                      exclude_function_types=exclude_function_types),
                enable_pecs=self.enable_pecs,
                disable_variance_functions=self.disable_variance_functions,
                variance_choices={}
            )
        return stype

    def gen_type_params(self,
                        count: int=None,
                        with_variance=False,
                        blacklist: List[str]=None,
                        for_function=False) -> List[tp.TypeParameter]:
        """Generate a list containing type parameters

        Args:
            count: number of type parameters, if none it randomly select the
                number of type parameters.
            with_variance: enable variance
            blacklist: a list of type parameter names
            for_function: create type parameters for parameterized functions
        """
        if not count and ut.random.bool():
            return []
        type_params = []
        type_param_names = blacklist or []
        variances = [tp.Invariant, tp.Covariant, tp.Contravariant]
        for _ in range(ut.random.integer(count or 1, self.cfg.limits.max_type_params)):
            name = ut.random.caps(blacklist=type_param_names)
            type_param_names.append(name)
            if for_function:
                # OK we do this trick for type parameters corresponding to
                # functions in order to avoid conflicts with type variables
                # of classes. TODO: consider being less conservative.
                name = "F_" + name
            variance = None
            if with_variance and ut.random.bool():
                variance = ut.random.choice(variances)
            bound = None
            if ut.random.bool():
                exclude_covariants = variance == tp.Contravariant or for_function
                exclude_contravariants = True
                bound = self.select_type(
                    exclude_arrays=True,
                    exclude_covariants=exclude_covariants,
                    exclude_contravariants=exclude_contravariants
                )
                if bound.is_primitive():
                    bound = bound.box_type()
            type_param = tp.TypeParameter(name, variance=variance, bound=bound)
            # Add type parameter to context.
            self.context.add_type(self.namespace, type_param.name, type_param)
            type_params.append(type_param)
        return type_params

    ### Internal helper functions ###

    def _get_type_variable_names(self) -> List[str]:
        """Get the name of type variables that are in place in the current
        namespace.
        """
        return list(self.context.get_types(self.namespace).keys())

    def _gen_func_params(self) -> List[ast.ParameterDeclaration]:
        """Generate parameters for a function or for a lambda.
        """
        params = []
        arr_index = None
        vararg_found = False
        vararg = None
        for i in range(ut.random.integer(0, self.cfg.limits.fn.max_params)):
            param = self.gen_param_decl()
            # If the type of the parameter is an array consider make it
            # a vararg.
            if not vararg_found and self._can_vararg_param(param) and (
                    ut.random.bool()):
                param.vararg = True
                arr_index = i
                vararg = param
                vararg_found = True
            params.append(param)
            self.context.add_var(self.namespace, param.name, param)
        len_p = len(params)
        # If one of the parameters is a vararg, then place it to the back.
        if arr_index is not None and arr_index != len_p - 1:
            params[len_p - 1], params[arr_index] = vararg, params[len_p - 1]
        return params

    # Where

    def _can_vararg_param(self, param: ast.ParameterDeclaration) -> bool:
        """Check if a parameter can be vararg.
        """
        if self.language == 'kotlin':
            # TODO theosotr Can we do this in a better way? without hardcode?
            # Actually in Kotlin, the type of varargs is Array<out T>.
            # So, until we add support for use-site variance, we support
            # varargs for 'primitive' types only which kotlinc treats them
            # as specialized arrays.
            t_constructor = getattr(param.get_type(), 't_constructor', None)
            return isinstance(t_constructor, kt.SpecializedArrayType)
        # A vararg is actually a syntactic sugar for a parameter whose type
        # is an array of something.
        return param.get_type().name == 'Array'

    def _get_func_ret_type(self,
                           params: List[ast.ParameterDeclaration],
                           etype: tp.Type,
                           not_void=False) -> tp.Type:
        """Get return type for a function or lambda.

        Args:
            params: function parameters.
            etype: use this type as the return type
            not_void: do not return void
        """
        if etype is not None:
            return etype
        param_types = [p.param_type for p in params
                       if getattr(p.param_type,
                                  'variance', None) != tp.Contravariant]
        if param_types and ut.random.bool():
            return ut.random.choice(param_types)
        return self.select_type(exclude_contravariants=True)

    def _gen_func_body(self, ret_type: tp.Type) -> Tuple[ast.Block, tp.Type]:
        """Generate the body of a function or a lambda.

        Args:
            ret_type: Return type of the function

        Returns:
            A tuple of the function block and its return type.
        """
        expr_type = (
            self.select_type(ret_types=False)
            if ret_type == self.bt_factory.get_void_type()
            else ret_type
        )
        expr = self.generate_expr(expr_type)
        decls = list(self.context.get_declarations(
            self.namespace, True).values())
        var_decls = [d for d in decls
                     if not isinstance(d, ast.ParameterDeclaration)]
        # TODO remove type inference from functions
        if (not var_decls and
                ret_type != self.bt_factory.get_void_type() and
                self.can_infer_function_ret_type(expr, decls)):
            # The function does not contain any declarations and its return
            # type is not Unit. So, we can create an expression-based function.
            inferred_type = ret_type
            body = expr
            # If the return type is Number, then this must be explicit.
            # If the return value is the bottom constant, then again the
            # return type must be explicit.
            if ret_type != self.bt_factory.get_number_type() and not (
                  expr.is_bottom()):
                ret_type = None
        else:
            inferred_type = None
            exprs, decls = self._gen_side_effects()
            body = ast.Block(decls + exprs + [expr])
        return body, inferred_type

    # Where

    # TODO probably we have to remove this functions.
    # theosotr what is the exact role of this function?
    def can_infer_function_ret_type(self, func_expr, decls):
        if not self.disable_inference_in_closures:
            return True

        # TODO theosotr
        # We want to disable inference in the following situations
        # fun foo(x: Any) {
        #    if (x is String) {
        #       fun bar() = x
        #       return bar()
        #    } else return ""
        # }
        # This will help us to avoid the repetition of an already discovered
        # bug.
        if not isinstance(func_expr, ast.Variable):
            return True

        return func_expr.name in {d.name for d in decls}

    # And

    def _gen_side_effects(self) -> Tuple[List[ast.Expr], List[ast.Declaration]]:
        """Generate expressions with side-effects for function bodies.

        Example side-effects: assignment, variable declaration, etc.
        """
        exprs = []
        for _ in range(ut.random.integer(0, self.cfg.limits.fn.max_side_effects)):
            expr = self.generate_expr(self.bt_factory.get_void_type())
            if expr:
                exprs.append(expr)
        # These are the new declarations that we created as part of the side-
        # effects.
        decls = self.context.get_declarations(self.namespace, True).values()
        decls = [d for d in decls
                 if not isinstance(d, ast.ParameterDeclaration)]
        return exprs, decls

    def _get_matching_objects(self,
                              etype: tp.Type,
                              subtype: bool,
                              attr_name: str
                             ) -> List[Tuple[ast.Expr,
                                       tu.TypeVarMap,
                                       ast.Declaration]]:
        """Get objects that have an attribute of attr_name that is/return etype.

        This function essentially searches for variables containing objects
        whose class has either a field of a specific value or a function that
        return a particular value.

        Args:
            etype: the targeted type that we are searching. Functions should
                return that type.
            subtype: The type of matching attribute could be a subtype of
                `etype`.
            attr_name: 'fields' or 'functions'

        Returns:
            A list that contains tuples of variables, their TypeVarMaps
            and declarations (field or function).
        """
        decls = []
        variables = self.context.get_vars(self.namespace).values()
        if self._inside_java_lambda:
            variables = list(filter(
                lambda v: (getattr(v, 'is_final', False) or (
                    v not in self.context.get_vars(self.namespace[:-1]).values())),
                variables))
        for var in variables:
            var_type = self._get_var_type_to_search(var.get_type())
            if not var_type:
                continue
            if isinstance(getattr(var_type, 't_constructor', None),
                          self.function_type):
                continue
            cls, type_map_var = self._get_class(var_type)
            for attr in getattr(cls, attr_name):  # function or field
                attr_type = tp.substitute_type(
                    attr.get_type(), type_map_var)
                if not attr_type:
                    continue
                if attr_type == self.bt_factory.get_void_type():
                    continue
                cond = (
                    attr_type.is_assignable(etype)
                    if subtype
                    else attr_type == etype
                )
                if not cond:
                    continue

                if attr_name == 'functions':
                    if attr.is_parameterized():
                        # Here we do the following. The retrieved attribute
                        # is a parameterized function. So, we need to
                        # instantiate it with some type arguments. However,
                        # note that if the matching object belongs to a
                        # parameterized class, we need to consider the
                        # following case:
                        #
                        # A<T> {
                        #   fun <X: T> foo(): X
                        # }
                        # val a = new A<String>()
                        # a.foo() -> here the type argument of the function
                        # `foo` should be a subtype of String, as the type of
                        # the receiver is A<String> and as a result the bound
                        # type variable X is String.
                        type_var_bounds = {}
                        for t_param in attr.type_parameters:
                            bound = t_param.bound
                            if bound is None:
                                continue
                            if bound.has_type_variables():
                                bound = tp.substitute_type(
                                    bound, type_map_var)
                                if not bound.has_type_variables():
                                    type_var_bounds[t_param] = bound
                        type_var_bounds.update(type_map_var)
                        fun_type_var_map = tu.instantiate_parameterized_function(
                            attr.type_parameters, self.get_types(),
                            type_var_map=type_var_bounds, only_regular=True)
                    else:
                        fun_type_var_map = {}

                    decls.append((ast.Variable(var.name), type_map_var, attr,
                                  fun_type_var_map))
                else:
                    decls.append((ast.Variable(var.name), type_map_var, attr))
        return decls

    def _get_matching_class(self,
                            etype:tp.Type,
                            subtype: bool,
                            attr_name: str) -> gu.AttrAccessInfo:
        """Get a class that has an attribute of attr_name that is/return etype.

        This function essentially searches for a class that has either a field
        of a specific value or a function that return a particular value.

        Args:
            etype: the targeted type that we are searching. Functions should
                return that type.
            subtype: The type of matching attribute could be a subtype of
                `etype`.
            attr_name: 'fields' or 'functions'

        Returns:
            An AttrAccessInfo with a matched class type and attribute
            declaration (field or function).
        """
        class_decls = self._get_matching_class_decls(etype, subtype, attr_name)
        if not class_decls:
            return None
        cls, type_var_map, attr = ut.random.choice(class_decls)
        func_type_var_map = {}
        is_parameterized_func = isinstance(
            attr, ast.FunctionDeclaration) and attr.is_parameterized()
        if cls.is_parameterized():
            cls_type_var_map = type_var_map

            variance_choices = (
                None
                if cls_type_var_map is None
                else gu.init_variance_choices(cls_type_var_map)
            )
            cls_type, params_map = tu.instantiate_type_constructor(
                cls.get_type(), self.get_types(),
                only_regular=True, type_var_map=type_var_map,
                enable_pecs=self.enable_pecs,
                disable_variance_functions=self.disable_variance_functions,
                variance_choices=variance_choices
            )
            if is_parameterized_func:
                # Here we have found a parameterized function in a
                # parameterized class. So wee need to both instantiate
                # the type constructor and the parameterized function.
                types = tu._get_available_types(cls.get_type(),
                                                self.get_types(),
                                                True, False)
                _, type_var_map = tu._compute_type_variable_assignments(
                    cls.type_parameters + attr.type_parameters,
                    types, type_var_map=type_var_map,
                    variance_choices=variance_choices
                )
                params_map, func_type_var_map = tu.split_type_var_map(
                    type_var_map, cls.type_parameters, attr.type_parameters)
                targs = [
                    params_map[t_param]
                    for t_param in cls.type_parameters
                ]
                cls_type = cls.get_type().new(targs)
            else:
                # Here, we have a non-parameterized function in a parameterized
                # class. So we only need to instantiate the type constructor.
                cls_type, params_map = tu.instantiate_type_constructor(
                    cls.get_type(), self.get_types(),
                    only_regular=True, type_var_map=cls_type_var_map,
                    enable_pecs=self.enable_pecs,
                    variance_choices=variance_choices
                )
        else:
            if is_parameterized_func:
                # We are in a parameterized class defined in a class that
                # is not a type constructor.
                func_type_var_map = tu.instantiate_parameterized_function(
                    attr.type_parameters, self.get_types(),
                    only_regular=True, type_var_map=type_var_map)
            cls_type, params_map = cls.get_type(), {}
        return gu.AttrAccessInfo(cls_type, params_map, attr, func_type_var_map)

    # Where

    def _get_matching_class_decls(self,
                                  etype: tp.Type,
                                  subtype: bool,
                                  attr_name: str
                                 ) -> List[Tuple[ast.ClassDeclaration,
                                                 tu.TypeVarMap,
                                                 ast.Declaration]]:
        """Get classes that have attributes of attr_name that are/return etype.

        Args:
            etype: the targeted type that we are searching. Functions should
                return that type.
            subtype: The type of matching attribute could be a subtype of
                `etype`.
            attr_name: 'fields' or 'functions'

        Returns:
            A list of tuples that include class declarations, TypeVarMaps for
            the attributes and the declarations of the attributes (fields or
            functions).
        """
        class_decls = []
        for c in self.context.get_classes(self.namespace).values():
            for attr in getattr(c, attr_name):  # field or function
                attr_type = attr.get_type()
                if not attr_type:
                    continue
                if attr_type == self.bt_factory.get_void_type():
                    continue
                cond = (
                    attr_type.is_assignable(etype)
                    if subtype else
                    attr_type == etype
                )
                type_var_map = None
                # if the type of the attribute has type variables,
                # then we have to unify it with the expected type so that
                # we can instantiate the corresponding type constructor
                # accordingly
                if not cond or attr_type.has_type_variables():
                    type_var_map = tu.unify_types(etype, attr_type,
                                                  self.bt_factory)
                if not type_var_map and not cond:
                    continue
                # Now here we keep the class and the function that match
                # the given type.
                class_decls.append((c, type_var_map, attr))
        return class_decls

    def _gen_matching_class(self,
                            etype: tp.Type,
                            attr_name: str,
                            not_void=False) -> gu.AttrAccessInfo:
        """Generate a class that has an attribute of attr_name that is/return etype.

        Args:
            etype: the targeted type that we want to get. Functions should
                return that type.
            attr_name: 'fields' or 'functions'
            not_void: Functions of the class should not return void.

        Returns:
            An AttrAccessInfo for the generated class type and attribute
            declaration (field or function).
        """
        initial_namespace = self.namespace
        class_name = gu.gen_identifier('capitalize')
        type_params = None
        if etype.has_type_variables():
            # We have to create a class that has an attribute whose type
            # is a type parameter. The only way to achieve this is to create
            # a parameterized class, and pass the type parameter 'etype'
            # as a type argument to the corresponding type constructor.
            self.namespace = ast.GLOBAL_NAMESPACE + (class_name,)
            type_params, type_var_map, can_wildcard = \
                self._create_type_params_from_etype(etype)
            etype2 = tp.substitute_type(etype, type_var_map)
        else:
            type_var_map, etype2, can_wildcard = {}, etype, False
        self.namespace = ast.GLOBAL_NAMESPACE
        if attr_name == 'functions':
            kwargs = {'fret_type': etype2}
        else:
            kwargs = {'field_type': etype2}
        cls = self.gen_class_decl(**kwargs, not_void=not_void,
                                  type_params=type_params,
                                  class_name=class_name)
        self.context.add_class(self.namespace, cls.name, cls)
        self.namespace = initial_namespace
        if cls.is_parameterized():
            type_map = {v: k for k, v in type_var_map.items()}
            if etype2.is_primitive() and (
                    etype2.box_type() == self.bt_factory.get_void_type()):
                type_map = None

            if can_wildcard:
                variance_choices = gu.init_variance_choices(type_map)
            else:
                variance_choices = None
            cls_type, params_map = tu.instantiate_type_constructor(
                cls.get_type(),
                self.get_types(),
                type_var_map=type_map,
                enable_pecs=self.enable_pecs,
                disable_variance_functions=self.disable_variance_functions,
                variance_choices=variance_choices
            )
        else:
            cls_type, params_map = cls.get_type(), {}
        for attr in getattr(cls, attr_name):
            attr_type = tp.substitute_type(attr.get_type(), params_map)
            if attr_type != etype:
                continue

            func_type_var_map = {}
            if isinstance(
                    attr, ast.FunctionDeclaration) and attr.is_parameterized():
                func_type_var_map = tu.instantiate_parameterized_function(
                    attr.type_parameters, self.get_types(), only_regular=True,
                    type_var_map=params_map)

            return gu.AttrAccessInfo(cls_type, params_map, attr,
                                  func_type_var_map)
        return None

    # Where

    def _create_type_params_from_etype(self, etype: tp.Type):
        """Generate type parameters for a type.

        Returns:
            * A list of type parameters.
            * A TypeVarMap for the type parameters.
            * A boolean to declare if we can use wildcards.
        """
        if not etype.has_type_variables():
            return []

        if isinstance(etype, tp.TypeParameter):
            type_params = self.gen_type_params(
                count=1, with_variance=self.language == 'kotlin')
            type_params[0].bound = etype.get_bound_rec(self.bt_factory)
            type_params[0].variance = tp.Invariant
            return type_params, {etype: type_params[0]}, True

        # the given type is parameterized
        assert isinstance(etype, tp.ParameterizedType)
        type_vars = etype.get_type_variables(self.bt_factory)
        type_params = self.gen_type_params(
            len(type_vars), with_variance=self.language == 'kotlin')
        type_var_map = {}
        available_type_params = list(type_params)
        can_wildcard = True
        for type_var, bounds in type_vars.items():
            # The given type 'etype' has type variables.
            # So, it's not safe to instantiate these type variables with
            # wildcard types. In this way we prevent errors like the following.
            #
            # class A<T> {
            #   B<T> foo();
            # }
            # A<? extends Number> x = new A<>();
            # B<Number> = x.foo(); // error: incompatible types
            # TODO: We may support this case in the future.
            can_wildcard = False
            bounds = list(bounds)
            type_param = ut.random.choice(available_type_params)
            available_type_params.remove(type_param)
            if bounds != [None]:
                type_param.bound = functools.reduce(
                    lambda acc, t: t if t.is_subtype(acc) else acc,
                    filter(lambda t: t is not None, bounds), bounds[0])
            else:
                type_param.bound = None
            type_param.variance = tp.Invariant
            type_var_map[type_var] = type_param
        return type_params, type_var_map, can_wildcard

    def _get_class(self,
                   etype: tp.Type
                  ) -> Tuple[ast.ClassDeclaration, tu.TypeVarMap]:
        """Find the class declaration for a given type.
        """
        # Get class declaration based on the given type.
        class_decls = self.context.get_classes(self.namespace).values()
        for c in class_decls:
            cls_type = c.get_type()
            t_con = getattr(etype, 't_constructor', None)
            # or t == t_con: If etype is a parameterized type (i.e.,
            # getattr(etype, 't_constructor', None) != None), we need to
            # get the class corresponding to its type constructor.
            if ((cls_type.is_assignable(etype) and cls_type.name == etype.name)
                    or cls_type == t_con):
                if c.is_parameterized():
                    type_var_map = {
                        t_param: etype.type_args[i]
                        for i, t_param in enumerate(c.type_parameters)
                    }
                else:
                    type_var_map = {}
                return c, type_var_map
        return None

    # theosotr check the following docstring
    def _get_var_type_to_search(self, var_type: tp.Type) -> tp.TypeParameter:
        """Find if the variable is bounded to a type parameter.

        Args:
            var_type: The type of the variable.
        """
        # We are only interested in variables of class types.
        if tu.is_builtin(var_type, self.bt_factory):
            return None
        if var_type.is_type_var() or var_type.is_wildcard():
            args = [] if var_type.is_wildcard() else [self.bt_factory]
            bound = var_type.get_bound_rec(*args)
            if not bound or tu.is_builtin(bound, self.bt_factory) or (
                  isinstance(bound, tp.TypeParameter)):
                return None
            var_type = bound
        return var_type
