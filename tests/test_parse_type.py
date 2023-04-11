from src.ir import (types as tp, java_types as jt, kotlin_types as kt,
                    scala_types as sc)
from src.generators.api.type_parsers import (JavaTypeParser, KotlinTypeParser,
                                             ScalaTypeParser)


def test_primitives():
    b = JavaTypeParser("java")
    assert b.parse_type("char") == jt.CharType(primitive=True)
    assert b.parse_type("byte") == jt.ByteType(primitive=True)
    assert b.parse_type("short") == jt.ShortType(primitive=True)
    assert b.parse_type("int") == jt.IntegerType(primitive=True)
    assert b.parse_type("long") == jt.LongType(primitive=True)
    assert b.parse_type("float") == jt.FloatType(primitive=True)
    assert b.parse_type("double") == jt.DoubleType(primitive=True)
    assert b.parse_type("boolean") == jt.BooleanType(primitive=True)


def test_builtin_types():
    b = JavaTypeParser("java")
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
    b = JavaTypeParser("java")
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


def test_nested_parameterized_types():
    b = JavaTypeParser("java")
    actual_t = b.parse_type("java.Foo<java.lang.String,java.Map<java.List<java.lang.Integer>,java.lang.Object>>")
    exp_t = tp.TypeConstructor(
        "java.Foo",
        [
            tp.TypeParameter("java.Foo.T1"),
            tp.TypeParameter("java.Foo.T2"),
        ]
    ).new([
        jt.String,
        tp.TypeConstructor(
            "java.Map",
            [tp.TypeParameter("java.Map.T1"),
             tp.TypeParameter("java.Map.T2")]
        ).new([
            tp.TypeConstructor(
                "java.List", [tp.TypeParameter("java.List.T1")]
            ).new([jt.Integer]),
            jt.Object
        ]),
    ])
    assert actual_t == exp_t


def test_type_variables():
    b = JavaTypeParser("java")
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
    b = JavaTypeParser("java")
    assert b.parse_type("?") == tp.WildCardType()
    assert b.parse_type("java.List<?>") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType()])
    assert b.parse_type("? extends java.lang.String") == tp.WildCardType(
        bound=jt.String, variance=tp.Covariant
    )
    assert b.parse_type("? super java.lang.String") == tp.WildCardType(
        bound=jt.String, variance=tp.Contravariant
    )


def test_instance_types():
    classifier = tp.SimpleClassifier("java.Foo")
    type_con = tp.TypeConstructor("java.Foo", [tp.TypeParameter("java.Foo.T1")])
    type_spec = {
        "java.Foo": classifier
    }

    b = JavaTypeParser("java", type_spec=type_spec)
    assert b.parse_type("java.Foo.Bar") == tp.InstanceType(
        "java.Foo.Bar", tp.SimpleClassifier("java.Foo")
    ).new([
        tp.SimpleClassifier("java.Foo")
    ])

    b.type_spec["java.Foo"] = type_con
    enclosing_type = type_con.new([jt.Integer])
    assert b.parse_type("java.Foo<java.lang.Integer>.Bar") == tp.InstanceType(
        "java.Foo.Bar", enclosing_type
    ).new([enclosing_type])

    b.type_spec["java.Foo"] = classifier
    assert b.parse_type("java.Foo.Bar<java.lang.Integer>") == tp.InstanceType(
        "java.Foo.Bar",
        tp.SimpleClassifier("java.Foo"),
        [tp.TypeParameter("java.Foo.Bar.T1")]
    ).new([tp.SimpleClassifier("java.Foo"), jt.Integer])

    b.type_spec["java.Foo"] = type_con
    actual_t = b.parse_type("java.Foo<java.lang.Integer>.Bar<java.lang.String>")
    exp_t = tp.InstanceType(
        "java.Foo.Bar", enclosing_type, [tp.TypeParameter("java.Foo.Bar.T1")]
    ).new([enclosing_type, jt.String])
    assert actual_t == exp_t


def test_kotlin_primitives():
    b = KotlinTypeParser()
    assert b.parse_type("kotlin.Char") == kt.CharType()
    assert b.parse_type("kotlin.Byte") == kt.ByteType()
    assert b.parse_type("kotlin.Short") == kt.ShortType()
    assert b.parse_type("kotlin.Int") == kt.IntegerType()
    assert b.parse_type("kotlin.Long") == kt.LongType()
    assert b.parse_type("kotlin.Float") == kt.FloatType()
    assert b.parse_type("kotlin.Double") == kt.DoubleType()
    assert b.parse_type("kotlin.Boolean") == kt.BooleanType()


def test_kotlin_builtin_types():
    b = KotlinTypeParser()
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
    assert b.parse_type("kotlin.Array<kotlin.String>") == kt.Array.new([kt.String])
    assert b.parse_type("int[]") == kt.IntegerArray
    assert b.parse_type("kotlin.CharArray") == kt.CharArray
    assert b.parse_type("kotlin.ByteArray") == kt.ByteArray
    assert b.parse_type("kotlin.ShortArray") == kt.ShortArray
    assert b.parse_type("kotlin.IntArray") == kt.IntegerArray
    assert b.parse_type("kotlin.LongArray") == kt.LongArray
    assert b.parse_type("kotlin.FloatArray") == kt.FloatArray
    assert b.parse_type("kotlin.DoubleArray") == kt.DoubleArray
    assert b.parse_type("kotlin.Any") == kt.Any
    assert b.parse_type("java.lang.Object") == kt.Any


def test_kotlin_regular_types():
    b = KotlinTypeParser()
    assert b.parse_type("k.Calendar") == tp.SimpleClassifier("k.Calendar")
    assert b.parse_type("k.List<kotlin.String>") == tp.TypeConstructor(
        "k.List", [tp.TypeParameter("k.List.T1")]).new([kt.String])
    assert b.parse_type("k.Map<kotlin.String,k.Calendar>") == \
        tp.TypeConstructor("k.Map",
                           [
                               tp.TypeParameter("k.Map.T1"),
                               tp.TypeParameter("k.Map.T2")
                           ]
        ).new([kt.String, tp.SimpleClassifier("k.Calendar")])
    t = b.parse_type("k.List<k.Map<kotlin.String,k.Calendar>>")
    t1 = tp.TypeConstructor("k.Map",
                           [
                               tp.TypeParameter("k.Map.T1"),
                               tp.TypeParameter("k.Map.T2")
                           ]
        ).new([kt.String, tp.SimpleClassifier("k.Calendar")])
    t2 = tp.TypeConstructor("k.List",
                            [tp.TypeParameter("k.List.T1")]).new([t1])
    assert t == t2


def test_kotlin_type_variables():
    b = KotlinTypeParser()
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

    assert b.parse_type_parameter("out T: kotlin.String") == tp.TypeParameter(
        "T", variance=tp.Covariant, bound=kt.String)
    assert b.parse_type_parameter("in T : kotlin.String") == tp.TypeParameter(
        "T", variance=tp.Contravariant, bound=kt.String)
    assert b.parse_type_parameter("out T") == tp.TypeParameter(
        "T", variance=tp.Covariant)
    assert b.parse_type_parameter("in T") == tp.TypeParameter(
        "T", variance=tp.Contravariant)


def test_kotlin_wildcards():
    b = KotlinTypeParser()
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
    assert b.parse_type("kotlin.Array<*>?") == kt.NullableType().new(
        [kt.ArrayType().new([tp.WildCardType()])])


def test_kotlin_function_types():
    b = KotlinTypeParser()
    assert b.parse_type("(Boolean) -> String") == kt.FunctionType(1).new(
        [kt.Boolean, kt.String])
    assert b.parse_type("(Boolean) -> (String)") == kt.FunctionType(1).new(
        [kt.Boolean, kt.String]
    )
    assert b.parse_type("() -> Unit") == kt.FunctionType(0).new([kt.Unit])
    t = b.parse_type("(Boolean, (Int) -> Boolean, k.List<String>) -> k.Set<String>")
    exp_t = kt.FunctionType(3).new([
        kt.Boolean,
        kt.FunctionType(1).new([kt.Integer, kt.Boolean]),
        tp.TypeConstructor("k.List", [tp.TypeParameter("k.List.T1")]).new([kt.String]),
        tp.TypeConstructor("k.Set", [tp.TypeParameter("k.Set.T1")]).new([kt.String]),
    ])

    assert t == exp_t

    t = b.parse_type("((Boolean) -> String) -> (Int) -> Int")
    exp_t = kt.FunctionType(1).new([
        kt.FunctionType(1).new([kt.Boolean, kt.String]),
        kt.FunctionType(1).new([kt.Integer, kt.Integer])
    ])
    assert t == exp_t

    t = b.parse_type("(k.Map<String, Int>) -> Unit")
    exp_t = kt.FunctionType(1).new([
        tp.TypeConstructor("k.Map", [
            tp.TypeParameter("k.Map.T1"),
            tp.TypeParameter("k.Map.T2")
        ]).new([kt.String, kt.Integer]),
        kt.Unit
    ])
    assert t == exp_t

    assert b.parse_type("(a: String, b: Int) -> Int") == kt.FunctionType(2).new(
        [kt.String, kt.Integer, kt.Integer])

    t = b.parse_type("(kotlin.collections.Map.Entry<K, V>) -> R?")
    exp_t = kt.FunctionType(1).new([
        tp.TypeConstructor(
            "kotlin.collections.Map.Entry",
            [
                tp.TypeParameter("kotlin.collections.Map.Entry.T1"),
                tp.TypeParameter("kotlin.collections.Map.Entry.T2"),
            ]
        ).new([
            tp.TypeParameter("K"),
            tp.TypeParameter("V")
        ]),
        kt.NullableType().new([tp.TypeParameter("R")])
    ])
    assert t == exp_t

    b.parse_type("kotlin.Function1[String, Int]") == kt.FunctionType(1).new([
        kt.String, kt.Integer
    ])
    b.parse_type("kotlin.Function0[Int]") == kt.FunctionType(0).new([kt.Integer])


def test_scala_primitives():
    b = ScalaTypeParser()
    assert b.parse_type("scala.Char") == sc.CharType()
    assert b.parse_type("scala.Byte") == sc.ByteType()
    assert b.parse_type("scala.Short") == sc.ShortType()
    assert b.parse_type("scala.Int") == sc.IntegerType()
    assert b.parse_type("scala.Long") == sc.LongType()
    assert b.parse_type("scala.Float") == sc.FloatType()
    assert b.parse_type("scala.Double") == sc.DoubleType()
    assert b.parse_type("scala.Boolean") == sc.BooleanType()


def test_scala_builtin_types():
    b = ScalaTypeParser()
    assert b.parse_type("void") == sc.Unit
    assert b.parse_type("Void") == sc.Unit
    assert b.parse_type("scala.Unit") == sc.Unit
    assert b.parse_type("Unit") == sc.Unit
    assert b.parse_type("scala.Any") == sc.Any
    assert b.parse_type("scala.String") == sc.String
    assert b.parse_type("scala.Array[scala.String]") == sc.Array.new(
        [sc.String])
    assert b.parse_type("scala.Seq[scala.String]") == sc.Seq.new(
        [sc.String])


def test_scala_regular_types():
    b = ScalaTypeParser()
    assert b.parse_type("k.Calendar") == tp.SimpleClassifier("k.Calendar")
    assert b.parse_type("k.List[scala.String]") == tp.TypeConstructor(
        "k.List", [tp.TypeParameter("k.List.T1")]).new([sc.String])
    assert b.parse_type("k.Map[scala.String,k.Calendar]") == \
        tp.TypeConstructor("k.Map",
                           [
                               tp.TypeParameter("k.Map.T1"),
                               tp.TypeParameter("k.Map.T2")
                           ]
        ).new([sc.String, tp.SimpleClassifier("k.Calendar")])
    t = b.parse_type("k.List[k.Map[scala.String,k.Calendar]]")
    t1 = tp.TypeConstructor("k.Map",
                           [
                               tp.TypeParameter("k.Map.T1"),
                               tp.TypeParameter("k.Map.T2")
                           ]
        ).new([sc.String, tp.SimpleClassifier("k.Calendar")])
    t2 = tp.TypeConstructor("k.List",
                            [tp.TypeParameter("k.List.T1")]).new([t1])
    assert t == t2

    b.parse_type("=> String") == sc.String


def test_scala_type_variables():
    b = ScalaTypeParser()
    assert b.parse_type("T") == tp.TypeParameter("T")
    assert b.parse_type("T <: scala.String") == tp.TypeParameter(
        "T", bound=sc.String)
    assert b.parse_type("Foo <: java.util.List[scala.String]") == \
        tp.TypeParameter("Foo", bound=tp.TypeConstructor(
            "java.util.List", [tp.TypeParameter("java.util.List.T1")]).new([sc.String]))
    assert b.parse_type("T <: X") == tp.TypeParameter(
        "T", bound=tp.TypeParameter("X"))
    t = b.parse_type("java.BaseStream[T,java.Stream[T]]")
    stream = tp.TypeConstructor(
        "java.Stream", [tp.TypeParameter("java.Stream.T1")]).new(
            [tp.TypeParameter("T")])
    base_stream = tp.TypeConstructor(
        "java.BaseStream",
        [tp.TypeParameter("java.BaseStream.T1"),
         tp.TypeParameter("java.BaseStream.T2")]).new([tp.TypeParameter("T"), stream])
    assert t == base_stream

    assert b.parse_type("+T <: scala.String") == tp.TypeParameter(
        "T", variance=tp.Covariant, bound=sc.String)
    assert b.parse_type("-T <: scala.String") == tp.TypeParameter(
        "T", variance=tp.Contravariant, bound=sc.String)
    assert b.parse_type("+T") == tp.TypeParameter(
        "T", variance=tp.Covariant)
    assert b.parse_type("-T") == tp.TypeParameter("T", variance=tp.Contravariant)
    assert b.parse_type(
        "+CC[X] <: scala.SortedSet[X] with scala.SortedSetOps[X, CC, CC[X]]") is None
    assert b.parse_type("+CC[X] <: scala.SortedSet[X]") is None
    assert b.parse_type("+CC[_] <: scala.SortedSet") is None
    assert b.parse_type("X >: Y") is None


def test_scala_wildcards():
    b = ScalaTypeParser()
    assert b.parse_type("?") == tp.WildCardType()
    assert b.parse_type("_") == tp.WildCardType()
    assert b.parse_type("java.List[?]") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType()])
    assert b.parse_type("? <: scala.String") == tp.WildCardType(
        bound=sc.String, variance=tp.Covariant
    )
    assert b.parse_type("? >: scala.String") == tp.WildCardType(
        bound=sc.String, variance=tp.Contravariant
    )
    assert b.parse_type("java.List[? <: Int]") == tp.TypeConstructor(
        "java.List", [tp.TypeParameter("java.List.T1")]).new([tp.WildCardType(
            bound=sc.Integer, variance=tp.Covariant
        )])
    assert b.parse_type("scala.Array[_]") == sc.ArrayType().new([tp.WildCardType()])


def test_scala_function_types():
     b = ScalaTypeParser()
     assert b.parse_type("(Boolean) => String") == sc.FunctionType(1).new(
         [sc.Boolean, sc.String])
     assert b.parse_type("(Boolean) => (String)") == sc.FunctionType(1).new(
         [sc.Boolean, sc.String]
     )
     assert b.parse_type("() => Unit") == sc.FunctionType(0).new([sc.Unit])
     t = b.parse_type("(Boolean, (Int) => Boolean, k.List[String]) => k.Set[String]")
     exp_t = sc.FunctionType(3).new([
         sc.Boolean,
         sc.FunctionType(1).new([sc.Integer, sc.Boolean]),
         tp.TypeConstructor("k.List", [tp.TypeParameter("k.List.T1")]).new([sc.String]),
         tp.TypeConstructor("k.Set", [tp.TypeParameter("k.Set.T1")]).new([sc.String]),
     ])

     assert t == exp_t

     t = b.parse_type("((Boolean) => String) => (Int) => Int")
     exp_t = sc.FunctionType(1).new([
         sc.FunctionType(1).new([sc.Boolean, sc.String]),
         sc.FunctionType(1).new([sc.Integer, sc.Integer])
     ])
     assert t == exp_t

     t = b.parse_type("(Boolean) => (String) => (Int)")
     exp_t = sc.FunctionType(1).new([
         sc.Boolean,
         sc.FunctionType(1).new([sc.String, sc.Integer])
     ])

     t = b.parse_type("(Boolean) => (String) => (Int) => Char")
     exp_t = sc.FunctionType(1).new([
         sc.Boolean,
         sc.FunctionType(1).new([
             sc.String,
             sc.FunctionType(1).new([sc.Integer, sc.Char])
         ])
     ])

     t = b.parse_type("(k.Map[String, Int]) => Unit")
     exp_t = sc.FunctionType(1).new([
         tp.TypeConstructor("k.Map", [
             tp.TypeParameter("k.Map.T1"),
             tp.TypeParameter("k.Map.T2")
         ]).new([sc.String, sc.Integer]),
         sc.Unit
     ])
     assert t == exp_t

     t = b.parse_type("(((String, Int))) => Boolean")
     exp_t = sc.FunctionType(2).new([
         sc.String,
         sc.Integer,
         sc.Boolean
     ])

     assert b.parse_type("scala.Function1[String, Int]") == sc.FunctionType(1).new([
         sc.String, sc.Integer
     ])
     assert b.parse_type("scala.Function0[Int]") == sc.FunctionType(0).new([sc.Integer])
     assert b.parse_type("(=> scala.String) => scala.Int") == sc.FunctionType(1).new([
         sc.String,
         sc.Integer
     ])

     t = b.parse_type("((scala.String) => scala.Int) => scala.Boolean")
     exp_t = sc.FunctionType(1).new([
         sc.FunctionType(1).new([
             sc.String,
             sc.Integer
         ]),
         sc.Boolean
     ])
     assert t == exp_t


def test_scala_tuple_types():
     b = ScalaTypeParser()
     assert b.parse_type("(String, Int)") == sc.TupleType(2).new([sc.String, sc.Integer])
     assert b.parse_type("k.Map[String,(String,Int)]") == tp.TypeConstructor(
         "k.Map", [tp.TypeParameter("k.Map.T1"), tp.TypeParameter("k.Map.T2")]).new([
             sc.String,
             sc.TupleType(2).new([sc.String, sc.Integer])
     ])
