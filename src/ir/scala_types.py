# pylint: disable=abstract-method, useless-super-delegation,too-many-ancestors
from typing import List

import src.ir.types as tp

import src.ir.builtins as bt


class ScalaBuiltinFactory(bt.BuiltinFactory):
    def get_language(self):
        return "scala"

    def get_builtin(self):
        return ScalaBuiltin

    def get_void_type(self):
        return UnitType()

    def get_any_type(self):
        return AnyType()

    def get_anyref_type(self):
        return AnyRefType()

    def get_number_type(self):
        return NumberType()

    def get_integer_type(self, primitive=False):
        return IntegerType()

    def get_byte_type(self, primitive=False):
        return ByteType()

    def get_short_type(self, primitive=False):
        return ShortType()

    def get_long_type(self, primitive=False):
        return LongType()

    def get_float_type(self, primitive=False):
        return FloatType()

    def get_double_type(self, primitive=False):
        return DoubleType()

    def get_big_decimal_type(self):
        return DoubleType()

    def get_big_integer_type(self):
        return IntegerType()

    def get_boolean_type(self, primitive=False):
        return BooleanType()

    def get_char_type(self, primitive=False):
        return CharType()

    def get_string_type(self):
        return StringType()

    def get_array_type(self):
        return ArrayType()

    def get_function_type(self, nr_parameters=0):
        return FunctionType(nr_parameters)

    def get_nothing(self):
        return NothingType()

    def get_non_nothing_types(self):
        types = super().get_non_nothing_types()
        types.extend([
            SeqType()
        ])
        return types

    def get_raw_type(self, t_constructor):
        return RawType(t_constructor)

    def get_raw_cls(self):
        return RawType


class ScalaBuiltin(tp.Builtin):
    def __str__(self):
        return str(self.name) + "(scala-builtin)"

    def is_primitive(self):
        return False


class AnyType(ScalaBuiltin):
    def __init__(self, name="Any"):
        super().__init__(name)

    def get_builtin_type(self):
        return bt.Any


class AnyRefType(AnyType):
    def __init__(self, name="AnyRef"):
        super().__init__(name)
        self.supertypes.append(AnyType())


class NothingType(ScalaBuiltin):
    def __init__(self, name="Nothing"):
        super().__init__(name)

    def is_subtype(self, other):
        return True

    def get_builtin_type(self):
        return bt.Nothing


class UnitType(AnyType):
    def __init__(self, name="Unit"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Void


class NumberType(AnyRefType):
    def __init__(self, name="Number"):
        super().__init__(name)
        self.supertypes.append(AnyRefType())

    def get_builtin_type(self):
        return bt.Number


class IntegerType(AnyType):
    def __init__(self, name="Int"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Integer


class ShortType(AnyType):
    def __init__(self, name="Short"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Short


class LongType(AnyType):
    def __init__(self, name="Long"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Long


class ByteType(AnyType):
    def __init__(self, name="Byte"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Byte


class FloatType(AnyType):
    def __init__(self, name="Float"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Float


class DoubleType(AnyType):
    def __init__(self, name="Double"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Double


class CharType(AnyType):
    def __init__(self, name="Char"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Char


class StringType(AnyRefType):
    def __init__(self, name="String"):
        super().__init__(name)
        self.supertypes.append(AnyRefType())

    def get_builtin_type(self):
        return bt.String


class BooleanType(AnyType):
    def __init__(self, name="Boolean"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Boolean


class RawType(tp.SimpleClassifier):
    def __init__(self, t_constructor: tp.TypeConstructor):
        self._name = t_constructor.name
        self.name = f"Raw{self._name}"
        self.t_constructor = t_constructor
        self.supertypes = []
        for supertype in t_constructor.supertypes:
            if not supertype.is_parameterized():
                self.supertypes.append(supertype)
            else:
                # Consider B<T> : A<T>
                # We convert the supertype A<T> to A<?>.
                sub = {type_param: tp.WildCardType()
                       for type_param in supertype.t_constructor.type_parameters}
                self.supertypes.append(tp.substitute_type(supertype, sub))
        self.supertypes.append(AnyType())

    def get_name(self):
        return self._name

    def get_raw_cls(self):
        return RawType


class ArrayType(tp.TypeConstructor, AnyRefType):
    def __init__(self, name="Array"):
        # In Scala, arrays are invariant.
        super().__init__(name, [tp.TypeParameter("T")])
        self.supertypes.append(AnyRefType())


class SeqType(tp.TypeConstructor, AnyRefType):
    def __init__(self, name="Seq"):
        super().__init__(name, [tp.TypeParameter("T", variance=tp.Covariant)])
        self.supertypes.append(AnyRefType())


class FunctionType(tp.TypeConstructor, AnyRefType):
    is_native = True

    def __init__(self, nr_type_parameters: int):
        name = "Function" + str(nr_type_parameters)
        # We can have decl-variance in Scala
        type_parameters = [
            tp.TypeParameter("A" + str(i), tp.Contravariant)
            for i in range(1, nr_type_parameters + 1)
        ] + [tp.TypeParameter("R", tp.Covariant)]
        self.nr_type_parameters = nr_type_parameters
        super().__init__(name, type_parameters)
        self.supertypes.append(AnyRefType())

    @classmethod
    def match_function(cls, receiver_type: tp.Type, ret_type: tp.Type,
                       param_types: List[tp.Type],
                       target_type: tp.Type,
                       bt_factory: bt.BuiltinFactory,
                       func_metadata: dict = {}):
        import src.ir.type_utils as tu
        api_type = FunctionType(
            len(param_types)).new(param_types + [ret_type])
        sub = tu.unify_types(target_type, api_type, bt_factory, same_type=True)
        if any(v == bt_factory.get_void_type()
               for v in sub.values()):
            # We don't want to match something that is needed to be
            # instantiated with void, e.g.,
            # Consumer<Int> != Function<Int, void>
            return False, None
        if sub or target_type == api_type:
            return True, sub
        return False, None

    @classmethod
    def get_param_types(cls, etype: tp.ParameterizedType):
        return etype.type_args[:-1]

    @classmethod
    def get_ret_type(cls, etype: tp.ParameterizedType):
        return etype.type_args[-1]


class TupleType(tp.TypeConstructor, AnyRefType):
    def __init__(self, n_type_parameters: int):
        name = "Tuple" + str(n_type_parameters)
        # We can have decl-variance in Scala
        type_parameters = [
            tp.TypeParameter("A" + str(i + 1), tp.Contravariant)
            for i in range(n_type_parameters)
        ]
        self.nr_type_parameters = n_type_parameters
        super().__init__(name, type_parameters)
        self.supertypes.append(AnyRefType())


Any = AnyType()
Nothing = NothingType()
Unit = UnitType()
Number = NumberType()
Integer = IntegerType()
Short = ShortType()
Long = LongType()
Byte = ByteType()
Float = FloatType()
Double = DoubleType()
Char = CharType()
String = StringType()
Boolean = BooleanType()
Array = ArrayType()
Seq = SeqType()
AnyRef = AnyRefType()

NonNothingTypes = [Any, Number, Integer, Short, Long, Byte, Float,
                   Double, Char, String, Boolean, Array, Seq]
