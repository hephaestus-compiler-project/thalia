from src.ir import types as tp, java_types as jt, kotlin_types as kt
from src.generators.api.builder import (JavaAPIGraphBuilder,
                                        KotlinAPIGraphBuilder)


def test_primitives():
    b = JavaAPIGraphBuilder("java")
    assert b.parse_type("char") == jt.CharType(primitive=True)
    assert b.parse_type("byte") == jt.ByteType(primitive=True)
    assert b.parse_type("short") == jt.ShortType(primitive=True)
    assert b.parse_type("int") == jt.IntegerType(primitive=True)
    assert b.parse_type("long") == jt.LongType(primitive=True)
    assert b.parse_type("float") == jt.FloatType(primitive=True)
    assert b.parse_type("double") == jt.DoubleType(primitive=True)
    assert b.parse_type("boolean") == jt.BooleanType(primitive=True)


def test_builtin_types():
    b = JavaAPIGraphBuilder("java")
    assert b.parse_type("java.lang.Character") == jt.CharType(primitive=False)
    assert b.parse_type("java.lang.Byte") == jt.ByteType(primitive=False)
    assert b.parse_type("java.lang.Short") == jt.ShortType(primitive=False)
    assert b.parse_type("java.lang.Integer") == jt.IntegerType(primitive=False)
    assert b.parse_type("java.lang.Long") == jt.LongType(primitive=False)
    assert b.parse_type("java.lang.Float") == jt.FloatType(primitive=False)
    assert b.parse_type("java.lang.Double") == jt.DoubleType(primitive=False)
    assert b.parse_type("java.lang.String") == jt.String
    assert b.parse_type("java.lang.Object") == jt.Object
    assert b.parse_type("void") == jt.Void
    assert b.parse_type("java.lang.String[]") == jt.Array.new([jt.String])
    assert b.parse_type("int[]") == jt.Array.new([jt.IntegerType(primitive=True)])


def test_regular_types():
    b = JavaAPIGraphBuilder("java")
    assert b.parse_type("java.util.Calendar") == tp.SimpleClassifier(
        "java.util.Calendar")
    assert b.parse_type("java.util.List<java.lang.String>") == tp.TypeConstructor(
        "java.util.List", [tp.TypeParameter("java.util.List.T1")]).new([jt.String])
    assert b.parse_type("java.util.Map<java.lang.String,java.util.Calendar>") == \
        tp.TypeConstructor("java.util.Map",
                           [
                               tp.TypeParameter("java.util.Map.T1"),
                               tp.TypeParameter("java.util.Map.T2")
                           ]
        ).new([jt.String, tp.SimpleClassifier("java.util.Calendar")])
    t = b.parse_type("java.util.List<java.util.Map<java.lang.String,java.util.Calendar>>")
    t1 = tp.TypeConstructor("java.util.Map",
                           [
                               tp.TypeParameter("java.util.Map.T1"),
                               tp.TypeParameter("java.util.Map.T2")
                           ]
        ).new([jt.String, tp.SimpleClassifier("java.util.Calendar")])
    t2 = tp.TypeConstructor("java.util.List",
                            [tp.TypeParameter("java.util.List.T1")]).new([t1])
    assert t == t2


def test_type_variables():
    b = JavaAPIGraphBuilder("java")
    assert b.parse_type("T") == tp.TypeParameter("T")
    assert b.parse_type("T extends java.lang.String") == tp.TypeParameter(
        "T", bound=jt.String)
    assert b.parse_type("Foo extends java.util.List<java.lang.String>") == \
        tp.TypeParameter("Foo", bound=tp.TypeConstructor(
            "java.util.List", [tp.TypeParameter("java.util.List.T1")]).new([jt.String]))
    assert b.parse_type("T extends X") == tp.TypeParameter(
        "T", bound=tp.TypeParameter("X"))
    t = b.parse_type("java.BaseStream<T,java.Stream<T>>")
    stream = tp.TypeConstructor(
        "java.Stream", [tp.TypeParameter("java.Stream.T1")]).new(
            [tp.TypeParameter("T")])
    base_stream = tp.TypeConstructor(
        "java.BaseStream",
        [tp.TypeParameter("java.BaseStream.T1"),
         tp.TypeParameter("java.BaseStream.T2")]).new([tp.TypeParameter("T"), stream])
    assert t == base_stream


def test_wildcards():
    b = JavaAPIGraphBuilder("java")
    assert b.parse_type("?") == tp.WildCardType()
    assert b.parse_type("java.List<?>") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType()])
    assert b.parse_type("? extends java.lang.String") == tp.WildCardType(
        bound=jt.String, variance=tp.Covariant
    )
    assert b.parse_type("? super java.lang.String") == tp.WildCardType(
        bound=jt.String, variance=tp.Contravariant
    )


def test_kotlin_primitives():
    b = KotlinAPIGraphBuilder()
    assert b.parse_type("Char") == kt.CharType()
    assert b.parse_type("Byte") == kt.ByteType()
    assert b.parse_type("Short") == kt.ShortType()
    assert b.parse_type("Int") == kt.IntegerType()
    assert b.parse_type("Long") == kt.LongType()
    assert b.parse_type("Float") == kt.FloatType()
    assert b.parse_type("Double") == kt.DoubleType()
    assert b.parse_type("Boolean") == kt.BooleanType()


def test_kotlin_builtin_types():
    b = KotlinAPIGraphBuilder()
    assert b.parse_type("java.lang.Character") == tp.SimpleClassifier("Char?")
    assert b.parse_type("java.lang.Byte") == tp.SimpleClassifier("Byte?")
    assert b.parse_type("java.lang.Short") == tp.SimpleClassifier("Short?")
    assert b.parse_type("java.lang.Integer") == tp.SimpleClassifier("Int?")
    assert b.parse_type("java.lang.Long") == tp.SimpleClassifier("Long?")
    assert b.parse_type("java.lang.Float") == tp.SimpleClassifier("Float?")
    assert b.parse_type("java.lang.Double") == tp.SimpleClassifier("Double?")
    assert b.parse_type("java.lang.String") == kt.String
    assert b.parse_type("java.lang.Object") == kt.Any
    assert b.parse_type("void") == kt.Unit
    assert b.parse_type("java.lang.String[]") == kt.Array.new([kt.String])
    assert b.parse_type("Array<String>") == kt.Array.new([kt.String])
    assert b.parse_type("int[]") == kt.IntegerArray
    assert b.parse_type("CharArray") == kt.CharArray
    assert b.parse_type("ByteArray") == kt.ByteArray
    assert b.parse_type("ShortArray") == kt.ShortArray
    assert b.parse_type("IntArray") == kt.IntegerArray
    assert b.parse_type("LongArray") == kt.LongArray
    assert b.parse_type("FloatArray") == kt.FloatArray
    assert b.parse_type("DoubleArray") == kt.DoubleArray
    assert b.parse_type("Any") == kt.Any
    assert b.parse_type("java.lang.Object") == kt.Any


def test_kotlin_regular_types():
    b = KotlinAPIGraphBuilder()
    assert b.parse_type("Calendar") == tp.SimpleClassifier("Calendar")
    assert b.parse_type("List<String>") == tp.TypeConstructor(
        "List", [tp.TypeParameter("List.T1")]).new([kt.String])
    assert b.parse_type("Map<String,Calendar>") == \
        tp.TypeConstructor("Map",
                           [
                               tp.TypeParameter("Map.T1"),
                               tp.TypeParameter("Map.T2")
                           ]
        ).new([kt.String, tp.SimpleClassifier("Calendar")])
    t = b.parse_type("List<Map<String,Calendar>>")
    t1 = tp.TypeConstructor("Map",
                           [
                               tp.TypeParameter("Map.T1"),
                               tp.TypeParameter("Map.T2")
                           ]
        ).new([kt.String, tp.SimpleClassifier("Calendar")])
    t2 = tp.TypeConstructor("List",
                            [tp.TypeParameter("List.T1")]).new([t1])
    assert t == t2


def test_kotlin_type_variables():
    b = KotlinAPIGraphBuilder()
    b._type_parameters = ["T", "Foo", "X"]
    assert b.parse_type("T") == tp.TypeParameter("T")
    assert b.parse_type("T : java.lang.String") == tp.TypeParameter(
        "T", bound=kt.String)
    assert b.parse_type("Foo : java.util.List<java.lang.String>") == \
        tp.TypeParameter("Foo", bound=tp.TypeConstructor(
            "java.util.List", [tp.TypeParameter("java.util.List.T1")]).new([kt.String]))
    assert b.parse_type("T : X") == tp.TypeParameter(
        "T", bound=tp.TypeParameter("X"))
    t = b.parse_type("java.BaseStream<T,java.Stream<T>>")
    stream = tp.TypeConstructor(
        "java.Stream", [tp.TypeParameter("java.Stream.T1")]).new(
            [tp.TypeParameter("T")])
    base_stream = tp.TypeConstructor(
        "java.BaseStream",
        [tp.TypeParameter("java.BaseStream.T1"),
         tp.TypeParameter("java.BaseStream.T2")]).new([tp.TypeParameter("T"), stream])
    assert t == base_stream

    assert b.parse_type_parameter("out T: String") == tp.TypeParameter(
        "T", variance=tp.Covariant, bound=kt.String)
    assert b.parse_type_parameter("in T : String") == tp.TypeParameter(
        "T", variance=tp.Contravariant, bound=kt.String)
    assert b.parse_type_parameter("out T") == tp.TypeParameter(
        "T", variance=tp.Covariant)
    assert b.parse_type_parameter("in T") == tp.TypeParameter(
        "T", variance=tp.Contravariant)


def test_kotlin_wildcards():
    b = KotlinAPIGraphBuilder()
    assert b.parse_type("*") == tp.WildCardType()
    assert b.parse_type("java.List<*>") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType()])
    assert b.parse_type("out java.lang.String") == tp.WildCardType(
        bound=kt.String, variance=tp.Covariant
    )
    assert b.parse_type("in java.lang.String") == tp.WildCardType(
        bound=kt.String, variance=tp.Contravariant
    )
    assert b.parse_type("java.List<out Int>") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType(
            bound=kt.Integer, variance=tp.Covariant
        )])
    assert b.parse_type("Array<*>?") == kt.NullableType().new(
        [kt.ArrayType().new([tp.WildCardType()])])
