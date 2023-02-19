from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict
import re


from src.ir import BUILTIN_FACTORIES, types as tp, kotlin_types as kt
from src.ir.builtins import BuiltinFactory


def map_type(f):
    def inner(parser: TypeParser, str_t: str):
        segs = str_t.split("<", 1)
        type_name = segs[0]
        if type_name in parser.mapped_types:
            mapped_type, mapped_parser = parser.mapped_types[type_name]
            str_t = mapped_type + (segs[1] if len(segs) == 2 else "")
            return mapped_parser.parse_type(mapped_type)
        else:
            return f(parser, str_t)
    return inner


class TypeParser(ABC):
    def __init__(self, target_language: str,
                 class_type_name_map: Dict[str, tp.TypeParameter] = None,
                 func_type_name_map: Dict[str, tp.TypeParameter] = None,
                 classes_type_parameters: dict = None,
                 type_spec: Dict[str, tp.Type] = None,
                 mapped_types: Dict[str, tuple] = None):
        self.bt_factory: BuiltinFactory = BUILTIN_FACTORIES[target_language]
        self.class_type_name_map = class_type_name_map or {}
        self.func_type_name_map = func_type_name_map or {}
        self.classes_type_parameters = classes_type_parameters or {}
        self.type_spec = type_spec or {}
        self.mapped_types = mapped_types or {}

    @abstractmethod
    def parse_function_type(self, str_t: str) -> tp.ParameterizedType:
        pass

    @abstractmethod
    def parse_wildcard(self, str_t: str) -> tp.WildCardType:
        pass

    @abstractmethod
    def parse_type_parameter(self, str_t: str, keep: bool) -> tp.TypeParameter:
        pass

    @abstractmethod
    def parse_type(self, str_t) -> tp.Type:
        pass


class JavaTypeParser(TypeParser):
    def __init__(self, target_language: str,
                 class_type_name_map: Dict[str, tp.TypeParameter] = None,
                 func_type_name_map: Dict[str, tp.TypeParameter] = None,
                 classes_type_parameters: dict = None,
                 type_spec: Dict[str, tp.Type] = None,
                 mapped_types: Dict[str, tuple] = None):
        super().__init__(target_language, class_type_name_map,
                         func_type_name_map, classes_type_parameters,
                         type_spec, mapped_types)

    def parse_function_type(self, str_t: str) -> tp.ParameterizedType:
        pass

    def parse_wildcard(self, str_t) -> tp.WildCardType:
        if str_t == "?":
            return tp.WildCardType()
        if "extends" in str_t:
            return tp.WildCardType(
                self.parse_type(str_t.split(" extends ", 1)[1]),
                variance=tp.Covariant)
        else:
            return tp.WildCardType(
                self.parse_type(str_t.split(" super ", 1)[1]),
                variance=tp.Contravariant)

    def parse_type_parameter(self, str_t: str,
                             keep: bool = False) -> tp.TypeParameter:
        segs = str_t.split(" extends ")
        type_var_map = deepcopy(self.class_type_name_map)
        type_var_map.update(self.func_type_name_map)
        if keep:
            # It might be the case where the names of function's and class's
            # type parameters conflict. In this case, we should not replace
            # the name of a function's type parameter with the name
            # of the corresponding class type parameter.
            type_var_map = {}

        if len(segs) == 1:
            return type_var_map.get(str_t, tp.TypeParameter(str_t))
        bound = self.parse_type(segs[1])
        return type_var_map.get(segs[0],
                                tp.TypeParameter(segs[0], bound=bound))

    def parse_reg_type(self, str_t: str) -> tp.Type:
        if str_t.startswith("?"):
            return self.parse_wildcard(str_t)
        segs = str_t.split(".")
        is_type_var = (
            len(segs) == 1 or
            (
                " extends " in str_t and
                "." not in str_t.split(" extends ")[0]
             )
        )
        if is_type_var:
            return self.parse_type_parameter(str_t)
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        segs = str_t.split("<", 1)
        if len(segs) == 1:
            parsed_t = tp.SimpleClassifier(str_t)
            return self.type_spec.get(str_t, parsed_t)
        base, type_args_str = segs[0], segs[1][:-1]
        type_args = re.findall(regex, type_args_str)
        new_type_args = []
        for type_arg in type_args:
            new_type_args.append(self.parse_type(type_arg))
        type_var_map = self.classes_type_parameters.get(base) or {}
        values = list(type_var_map.values())
        type_vars = [
            (
                values[i]
                if i < len(values)
                else tp.TypeParameter(base + ".T" + str(i + 1))
            )
            for i in range(len(new_type_args))
        ]
        parsed_t = self.type_spec.get(base, tp.TypeConstructor(base,
                                                               type_vars))
        return parsed_t.new(new_type_args)

    def parse_type(self, str_t: str) -> tp.Type:
        tf = self.bt_factory
        if str_t.endswith("[]"):
            str_t = str_t.split("[]")[0]
            return tf.get_array_type().new([self.parse_type(str_t)])
        elif str_t.endswith("..."):
            # TODO consider this as a vararg rather than a single type.
            return self.parse_type(str_t.split("...")[0])
        else:
            return self._parse_type(str_t)

    @map_type
    def _parse_type(self, str_t: str) -> tp.Type:
        tf = self.bt_factory
        if str_t in ["char", "java.lang.Character"]:
            primitive = str_t == "char"
            return tf.get_char_type(primitive)
        elif str_t in ["byte", "java.lang.Byte"]:
            primitive = str_t == "byte"
            return tf.get_byte_type(primitive)
        elif str_t in ["short", "java.lang.Short"]:
            primitive = str_t == "short"
            return tf.get_short_type(primitive=primitive)
        elif str_t in ["int", "java.lang.Integer"]:
            primitive = str_t == "int"
            return tf.get_integer_type(primitive=primitive)
        elif str_t in ["long", "java.lang.Long"]:
            primitive = str_t == "long"
            return tf.get_long_type(primitive=primitive)
        elif str_t in ["float", "java.lang.Float"]:
            primitive = str_t == "float"
            return tf.get_float_type(primitive=primitive)
        elif str_t in ["double", "java.lang.Double"]:
            primitive = str_t == "double"
            return tf.get_double_type(primitive=primitive)
        elif str_t in ["boolean", "java.lang.Boolean"]:
            primitive = str_t == "boolean"
            return tf.get_boolean_type(primitive=primitive)
        elif str_t == "java.lang.String":
            return tf.get_string_type()
        elif str_t == "java.lang.Object":
            return tf.get_any_type()
        elif str_t == "java.lang.BigDecimal":
            return tf.get_double_type()
        elif str_t == "void":
            return tf.get_void_type()
        else:
            return self.parse_reg_type(str_t)


class KotlinTypeParser(TypeParser):
    FUNC_SEP_REGEX = re.compile(r"->(?![^()]*\))")

    COMMA_SEP_REGEX = re.compile(r"(?:[^,<(]|\([^)]*\)|<[^>]*>)+")

    FUNC_REGEX = re.compile(r"^\(.*\) -> .*")

    def __init__(self,
                 class_type_name_map: Dict[str, tp.TypeParameter] = None,
                 func_type_name_map: Dict[str, tp.TypeParameter] = None,
                 classes_type_parameters: dict = None,
                 type_spec: Dict[str, tp.Type] = None,
                 mapped_types: Dict[str, tuple] = None):
        super().__init__("kotlin", class_type_name_map,
                         func_type_name_map, classes_type_parameters,
                         type_spec, mapped_types)

    def is_func_type(self, str_t: str) -> bool:
        return bool(re.match(self.FUNC_REGEX, str_t))

    def parse_function_type(self, str_t: str) -> tp.ParameterizedType:
        segs = self.FUNC_SEP_REGEX.split(str_t, 1)
        assert len(segs) == 2
        param_strs = re.findall(self.COMMA_SEP_REGEX, segs[0].rstrip()[1:-1])
        param_types = [
            self.parse_type(param_str.strip().split(": ", 1)[-1])
            for param_str in param_strs
        ]
        ret_type = self.parse_type(segs[1].lstrip())
        return self.bt_factory.get_function_type(len(param_types)).new(
            param_types + [ret_type]
        )

    def parse_wildcard(self, str_t) -> tp.WildCardType:
        if str_t == "*":
            return tp.WildCardType()
        if "out " in str_t:
            return tp.WildCardType(
                self.parse_type(str_t.split("out ", 1)[1].lstrip()),
                variance=tp.Covariant)
        else:
            return tp.WildCardType(
                self.parse_type(str_t.split("in ", 1)[1].lstrip()),
                variance=tp.Contravariant)

    def parse_type_parameter(self, str_t: str,
                             keep: bool = False) -> tp.TypeParameter:
        if str_t.startswith("out "):
            variance = tp.Covariant
            type_param = str_t.split("out ", 1)[1]
        elif str_t.startswith("in "):
            variance = tp.Contravariant
            type_param = str_t.split("in ", 1)[1]
        else:
            variance = tp.Invariant
            type_param = str_t
        segs = type_param.split(":")
        type_var_map = deepcopy(self.class_type_name_map)
        type_var_map.update(self.func_type_name_map)
        if keep:
            # It might be the case where the names of function's and class's
            # type parameters conflict. In this case, we should not replace
            # the name of a function's type parameter with the name
            # of the corresponding class type parameter.
            type_var_map = {}

        if len(segs) == 1:
            return type_var_map.get(type_param,
                                    tp.TypeParameter(type_param,
                                                     variance=variance))
        bound = self.parse_type(segs[1].lstrip())
        return type_var_map.get(
            segs[0].rstrip(),
            tp.TypeParameter(segs[0].rstrip(), variance=variance, bound=bound))

    def parse_reg_type(self, str_t: str) -> tp.Type:
        if str_t.startswith("*") or str_t.startswith("out ") or \
                str_t.startswith("in "):
            return self.parse_wildcard(str_t)
        segs = str_t.split(".")
        is_type_var = (
            len(segs) == 1 or
            (
                ": " in str_t and
                "." not in str_t.split(":")[0]
             )
        )
        if is_type_var:
            return self.parse_type_parameter(str_t)
        regex = re.compile(r'(?:[^,<]|<[^>]*>)+')
        segs = str_t.replace(", ", ",").split("<", 1)
        if len(segs) == 1:
            parsed_t = tp.SimpleClassifier(str_t)
            return self.type_spec.get(str_t, parsed_t)
        base, type_args_str = segs[0], segs[1][:-1]
        type_args = re.findall(regex, type_args_str)
        new_type_args = []
        for type_arg in type_args:
            new_type_args.append(self.parse_type(type_arg))
        type_var_map = self.classes_type_parameters.get(base) or {}
        values = list(type_var_map.values())
        type_vars = [
            (
                values[i]
                if i < len(values)
                else tp.TypeParameter(base + ".T" + str(i + 1))
            )
            for i in range(len(new_type_args))
        ]
        parsed_t = self.type_spec.get(base, tp.TypeConstructor(base,
                                                               type_vars))
        return parsed_t.new(new_type_args)

    def parse_type(self, str_t: str) -> tp.Type:
        tf = self.bt_factory
        if self.is_func_type(str_t):
            return self.parse_function_type(str_t)
        if str_t.startswith("("):
            str_t = str_t[1:]
        if str_t.endswith(")"):
            str_t = str_t[:-1]
        if str_t.endswith("?"):
            # This is a nullable type.
            return kt.NullableType().new([self.parse_type(str_t[:-1])])
        elif str_t.startswith("kotlin.Array<"):
            str_t = str_t.split("kotlin.Array<")[1][:-1]
            return tf.get_array_type().new([self.parse_type(str_t)])
        else:
            return self._parse_type(str_t)

    @map_type
    def _parse_type(self, str_t: str) -> tp.Type:
        tf = self.bt_factory
        if str_t == "kotlin.CharArray":
            return kt.CharArray
        elif str_t == "kotlin.ByteArray":
            return kt.ByteArray
        elif str_t == "kotlin.ShortArray":
            return kt.ShortArray
        elif str_t == "kotlin.IntArray":
            return kt.IntegerArray
        elif str_t == "kotlin.LongArray":
            return kt.LongArray
        elif str_t == "kotlin.FloatArray":
            return kt.FloatArray
        elif str_t == "kotlin.DoubleArray":
            return kt.DoubleArray
        elif str_t == "int[]":
            return kt.IntegerArray
        elif str_t.startswith("vararg "):
            return self.parse_type(str_t.split("vararg ")[1])
        elif str_t == "java.lang.Byte":
            return tp.SimpleClassifier("Byte?")
        elif str_t == "java.lang.Short":
            return tp.SimpleClassifier("Short?")
        elif str_t == "java.lang.Integer":
            return tp.SimpleClassifier("Int?")
        elif str_t == "java.lang.Long":
            return tp.SimpleClassifier("Long?")
        elif str_t == "java.lang.Float":
            return tp.SimpleClassifier("Float?")
        elif str_t == "java.lang.Double":
            return tp.SimpleClassifier("Double?")
        elif str_t == "java.lang.Character":
            return tp.SimpleClassifier("Char?")
        elif str_t == "java.lang.Boolean":
            return tp.SimpleClassifier("Boolean?")
        elif str_t in ["kotlin.Char", "char", "Char"]:
            return tf.get_char_type()
        elif str_t in ["kotlin.Byte", "byte", "Byte"]:
            return tf.get_byte_type()
        elif str_t in ["kotlin.Short", "short", "Short"]:
            return tf.get_short_type()
        elif str_t in ["kotlin.Int", "int", "Int"]:
            return tf.get_integer_type()
        elif str_t in ["kotlin.Long", "long", "Long"]:
            return tf.get_long_type()
        elif str_t in ["kotlin.Float", "float", "Float"]:
            return tf.get_float_type()
        elif str_t in ["kotlin.Double", "double", "Double"]:
            return tf.get_double_type()
        elif str_t in ["kotlin.Boolean", "boolean", "Boolean"]:
            return tf.get_boolean_type()
        elif str_t in ["kotlin.String", "java.lang.String", "String"]:
            return tf.get_string_type()
        elif str_t in ["kotlin.Number", "java.lang.Number", "Number"]:
            return tf.get_number_type()
        elif str_t in ["kotlin.Any", "java.lang.Object", "Any"]:
            return tf.get_any_type()
        elif str_t == "java.lang.BigDecimal":
            return tf.get_double_type()
        elif str_t in ["kotlin.Unit", "void", "Void", "Unit"]:
            return tf.get_void_type()
        else:
            return self.parse_reg_type(str_t)
