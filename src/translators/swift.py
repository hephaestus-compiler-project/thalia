from src.ir import ast, types as tp, swift_types as swift, type_utils as tu
from src.translators.base import BaseTranslator
import re

def append_to(visit):
    def inner(self, node):
        self._nodes_stack.append(node)
        res = visit(self, node)
        self._nodes_stack.pop()
    return inner

class SwiftTranslator(BaseTranslator):
    filename = "program.swift"
    def __init__(self, package=None, options={}):
        super().__init__(package, options)
        self._children_res = []
        self.ident = 0
        self.is_unit = False
        self.is_lambda = False
        self._cast_integers = False
        self.context = None
        self._nodes_stack = [None]

    

    def _reset_state(self):
        self._children_res = []
        self.ident = 0
        self.is_unit = False
        self.is_lambda = False
        self._cast_integers = False
        self._nodes_stack = [None]
        self.context = None
    def pop_children_res(self, children):
        len_c = len(children)
        if not len_c:
            return []
        res = self._children_res[-len_c:]
        self._children_res = self._children_res[:-len_c]
        return res
    @staticmethod
    def get_filename():
        return SwiftTranslator.filename
    @append_to
    def visit_lambda(self, node):
        

        old_ident = self.ident
        is_expression = not isinstance(node.body, ast.Block)
        self.ident = 0 if is_expression else self.ident + 2
        children = node.children()

        prev_is_unit = self.is_unit
        prev_is_lambda = self.is_lambda
        self.is_unit = node.get_type() == swift.VoidType()
        use_lambda = isinstance(self._nodes_stack[-2], ast.VariableDeclaration)

                      
        self.is_lambda = use_lambda

        

        prev_c = self._cast_integers
        if is_expression:
            self._cast_integers = True

        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        self.ident = old_ident

        param_res = [children_res[i] for i, _ in enumerate(node.params)]
        body_res = children_res[-1] if node.body else ''
        type_name = self.get_type_name(node.ret_type)
       
        
        type_name = type_name.replace('inout ','')
        ret_type = " -> " + type_name
        if node.can_infer_signature:
            param_res = [p.name for p in node.params]
        #* in swift the lambda sintax is the following: 
        #*  (type,type) -> ret_type = {(a,b) in body}
        param_dict = dict()
        for s in param_res:
            s = s.split(': ')
            param_dict[s[0]] = s[1]

        #if is_expression: # TODO LAMBDAS
        is_void = False
        if not use_lambda:
        
            # use the lambda syntax: { params -> stmt }
            res = "{{({params}) in {body}}}".format(
                
                
                params=", ".join(param_dict.keys()),
                body=body_res[1:-1] if body_res.startswith('{') else body_res
            )
        # from python 3.7 dicts are ordered
        
        else:
            types = param_dict.values()
            _types = []
            for t in types:
                _t = str(t)
                #if _t == 'Void':
                    #_t = ''
                    #is_void = True
                if _t.startswith('Reference<'):
                    _t = _t[10:-1]
                    _t = 'inout ' + _t
                while _t.count('inout ')>1:
                     _t = _t.replace('inout ','',1)
                _types.append(_t)

            if is_void:
                res = "{ident}({types}){ret_type} = {{ return {body} }}".format(
                ident=" " * self.ident,
                types=", ".join(_types),
                ret_type=ret_type,  
                params = ", ".join(param_dict.keys()),
                body=body_res[1:-1] if body_res.startswith('{') else body_res
        )
            else:
                
                res = "{ident}({types}){ret_type} = {{ ({params}) in {body} }}".format(
                ident=" " * self.ident,
                types=", ".join(_types),
                ret_type=ret_type,  
                params = ", ".join(param_dict.keys()),
                body=body_res[1:-1] if body_res.startswith('{') else body_res
            )

        self.is_unit = prev_is_unit
        self.is_lambda = prev_is_lambda
        self._cast_integers = prev_c
        self._children_res.append(res)
   
    
    def visit_equality_expr(self, node):
        prev = self._cast_integers
        # When we encounter equality epxressions,
        # we need to explicitly cast integer literals.
        # Kotlin does not permit operations like the following
        # val d: Short = 1
        # d == 2
        #
        # As a workaround, we can do
        # d == 2.toShort()
        self._cast_integers = True
        self.visit_binary_op(node)
        self._cast_integers = prev
    @append_to
    def visit_func_ref(self, node):
        old_ident = self.ident

        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)

        self.ident = old_ident

        children_res = self.pop_children_res(children)
        segs = node.func.rsplit(".", 1)
        func_name = segs[-1]
        receiver = (
            (
                "" if node.func == ast.FunctionReference.NEW_REF
                else children_res[0]
            )
            if children_res
            else segs[0]
        )
        """
        map_types = {
            kt.Long: ".toLong()",
            kt.Short: ".toShort()",
            kt.Byte: ".toByte()",
            kt.Float: ".toFloat()",
            kt.Double: ".toDouble()",
        }
        """
        if isinstance(node.receiver, ast.New):
            func_name = node.receiver.class_type.name.rsplit(".", 1)[-1]
        """
        if isinstance(node.receiver, (ast.IntegerConstant, ast.RealConstant)):
            if float(node.receiver.literal) < 0:
                # (-34)::div
                receiver = f"({receiver})"
            t = (
                node.receiver.integer_type
                if isinstance(node.receiver, ast.IntegerConstant)
                else node.receiver.real_type
            )
            suffix = map_types.get(t, "")
            receiver += suffix
        """
        if not children_res:
            receiver = receiver.split('<')[0] + '()'

        receiver += "."
        named_parameters = node.named_parameters if node.named_parameters else []
        named_par_str = []
        if len(named_parameters) > 0:
            for np in named_parameters:
                if np == '':
                    named_par_str.append('_')
                else:
                    named_par_str.append(np)
        if len(named_par_str) > 0:
            named_par_str = ': '.join(named_par_str) + ':'
        

        if receiver.startswith('BOTTOM'):
            receiver = receiver.split('BOTTOM() as ')[1]
        res = "{ident}{receiver}{name}({named_par_str})".format(
            ident=" " * self.ident,
            receiver=receiver,
            name=func_name,
            named_par_str=named_par_str
        )
        self._children_res.append(res)
    @append_to
    def visit_conditional(self, node): #XXX
        old_ident = self.ident
        self.ident += 2
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        """
        res = "{}(if ({})\n{}\n{}else\n{})".format(
            " " * old_ident, children_res[0][self.ident:], children_res[1],
            " " * old_ident, children_res[2])
            """
        res = "{} ? {} : {}".format(
            children_res[0][self.ident:], children_res[1], children_res[2])
        self.ident = old_ident
        self._children_res.append(res)
    @append_to
    def visit_bottom_constant(self, node):
    # Start with the base representation of nil in Swift

    # If the node has a type and it's not a 'Nothing' equivalent
        
        ident = " " * self.ident
        swift_nil = "BOTTOM(){}".format(
            
            " as " + self.get_type_name(node.t) )
        if node.t:
            t_name = self.get_type_name(node.t)
            if t_name.startswith('inout '):
                t_name = t_name[6:]
            segs = t_name.split(' -> ', 1)
            if len(segs) > 1:
                if segs[0] == '(Void)':
                    t_name = t_name.replace('(Void)', '()')
            swift_nil = "BOTTOM(){}".format(
             " as " + t_name )

        
        if str(self.get_type_name(node.t)).startswith('Function'):
            swift_nil = f"{self.get_type_name(node.t)}"
    # Add indentation
        indented_nil = f"{ident}{swift_nil}"

    # Return the adapted Swift nil representation
        self._children_res.append(indented_nil)

    @append_to
    def visit_var_decl(self, node):
        old_ident = self.ident
        prefix = " " * (self.ident+1)
        self.ident = 0
        children = node.children()
        
        prev = self._cast_integers
        if node.var_type is None:
            self._cast_integers = True
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        
        #var_type = "let " if node.is_final else "var "
        var_type = "var "
        res = prefix + var_type + node.name
        
        type_name = ''
        if node.var_type is not None:
            type_name = self.get_type_name(node.var_type)
            #TODO Any
            """
            if type_name == '':
                type_name = 'Any'
            """
            if isinstance(children[0],ast.Lambda):
                res = res + ': '
            else:
                if type_name:
                    if type_name.startswith('Reference<'):
                        type_name = type_name[10:-1]
                    if type_name.startswith('inout '):
                        type_name = type_name[6:]
                    res = res + ": " + type_name + ' = '
                if type_name == '':
                    res = res + ' = '
        
        res += children_res[0]
        self.ident = old_ident
        self._cast_integers = prev
        self._children_res.append(res)
    
    

    @append_to
    def visit_func_decl(self, node):
        prev_is_unit = self.is_unit
        self.is_unit = node.get_type() == swift.VoidType()
        old_ident = self.ident
        self.ident += 2
        children = node.children()
        prefix = " " * old_ident
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        #print ('node.params', node.params)
        param_res = [children_res[i] for i, _ in enumerate(node.params)]
        len_params = len(node.params)
        len_type_params = len(node.type_parameters)
        #print ('type_params', node.type_parameters)
        type_parameters_res = ", ".join([str(_tp).replace(' any ',' ') for _tp in 
            children_res[len_params:len_type_params + len_params]])
        body_res = children_res[-1] if node.body else ''
        
        type_params = (
            "<" + type_parameters_res + ">" if type_parameters_res else "")
        #type_params = ''
        res = prefix + "func "  + node.name + type_params + "(" + ", ".join(
            param_res) + ")"

        if node.ret_type:
            res += " -> " + self.get_type_name(node.ret_type)
        res += " " + body_res
        
        self.ident = old_ident
        self._children_res.append(res)
    def type_arg2str(self, t_arg):
        """if t_arg.name.startswith('any'):
            t_arg.name = 'any ' + t_arg.name
        """
        if not isinstance(t_arg, tp.WildCardType):
            return self.get_type_name(t_arg)
        return self.get_type_name(t_arg.bound)
        if t_arg.is_invariant():
            return "*"
        elif t_arg.is_covariant():
            return "out " + self.get_type_name(t_arg.bound)
        else:
            return "in " + self.get_type_name(t_arg.bound)
        
    def visit_program(self, node):
        self.context = node.context
        children = node.children()
        for c in children:
            c.accept(self)
        
            
        package_str = ''
        bottom_const = 'func BOTTOM<T>() -> T { fatalError("x"); }'
        imports = ['CoreML','CoreFoundation','Accelerate','MusicKit','Foundation','CreateML','Charts','AppIntents','SwiftUI','RealityKit','SwiftData','ExtensionKit']
        imports = '\n'.join(['import ' + i for i in imports])

       
        self.program = imports + '\n' + bottom_const + '\n' + '\n\n'.join(
            self.pop_children_res(children))
    @append_to
    def visit_type_param(self, node):
        self._children_res.append("{}{}{}{}".format(
            node.variance_to_string(),
            ' ' if node.variance != tp.Invariant else '',
            node.name,
            ': ' + (
                self.get_type_name(node.bound)
                if node.bound is not None
                else swift.AnyType().name
            )
        ))
    @append_to
    def visit_param_decl(self, node):
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in node.children():
            c.accept(self)
        self.ident = old_ident
        """
        *need support for varargs and closures
        """
        res = node.name + ": " + self.get_type_name(node.param_type)

        if len(children):
            children_res = self.pop_children_res(children)
            res += " = " + children_res[0]
        self._children_res.append(res)
    @append_to
    def visit_call_argument(self, node):
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in node.children():
            c.accept(self)
        self.ident = old_ident
        children_res = self.pop_children_res(children)
        res = children_res[0]
        is_inout = node.inout
        if is_inout:
            res = '&' + res

        if node.name:
            res = node.name + ": " + res
        self._children_res.append(res)
    @append_to
    def visit_field_access(self, node):
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        self.ident = old_ident
        if children:
            receiver_expr = (
                '({}).'.format(children_res[0])
                if isinstance(node.expr, ast.BottomConstant)
                else "{}.".format(children_res[0])
            )
        else:
            receiver_expr = ""
        field = node.field
        if receiver_expr:
            field = f"{field}"
        res = "{}{}{}".format(" " * self.ident, receiver_expr, field)
        self._children_res.append(res)

    @append_to
    def visit_field_decl(self, node):
        prefix = ''
        prefix += 'let ' if node.is_final else 'var '
        res = prefix + node.name + ": " + self.get_type_name(node.field_type)
        self._children_res.append(res)


    def visit_integer_constant(self, node):
        
        literal = str(node.literal)
        literal = (
            "(" + literal + ")"
            if literal[0] == '-'
            else literal
        )
        self._children_res.append(literal)
    @append_to
    def visit_real_constant(self, node):
        real_types = {
            #there is no 'f' suffix in swift
            swift.Float: ""
        }
        suffix = real_types.get(node.real_type, "")
        self._children_res.append(
            " " * self.ident + str(node.literal) + suffix)

    @append_to
    def visit_char_constant(self, node):
        """Characters in Swift require double quotes like Strings
        """
        self._children_res.append('{}"{}"'.format(
            " " * self.ident, node.literal))

    @append_to
    def visit_string_constant(self, node):
        self._children_res.append('{}"{}"'.format(
            " " * self.ident, node.literal))

    @append_to
    def visit_boolean_constant(self, node):
        self._children_res.append(" " * self.ident + str(node.literal))
    @append_to
    def visit_variable(self, node):
        self._children_res.append(" " * self.ident + node.name)
    @append_to
    def visit_block(self, node):
        children = node.children()
        is_unit = self.is_unit
        is_lambda = self.is_lambda
        self.is_unit = False
        self.is_lambda = False
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        res = "{" if not is_lambda else ""
        res += "\n" + "\n".join(children_res[:-1])
        if children_res[:-1]:
            res += "\n"
        ret_keyword = " " * self.ident + "return " if node.is_func_block and not is_unit else ""#and not is_lambda 
        if children_res:
            res += " " * self.ident + ret_keyword + \
                   children_res[-1] + "\n" + \
                   " " * self.ident
        else:
            res += " " * self.ident + ret_keyword + "\n" + \
                   " " * self.ident
        res += "}" if not is_lambda else "" 
        self.is_unit = is_unit
        self.is_lambda = is_lambda
        self._children_res.append(res)

    @append_to
    def visit_func_call(self, node):
        """
        need to handle:
          *varargs
        
        """
        
        
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)
        self.ident = old_ident
        children_res = self.pop_children_res(children)
        type_args = (
            "<" + ",".join(
                [self.get_type_name(t) for t in node.type_args]) + ">"
            if not node.can_infer_type_args and node.type_args
            else ""
        )
        segs = node.func.rsplit(".", 1)
        if node.receiver:
            receiver_expr = (
                '({})'.format(children_res[0])
                if isinstance(node.receiver, ast.BottomConstant)
                else children_res[0]
            )
            func = node.func
            args = children_res[1:]
        else:
            receiver_expr, func = (
                ("", node.func)
                if len(segs) == 1
                else (segs[0], segs[1])
            )
            args = children_res
        if receiver_expr:
            receiver_expr += "."

        named_parameters = node.names
        func = segs[-1] #TODO check if this is correct SWIFT 
        
        
            
        res = "{ident}{rec}{func}({args})".format(
            ident=" " * self.ident,
            rec=receiver_expr,
            func=func,
            args=", ".join(args)
        )
        if str(func).endswith('...'):
            func = '...'
        elif str(func).endswith('..<'):
            func = '..<'
        else:
            func = str(func).split('.')[-1]
        

        non_letter_pattern = r'[^a-zA-Z]'
        # Finding all non-letter characters
        binary_op = re.findall(non_letter_pattern, func)
        binary_op = ''.join(binary_op)
        if binary_op == func:
            binary_op = " " + binary_op + " "
            if args[0].startswith('&'):
                args = [args[0][1:] if i==0 else args[i] for i in range(len(args))]
            #ar = [str(a).split(': ')[-1] for a in args] #drop the name of the parameter, idk why it is here
            #print(ar)
            res = "({args})".format(args=binary_op.join(args))
        if func == 'subscript':
            res = "{ident}{rec}[{args}]".format(
            ident=" " * self.ident,
            rec=receiver_expr[:-1],
            args=", ".join(args)
        )
        throws = True if node.throws else False
        if throws:
            res = "(try! " + res + ")"
         
        self._children_res.append(res)
    @append_to
    def visit_binary_op(self, node):
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        res = "{}({} {} {})".format(
            " " * old_ident, children_res[0], node.operator,
            children_res[1])
        self.ident = old_ident
        self._children_res.append(res)
    def visit_logical_expr(self, node):
        self.visit_binary_op(node)
    def visit_comparison_expr(self, node):
        self.visit_binary_op(node)

    def visit_arith_expr(self, node):
        self.visit_binary_op(node)
    """
    @append_to
    def visit_conditional(self, node): #XXX
        old_ident = self.ident
        self.ident += 2
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        res = "{}(if ({})\n{}\n{}else\n{})".format(
            " " * old_ident, children_res[0][self.ident:], children_res[1],
            " " * old_ident, children_res[2])
        self.ident = old_ident
        self._children_res.append(res)
    """
    @append_to
    def visit_class_decl(self, node):
        old_ident = self.ident
        self.ident += 2
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        field_res = [children_res[i]
                     for i, _ in enumerate(node.fields)]
        len_fields = len(field_res)
        superclasses_res = [children_res[i + len_fields]
                            for i, _ in enumerate(node.superclasses)]
        len_supercls = len(superclasses_res)
        function_res = [children_res[i + len_fields + len_supercls]
                        for i, _ in enumerate(node.functions)]
        len_functions = len(function_res)
        type_parameters_res = ", ".join(
            children_res[len_fields + len_supercls + len_functions:])

        is_sam = tu.is_sam(self.context, cls_decl=node)
        class_prefix = "interface" if is_sam else node.get_class_prefix()
        body = ""
        if function_res:
            body = " {{\n{function_res}\n{old_ident}}}".format(
                function_res="\n\n".join(function_res),
                old_ident=" " * old_ident
            )

        res = "{ident}{f}{o}{p} {n}".format(
            ident=" " * old_ident,
            f="fun " if is_sam else "",
            o="open " if (not node.is_final and
                          node.class_type != ast.ClassDeclaration.INTERFACE and
                          not is_sam) else "",
            p=class_prefix,
            n=node.name,
            tps="<" + type_parameters_res + ">" if type_parameters_res else "",
            fields="(" + ", ".join(field_res) + ")" if field_res else "",
            s=": " + ", ".join(superclasses_res) if superclasses_res else "",
            body=body
        )

        if type_parameters_res:
            res = "{}<{}>".format(res, type_parameters_res)
        if field_res:
            res = "{}({})".format(
                res, ", ".join(field_res))
        if superclasses_res:
            res += ": " + ", ".join(superclasses_res)
        if function_res:
            res += " {\n" + "\n\n".join(
                function_res) + "\n" + " " * old_ident + "}"
        self.ident = old_ident
        self._children_res.append(res)
    @append_to
    def visit_assign(self, node):
        old_ident = self.ident
        prev = self._cast_integers
        self._cast_integers = True
        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)
        self.ident = old_ident
        children_res = self.pop_children_res(children)
        if node.receiver:
            receiver_expr = (
                '({})'.format(children_res[0])
                if isinstance(node.receiver, ast.BottomConstant)
                else children_res[0]
            )
            res = "{}{}.{} = {}".format(" " * old_ident, receiver_expr,
                                        node.name, children_res[1])
        else:
            res = "{}{} = {}".format(" " * old_ident, node.name,
                                     children_res[0])
        self.ident = old_ident
        self._cast_integers = prev
        self._children_res.append(res)
    @append_to
    def visit_new(self, node):
        old_ident = self.ident
        self.ident = 0
        children = node.children()
        for c in children:
            c.accept(self)
        children_res = self.pop_children_res(children)
        self.ident = old_ident
        # Remove type arguments from Parameterized Type
        _args=children_res[:len(node.args)]
        #args = ', '.join(args)
        
        named_parameters = node.names
        if named_parameters and len(named_parameters) == len(node.args):
            args = ', '.join([str(_args[i]) if named_parameters[i] is None else str(named_parameters[i]) + ': ' + str(_args[i]) for i in range(len(named_parameters))])
        else:
            args = ', '.join(_args)
        
        #args = ', '.join(_args)
        



        if getattr(node.class_type, 'can_infer_type_args', None) is True:
            prefix = (
                node.class_type.name.rsplit(".", 1)[1]
                if node.receiver
                else node.class_type.name
            )
            cls = prefix
            self._children_res.append("{ident}{rec}{name}({args})".format(
                ident=" " * self.ident,
                rec=children_res[-1] + "." if node.receiver else "",
                name=cls,
                args=args))
        else:
            cls = self.get_type_name(node.class_type)
            segs = cls.split("<", 1)
            prefix = (
                segs[0].rsplit(".", 1)[1]
                if node.receiver and len(segs[0].rsplit(".", 1))>1
                else segs[0]
            )
            cls = prefix if len(segs) == 1 else prefix + "<" + segs[1]
            self._children_res.append("{ident}{rec}{name}({args})".format(
                ident=" " * self.ident,
                rec=children_res[-1] + "." if node.receiver else "",
                name=cls,
                args=args))
    def instance_type2str(self, t):
        basename = t.t_constructor.basename
        if not t.t_constructor.extra_type_params:
            enclosing_str = self.get_type_name(
                t.t_constructor.enclosing_type.new(t.type_args))
            return f"{enclosing_str}.{basename}"

        type_params = t.t_constructor.enclosing_type.type_parameters
        enclosing_str = self.get_type_name(
            t.t_constructor.enclosing_type.new(t.type_args[:len(type_params)]))
        extra_type_args = ", ".join(self.type_arg2str(ta)
                                    for ta in t.type_args[len(type_params):])
        return f"{enclosing_str}.{basename}<{extra_type_args}>"
    def get_type_name(self, t):
        #TODO check if function type and output the right syntax for swift
        
        """
        if (t.name == 'Reference'):
            print('typeargs',t.type_args)
            type_args = [self.get_type_name(ta) for ta in t.type_args]
            print('type_args list', type_args)
            return type_args[0] #TODO check if works
        """
        
            
        if t.is_wildcard():
            t = t.get_bound_rec()
            return self.get_type_name(t)
        
        if isinstance(t, swift.RawType):
            converted_t = t.t_constructor.new(
                [tp.WildCardType()
                 for _ in range(len(t.t_constructor.type_parameters))])
            return self.get_type_name(converted_t)
        t_constructor = getattr(t, 't_constructor', None)
        if isinstance(t_constructor,swift.ReferenceType):
            str_t = self.get_type_name(t.type_args[0])
            return 'inout ' + str_t
        if not t_constructor:
            """if t.name.startswith('any'):
                t.name = t.name[4:]
            """

            return t.get_name()
        
        
        if t.is_instance_type():
            return self.instance_type2str(t)
        
        funtion_pattern = r'Function\d+'
        match = re.match(funtion_pattern, t.name)
        if match:
            ret = self.get_type_name(t.type_args[-1])
            params = ", ".join(self.get_type_name(ta)
                                   for ta in t.type_args[:-1])
            return f"({params}) -> {ret}"
        if t.name.startswith('Tuple'):
            ta_  = ", ".join(self.get_type_name(ta)
                                   for ta in t.type_args)
            return f"({ta_})"
        
        if isinstance(t_constructor, swift.NullableType):
            str_t = self.get_type_name(t.type_args[0])
            if str_t.startswith('any '):
                return "({})?".format(str_t)
            else: 
                return "{}?".format(str_t)
        return "{}<{}>".format(t.name, ", ".join([self.type_arg2str(ta)
                                                  for ta in t.type_args]))  
    