from src.ir import types as tp, java_types as jt
from src.generators.api_graph import JavaAPIGraphBuilder


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
