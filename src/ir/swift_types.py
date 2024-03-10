# pylint: disable=abstract-method, useless-super-delegation,too-many-ancestors
from typing import List

import src.ir.types as tp

import src.ir.builtins as bt


class SwiftBuiltinFactory(bt.BuiltinFactory):

    generic_whitelist = set()
    def get_language(self):
        return "swift"
    def get_generic_whitelist(self):
        return self.generic_whitelist
    def get_builtin(self):
        return SwiftBuiltin

    def get_void_type(self):
        return VoidType()

    def get_any_type(self):
        return AnyType()

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
        # FIXME
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
    
    def get_tuple_type(self, nr_parameters=0):
        return TupleType(nr_parameters)

    

    def get_non_nothing_types(self):
        types = super().get_non_nothing_types()
        
        return types

    def get_raw_type(self, t_constructor):
        return RawType(t_constructor)

    def get_raw_cls(self):
        return RawType


class SwiftBuiltin(tp.Builtin):
    def __str__(self):
        return str(self.name) + "(swift-builtin)"

    def is_primitive(self):
        return False


class AnyType(SwiftBuiltin, ):
    def __init__(self, name="Any"):
        super().__init__(name)

    def get_builtin_type(self):
        return bt.Any




class VoidType(AnyType):
    def __init__(self, name="Void"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Void


class NumberType(AnyType):
    def __init__(self, name="Number"):
        super().__init__(name)
        self.supertypes.append(AnyType())

    def get_builtin_type(self):
        return bt.Number

class ByteType(NumberType):
    def __init__(self, name="Byte"):
        super().__init__(name)
        self.supertypes.append(NumberType())

    def get_builtin_type(self):
        return bt.Byte
class ShortType(NumberType):
    def __init__(self, name="Short"):
        super().__init__(name)
        self.supertypes.append(NumberType())

    def get_builtin_type(self):
        return bt.Short
class LongType(NumberType):
    def __init__(self, name="Long"):
        super().__init__(name)
        self.supertypes.append(NumberType())

    def get_builtin_type(self):
        return bt.Long


class IntegerType(NumberType):
    """
    Represents the Swift Int type, supertypes taken from https://developer.apple.com/documentation/swift/int
    """
    def __init__(self, name="Int"):
        super().__init__(name)
        self.supertypes.append(NumberType())
        supertypes = [tp.SimpleClassifier("any Swift.AdditiveArithmetic"),
                      tp.SimpleClassifier("any Swift.BinaryInteger"),
                      tp.SimpleClassifier("any Swift.CVarArg"),
                      tp.SimpleClassifier("any Swift.CodingKeyRepresentable"),
                      tp.SimpleClassifier("any Swift.Comparable"),
                      tp.SimpleClassifier("any Swift.CustomReflectable"),
                      tp.SimpleClassifier("any Swift.CustomStringConvertible"),
                      tp.SimpleClassifier("any Swift.Decodable"),
                      tp.SimpleClassifier("any Swift.Encodable"),
                      tp.SimpleClassifier("any Swift.Equatable"),
                      tp.SimpleClassifier("any Swift.ExpressibleByIntegerLiteral"),
                      tp.SimpleClassifier("any Swift.FixedWidthInteger"),
                      tp.SimpleClassifier("any Swift.Hashable"),
                      tp.SimpleClassifier("any Swift.LosslessStringConvertible"),
                      tp.SimpleClassifier("any Swift.MirrorPath"),
                      tp.SimpleClassifier("any Swift.Numeric"),
                      tp.SimpleClassifier("any Swift.SIMDScalar"),
                      tp.SimpleClassifier("any Swift.SignedInteger"),
                      tp.SimpleClassifier("any Swift.SignedNumeric"),
                      tp.SimpleClassifier("any Swift.Strideable")]
        for supertype in supertypes:
            self.supertypes.append(supertype)
        
    
        

    def get_builtin_type(self):
        return bt.Integer




class FloatType(NumberType):
    """
    Represents the Swift Float type, supertypes taken from https://developer.apple.com/documentation/swift/float
    """
    def __init__(self, name="Float"):
        super().__init__(name)
        self.supertypes.append(NumberType())
        supertypes = [tp.SimpleClassifier("any Swift.AdditiveArithmetic"),
        tp.SimpleClassifier("any Accelerate.BNNSScalar"),
        tp.SimpleClassifier("any Swift.BinaryFloatingPoint"),
        tp.SimpleClassifier("any Swift.CVarArg"),
        tp.SimpleClassifier("any Swift.Comparable"),
        tp.SimpleClassifier("any Swift.CustomDebugStringConvertible"),
        tp.SimpleClassifier("any Swift.CustomReflectable"),
        tp.SimpleClassifier("any Swift.CustomStringConvertible"),
        tp.SimpleClassifier("any Swift.Decodable"),
        tp.SimpleClassifier("any Swift.Encodable"),
        tp.SimpleClassifier("any Swift.Equatable"),
        tp.SimpleClassifier("any Swift.ExpressibleByFloatLiteral"),
        tp.SimpleClassifier("any Swift.ExpressibleByIntegerLiteral"),
        tp.SimpleClassifier("any Swift.FloatingPoint"),
        tp.SimpleClassifier("any Swift.Hashable"),
        tp.SimpleClassifier("any Swift.LosslessStringConvertible"),
        tp.SimpleClassifier("any Coreml.MLShapedArrayScalar"),
        tp.SimpleClassifier("any Swift.Numeric"),
        tp.SimpleClassifier("any Swift.SIMDScalar"),
        tp.SimpleClassifier("any Swift.SignedNumeric"),
        tp.SimpleClassifier("any Swift.Strideable"),
        tp.SimpleClassifier("any Swift.TextOutputStreamable"),
        tp.SimpleClassifier("any Accelerate.vDSP_DiscreteFourierTransformable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointBiquadFilterable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointConvertable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointDiscreteFourierTransformable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointGeneratable")]
        for supertype in supertypes:
            self.supertypes.append(supertype)

    def get_builtin_type(self):
        return bt.Float


class DoubleType(NumberType):
    """
    Represents the Swift Double type, supertypes taken from https://developer.apple.com/documentation/swift/double
    """
    def __init__(self, name="Double"):
        super().__init__(name)
        self.supertypes.append(NumberType())
        supertypes = [tp.SimpleClassifier("any Swift.AdditiveArithmetic"),
        tp.SimpleClassifier("any Swift.BinaryFloatingPoint"),
        tp.SimpleClassifier("any Swift.CVarArg"),
        tp.SimpleClassifier("any Swift.Comparable"),
        tp.SimpleClassifier("any Swift.CustomDebugStringConvertible"),
        tp.SimpleClassifier("any Swift.CustomReflectable"),
        tp.SimpleClassifier("any Swift.CustomStringConvertible"),
        tp.SimpleClassifier("any Swift.Decodable"),
        tp.SimpleClassifier("any Swift.Encodable"),
        tp.SimpleClassifier("any Swift.Equatable"),
        tp.SimpleClassifier("any Swift.ExpressibleByFloatLiteral"),
        tp.SimpleClassifier("any Swift.ExpressibleByIntegerLiteral"),
        tp.SimpleClassifier("any Swift.FloatingPoint"),
        tp.SimpleClassifier("any Swift.Hashable"),
        tp.SimpleClassifier("any Swift.LosslessStringConvertible"),
        tp.SimpleClassifier("any Coreml.MLShapedArrayScalar"),
        tp.SimpleClassifier("any Swift.Numeric"),
        tp.SimpleClassifier("any Swift.SIMDScalar"),
        tp.SimpleClassifier("any Swift.SignedNumeric"),
        tp.SimpleClassifier("any Swift.Strideable"),
        tp.SimpleClassifier("any Swift.TextOutStreamable"),
        tp.SimpleClassifier("any Accelerate.vDSP_DiscreteFourierTransformable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointBiquadFilterable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointConvertable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointDiscreteFourierTransformable"),
        tp.SimpleClassifier("any Accelerate.vDSP_FloatingPointGeneratable")]
        for supertype in supertypes:
            self.supertypes.append(supertype)


    def get_builtin_type(self):
        return bt.Double


class CharType(AnyType):
    """
    Represents the Swift Character type, supertypes taken from https://developer.apple.com/documentation/swift/character
    """
    def __init__(self, name="Character"):
        super().__init__(name)
        self.supertypes.append(AnyType())
        supertypes = [tp.SimpleClassifier("any Swift.Comparable"),
        tp.SimpleClassifier("any Swift.CustomDebugStringConvertible"),
        tp.SimpleClassifier("any Swift.CustomReflectable"),
        tp.SimpleClassifier("any Swift.CustomStringConvertible"),
        tp.SimpleClassifier("any Swift.Equatable"),
        tp.SimpleClassifier("any Swift.ExpressibleByExtendedGraphemeClusterLiteral"),
        tp.SimpleClassifier("any Swift.ExpressibleByUnicodeScalarLiteral"),
        tp.SimpleClassifier("any Swift.Hashable"),
        tp.SimpleClassifier("any Swift.LosslessStringConvertible"),
        tp.SimpleClassifier("any Swift.RegexComponent"),
        tp.SimpleClassifier("any Swift.TextOutputStreamable")]
        for supertype in supertypes:
            self.supertypes.append(supertype)

    def get_builtin_type(self):
        return bt.Char


class StringType(AnyType):
    """
    Represents the Swift String type, supertypes taken from https://developer.apple.com/documentation/swift/string
    """
    def __init__(self, name="String"):
        super().__init__(name)
        self.supertypes.append(AnyType())
        supertypes = [tp.SimpleClassifier("any Swift.BidirectionalCollection"),
        tp.SimpleClassifier("any Swift.CVarArg"),
        tp.SimpleClassifier("any Swift.CodingKeyRepresentable"),
        tp.SimpleClassifier("any Swift.Collection"),
        tp.SimpleClassifier("any Swift.Comparable"),
        tp.SimpleClassifier("any Swift.CustomDebugStringConvertible"),
        tp.SimpleClassifier("any Swift.CustomReflectable"),
        tp.SimpleClassifier("any Swift.CustomStringConvertible"),
        tp.SimpleClassifier("any Swift.Decodable"),
        tp.SimpleClassifier("any Swift.Encodable"),
        tp.SimpleClassifier("any Swift.Equatable"),
        tp.SimpleClassifier("any Swift.ExpressibleByExtendedGraphemeClusterLiteral"),
        tp.SimpleClassifier("any Swift.ExpressibleByStringInterpolation"),
        tp.SimpleClassifier("any Swift.ExpressibleByStringLiteral"),
        tp.SimpleClassifier("any Swift.ExpressibleByUnicodeScalarLiteral"),
        tp.SimpleClassifier("any Swift.Hashable"),
        tp.SimpleClassifier("any Swift.LosslessStringConvertible"),
        tp.SimpleClassifier("any Swift.MirrorPath"),
        tp.SimpleClassifier("any Swift.RangeReplaceableCollection"),
        tp.SimpleClassifier("any Swift.RegexComponent"),
        tp.SimpleClassifier("any Swift.StringProtocol"),
        tp.SimpleClassifier("any Swift.TextOutputStream"),
        tp.SimpleClassifier("any Swift.TextOutputStreamable")]
        for supertype in supertypes:
            self.supertypes.append(supertype)
    def get_builtin_type(self):
        return bt.String


class BooleanType(AnyType):
    """
    Represents the Swift Bool type, supertypes taken from https://developer.apple.com/documentation/swift/bool
    """
    def __init__(self, name="Bool"):
        super().__init__(name)
        self.supertypes.append(AnyType())
        supertypes = [tp.SimpleClassifier("any Accelerate.BNNSScalar"),
        tp.SimpleClassifier("any Swift.CVarArg"),
        tp.SimpleClassifier("any Swift.CustomReflectable"),
        tp.SimpleClassifier("any Swift.CustomStringConvertible"),
        tp.SimpleClassifier("any Swift.Decodable"),
        tp.SimpleClassifier("any Swift.Encodable"),
        tp.SimpleClassifier("any Swift.Equatable"),
        tp.SimpleClassifier("any Swift.ExpressibleByBooleanLiteral"),
        tp.SimpleClassifier("any Swift.Hashable"),
        tp.SimpleClassifier("any Swift.LosslessStringConvertible")]
        for supertype in supertypes:
            self.supertypes.append(supertype)
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


class ArrayType(tp.TypeConstructor, AnyType):
    def __init__(self, name="Array"):
        # in swift arrays are covariant
        super().__init__(name, [tp.TypeParameter("T", variance=tp.Covariant)]) #TODO check varivance
        self.supertypes.append(AnyType())




class ReferenceType(tp.TypeConstructor):
    """
    a type representing inout parameters; inout Int -> Reference<Int>
    """
    def __init__(self, name="Reference"):
        super().__init__(name, [tp.TypeParameter("T", variance=tp.Invariant)]) #TODO check varivance 
        
class NullableType(tp.TypeConstructor):
    """
    a type representing nullable types; Int? -> Nullable<Int>
    """
    def __init__(self, name="Nullable"):
        super().__init__(name, [tp.TypeParameter("T", variance=tp.Covariant)]) #TODO check varivance 


class TupleType(tp.TypeConstructor):
    """
    Represents a tuple type with a fixed number of elements.
    """
    is_native = True

    def __init__(self, nr_type_parameters: int):
        name = "Tuple" + str(nr_type_parameters)
        type_parameters = [
            tp.TypeParameter("A" + str(i), tp.Invariant)
            for i in range(1, nr_type_parameters + 1)
        ]
        self.nr_type_parameters = nr_type_parameters
        super().__init__(name, type_parameters)


class FunctionType(tp.TypeConstructor, AnyType):
    """
    Represents closures
    """
    is_native = True

    def __init__(self, nr_type_parameters: int):
        name = "Function" + str(nr_type_parameters)
        #name = ''
        type_parameters = [
            tp.TypeParameter("A" + str(i), tp.Contravariant)
            for i in range(1, nr_type_parameters + 1)
        ] + [tp.TypeParameter("R", tp.Covariant)]
        self.nr_type_parameters = nr_type_parameters
        super().__init__(name, type_parameters)
        #self.supertypes.append(AnyType()) TODO 

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


class FunctionTypeWithReceiver(FunctionType):
    is_native = True

    def __init__(self, nr_type_parameters: int, is_suspend: bool = False):
        super().__init__(nr_type_parameters + 1, is_suspend)

    @classmethod
    def match_function(cls, receiver_type: tp.Type, ret_type: tp.Type,
                       param_types: List[tp.Type],
                       target_type: tp.Type,
                       bt_factory: bt.BuiltinFactory,
                       func_metadata: dict = {}):
        is_suspend = target_type.t_constructor.is_suspend
        if func_metadata.get("is_suspend", False) != is_suspend:
            return False, None
        if receiver_type is None:
            # A receiver is not found. Therefore, there is not match.
            return False, None
        import src.ir.type_utils as tu
        api_type = FunctionTypeWithReceiver(
            len(param_types)).new([receiver_type] + param_types + [ret_type])
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
        return etype.type_args[1:-1]

    @classmethod
    def get_ret_type(cls, etype: tp.ParameterizedType):
        return etype.type_args[-1]

Float = FloatType()
