from src.generators.api import api_graph as ag
from src.generators.api.builder import JavaAPIGraphBuilder


DOCS1 = {
    "java.StringList": {
        "name": "java.StringList",
        "inherits": ["java.util.LinkedList<java.lang.String>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.IntegerList": {
        "name": "java.IntegerList",
        "inherits": ["java.util.LinkedList<java.lang.Integer>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.util.List": {
        "name": "java.util.List",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    },
    "java.util.LinkedList": {
        "name": "java.util.LinkedList",
        "inherits": ["java.util.List<T>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    }
}


DOCS2 = {
   "java.Number": {
        "name": "java.Number",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.Integer": {
        "name": "java.Integer",
        "inherits": ["java.Number"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.Long": {
        "name": "java.Long",
        "inherits": ["java.Number"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.String": {
        "name": "java.String",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
}


DOCS3 = {
    "java.Map": {
        "name": "java.Map",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["K", "V"]
    },
    "java.HashMap": {
        "name": "java.HashMap",
        "inherits": ["java.Map<K,V>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["K", "V"]
    },
    "java.Foo": {
        "name": "java.Foo",
        "inherits": ["java.HashMap<java.lang.String,T>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    },
    "java.Bar": {
        "name": "java.Bar",
        "inherits": ["java.Foo<java.Map<java.lang.String,java.lang.Integer>>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    }
}


DOCS4 = {
    "java.Map": {
        "name": "java.Map",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["K", "V"]
    },
    "java.Stream": {
        "name": "java.Stream",
        "inherits": ["java.Map<T,java.Map<T,java.lang.String>>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    },
    "java.Foo": {
        "name": "java.Foo",
        "inherits": ["java.Stream<java.lang.Object>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
}


DOCS5 = {
    "java.util.Spliterator.OfInt": {
        "name": "java.util.Spliterator.OfInt",
        "type_parameters": [],
        "implements": [],
        "inherits": [
          "java.util.Spliterator.OfPrimitive<java.lang.Integer,java.lang.Integer,java.util.Spliterator.OfInt>"
        ],
        "methods": [],
        "fields": []

    },
    "java.util.Spliterator.OfPrimitive": {
        "name": "java.util.Spliterator.OfPrimitive",
        "type_parameters": [
          "T",
          "T_CONS",
          "T_SPLITR extends Spliterator.OfPrimitive<T,T_CONS,T_SPLITR>"
        ],
        "implements": [],
        "inherits": [
            "java.lang.Object"
        ],
        "methods": [],
        "fields": []
    }
}


DOCS6 = {
    "java.Comparable": {
        "name": "java.Comparable",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    },
    "java.String": {
        "name": "java.String",
        "inherits": ["java.Comparable<java.String>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": []
    },
    "java.Foo": {
        "name": "java.Foo",
        "inherits": ["java.Comparable<java.Foo<T>>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    },
    "java.BaseStream": {
        "name": "java.BaseStream",
        "inherits": ["java.lang.Object"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T", "S"]
    },
    "java.Stream": {
        "name": "java.Stream",
        "inherits": ["java.BaseStream<T,java.Stream<T>>"],
        "implements": [],
        "fields": [],
        "methods": [],
        "type_parameters": ["T"]
    }

}


def test_subtypes1():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS1)

    # Case 1
    subtypes = api_graph.subtypes(b.parse_type(
        "java.util.List<java.lang.Object>"))
    assert subtypes == {
        b.parse_type("java.util.List<java.lang.Object>"),
        b.parse_type("java.util.LinkedList<java.lang.Object>"),
    }

    # Case 2
    subtypes = api_graph.subtypes(b.parse_type(
        "java.util.List<java.lang.String>"))
    assert subtypes == {
        b.parse_type("java.util.List<java.lang.String>"),
        b.parse_type("java.util.LinkedList<java.lang.String>"),
        b.parse_type("java.StringList")
    }

    # Case 3
    subtypes = api_graph.subtypes(b.parse_type(
        "java.util.List<java.lang.Integer>"))
    assert subtypes == {
        b.parse_type("java.util.List<java.lang.Integer>"),
        b.parse_type("java.util.LinkedList<java.lang.Integer>"),
        b.parse_type("java.IntegerList")
    }

    # Case 4
    subtypes = api_graph.subtypes(b.parse_type("java.util.List<T>"))
    assert subtypes == {
        b.parse_type("java.util.List<T>"),
        b.parse_type("java.util.LinkedList<T>"),
    }

    subtypes = api_graph.subtypes(b.parse_type(
        "java.util.List<? extends java.lang.String>"))
    assert subtypes == {
        b.parse_type("java.util.List<? extends java.lang.String>"),
        b.parse_type("java.util.List<java.lang.String>"),
        b.parse_type("java.util.LinkedList<java.lang.String>"),
        b.parse_type("java.StringList")
    }


def test_subtypes2():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS2)

    # Case 1
    subtypes = api_graph.subtypes(b.parse_type("java.lang.Object"))
    assert subtypes == {
        b.parse_type("java.lang.Object"),
        b.parse_type("java.Number"),
        b.parse_type("java.Integer"),
        b.parse_type("java.Long"),
        b.parse_type("java.String"),
    }

    # Case 2
    subtypes = api_graph.subtypes(b.parse_type("java.Number"))
    assert subtypes == {
        b.parse_type("java.Number"),
        b.parse_type("java.Integer"),
        b.parse_type("java.Long"),
    }

    # Case 3
    subtypes = api_graph.subtypes(b.parse_type("java.String"))
    assert subtypes == { b.parse_type("java.String") }


def test_subtypes3():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS3)
    subtypes = api_graph.subtypes(b.parse_type(
        "java.Map<T1,java.lang.String>"))
    assert subtypes == {
        b.parse_type("java.Map<T1,java.lang.String>"),
        b.parse_type("java.HashMap<T1,java.lang.String>"),
    }

    subtypes = api_graph.subtypes(b.parse_type(
        "java.HashMap<java.lang.String,java.lang.Integer>"))
    assert subtypes == {
        b.parse_type("java.HashMap<java.lang.String,java.lang.Integer>"),
        b.parse_type("java.Foo<java.lang.Integer>"),
    }

    subtypes = api_graph.subtypes(b.parse_type(
        "java.Map<java.lang.String,java.Map<java.lang.String,java.lang.Integer>>"))
    assert subtypes == {
        b.parse_type("java.Map<java.lang.String,java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.HashMap<java.lang.String,java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.Foo<java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.Bar"),
    }


def test_subtypes4():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS4)
    subtypes = api_graph.subtypes(b.parse_type(
        "java.Map<T1,java.lang.String>"))
    assert subtypes == {
        b.parse_type("java.Map<T1,java.lang.String>"),
    }

    subtypes = api_graph.subtypes(b.parse_type(
        "java.Map<F,java.Map<F,java.lang.Integer>>"))
    assert subtypes == {
        b.parse_type("java.Map<F,java.Map<F,java.lang.Integer>>"),
    }

    subtypes = api_graph.subtypes(b.parse_type(
        "java.Map<F,java.Map<F,java.lang.String>>"))
    assert subtypes == {
        b.parse_type("java.Map<F,java.Map<F,java.lang.String>>"),
        b.parse_type("java.Stream<F>"),
    }


def test_supertypes1():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS1)

    supertypes = api_graph.supertypes(b.parse_type("java.lang.Object"))
    assert supertypes == set()

    supertypes = api_graph.supertypes(b.parse_type("java.StringList"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
        b.parse_type("java.util.List<java.lang.String>"),
        b.parse_type("java.util.LinkedList<java.lang.String>"),
    }

    supertypes = api_graph.supertypes(b.parse_type(
        "java.util.LinkedList<java.lang.Object>"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
        b.parse_type("java.util.List<java.lang.Object>"),
    }

    supertypes = api_graph.supertypes(b.parse_type(
        "java.util.List<java.lang.Object>"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
    }


def test_supertypes2():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS2)

    supertypes = api_graph.supertypes(b.parse_type("java.String"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
    }

    supertypes = api_graph.supertypes(b.parse_type("java.Long"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
        b.parse_type("java.Number"),
    }


def test_supertypes3():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS3)

    supertypes = api_graph.supertypes(b.parse_type(
        "java.Foo<java.lang.Integer>"))
    assert supertypes == {
        b.parse_type("java.HashMap<java.lang.String,java.lang.Integer>"),
        b.parse_type("java.Map<java.lang.String,java.lang.Integer>"),
        b.parse_type("java.lang.Object"),
    }

    supertypes = api_graph.supertypes(b.parse_type(
        "java.Bar"))
    assert supertypes == {
        b.parse_type("java.Foo<java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.HashMap<java.lang.String,java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.Map<java.lang.String,java.Map<java.lang.String,java.lang.Integer>>"),
        b.parse_type("java.lang.Object"),
    }


def test_supertypes4():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS4)

    supertypes = api_graph.supertypes(b.parse_type("java.Stream<K>"))
    assert supertypes == {
        b.parse_type("java.Map<K,java.Map<K,java.lang.String>>"),
        b.parse_type("java.lang.Object"),
    }

    supertypes = api_graph.supertypes(b.parse_type(
        "java.Foo"))
    assert supertypes == {
        b.parse_type("java.Stream<java.lang.Object>"),
        b.parse_type("java.Map<java.lang.Object,java.Map<java.lang.Object,java.lang.String>>"),
        b.parse_type("java.lang.Object"),
    }


def test_supertypes5():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS5)

    supertypes = api_graph.supertypes(b.parse_type(
        "java.util.Spliterator.OfInt"))
    assert supertypes == {
        b.parse_type("java.lang.Object"),
        b.parse_type(
            "java.util.Spliterator.OfPrimitive<java.lang.Integer,java.lang.Integer,java.util.Spliterator.OfInt>")
    }


def test_get_instantiations_of_recursive_bound():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS6)

    # Case 1
    types = api_graph.get_instantiations_of_recursive_bound(b.parse_type(
        "java.Comparable<T>"))
    assert types == {b.parse_type("java.String"),
                     b.construct_class_type(DOCS6["java.Foo"])}

    # Case 2
    types = api_graph.get_instantiations_of_recursive_bound(b.parse_type(
        "java.Comparable<java.lang.Integer>"))
    assert types == set()

    # Case 3
    types = api_graph.get_instantiations_of_recursive_bound(b.parse_type(
        "java.Comparable<java.String>"))
    assert types == set()

    # Case 4
    types = api_graph.get_instantiations_of_recursive_bound(b.parse_type(
        "java.Comparable<java.String>"))
    assert types == set()

    # Case 5 / BaseStream
    b._class_name = "java.BaseStream"
    types = api_graph.get_instantiations_of_recursive_bound(b.parse_type(
        "java.BaseStream<T,S>"))
    assert types == set()
