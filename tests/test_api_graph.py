import copy

from src.ir import types as tp, java_types as jt
from src.generators.api import api_graph as ag
from src.generators.api.builder import JavaAPIGraphBuilder


DOCS1 = {
    "java.Foo": {
        "name": "java.Foo",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "makeList",
            "is_static": False,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.List"


        }],
        "type_parameters": []
    },
    "java.List": {
        "name": "java.List",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "toSet",
            "is_static": False,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.Set"


        }],
        "type_parameters": []
    },
    "java.Set": {
        "name": "java.Set",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "add",
            "is_static": False,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "void"


        }],
        "type_parameters": []
    },
}


DOCS2 = {
    "java.Foo": {
        "name": "java.Foo",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "makeList",
            "is_static": False,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.List<T>"
        }],
        "type_parameters": ["T"]
    },
    "java.List": {
        "name": "java.List",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "toSet",
            "is_static": False,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.Set<T>"
        }],
        "type_parameters": ["T"]
    },
    "java.Set": {
        "name": "java.Set",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "add",
            "is_static": False,
            "is_constructor": False,
            "parameters": ["T"],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "void"


        }],
        "type_parameters": ["T"]
    },
}

DOCS3 = {
    "java.Foo": {
        "name": "java.Foo",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [
            {
                "name": "m1",
                "is_static": False,
                "is_constructor": False,
                "parameters": [],
                "access_mod": "public",
                "type_parameters": [],
                "return_type": "java.lang.Object"
            },
            {
                "name": "m2",
                "is_static": False,
                "is_constructor": False,
                "parameters": ["java.lang.String"],
                "access_mod": "public",
                "type_parameters": [],
                "return_type": "java.lang.Object"
            },
            {
                "name": "m3",
                "is_static": False,
                "is_constructor": False,
                "parameters": [],
                "access_mod": "public",
                "type_parameters": ["T"],
                "return_type": "java.List<T>"
            },
            {
                "name": "Foo",
                "is_static": False,
                "is_constructor": True,
                "parameters": [],
                "access_mod": "public",
                "type_parameters": [],
                "return_type": None
            },
        ],
        "type_parameters": ["T"]
    },
    "java.List": {
        "name": "java.List",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "m4",
            "is_static": False,
            "is_constructor": False,
            "parameters": ["java.lang.String"],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.lang.Object"
        }],
        "type_parameters": ["T"]
    },
    "java.Function": {
        "name": "java.Function",
        "type_parameters": [
          "T",
          "R"
        ],
        "functional_interface": True,
        "implements": [],
        "inherits": [],
        "class_type": 1,
        "fields": [],
        "methods": [
          {
            "name": "apply",
            "parameters": [
              "T"
            ],
            "type_parameters": [],
            "return_type": "R",
            "is_static": False,
            "is_constructor": False,
            "access_mod": "public",
            "throws": [],
            "is_default": False
          },
        ]
    },
    "java.Producer": {
        "name": "java.Producer",
        "type_parameters": ["T"],
        "functional_interface": True,
        "implements": [],
        "inherits": [],
        "class_type": 1,
        "fields": [],
        "methods": [
          {
            "name": "apply",
            "parameters": [],
            "type_parameters": [],
            "return_type": "T",
            "is_static": False,
            "is_constructor": False,
            "access_mod": "public",
            "throws": [],
            "is_default": False
          },
        ]
    },
}


DOCS4 = {
    "java.Producer": {
        "name": "java.Producer",
        "type_parameters": ["T"],
        "functional_interface": True,
        "implements": [],
        "inherits": [],
        "class_type": 1,
        "fields": [],
        "methods": [
          {
            "name": "apply",
            "parameters": [],
            "type_parameters": [],
            "return_type": "T",
            "is_static": False,
            "is_constructor": False,
            "access_mod": "public",
            "throws": [],
            "is_default": False
          },
        ]
    },
    "java.Foo": {
        "name": "java.Foo",
        "type_parameters": [],
        "functional_interface": False,
        "implements": ["java.Producer<java.lang.String>"],
        "inherits": [],
        "class_type": 9,
        "fields": [],
        "methods": []
    }
}


DOCS5 = {
    "java.Foo": {
        "name": "java.Foo",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "makeList",
            "is_static": True,
            "is_constructor": False,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": "java.Foo<java.lang.String>"


        }],
        "type_parameters": ["T"]
    },
    "java.Foo.List": {
        "name": "java.Foo.List",
        "inherits": [],
        "implements": [],
        "fields": [],
        "methods": [{
            "name": "List",
            "is_static": False,
            "is_constructor": True,
            "parameters": [],
            "access_mod": "public",
            "type_parameters": [],
            "return_type": None


        }],
        "parent": "java.Foo",
        "type_parameters": []
    },
}


def filter_types(path):
    return [
        p
        for i, p in enumerate(path)
        if i == 0 or not isinstance(p, tp.Type)
    ]


def test1():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS1)
    path, assignments, _ = api_graph.find_API_path(b.parse_type("java.Set"))
    assert assignments == {}

    path = filter_types(path)

    assert path == [
        b.parse_type("java.Foo"),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]


def test2():
    docs = copy.deepcopy(DOCS1)
    docs["java.Foo"]["type_parameters"] = ["T"]
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(docs)
    path, assignments, _ = api_graph.find_API_path(b.parse_type("java.Set"))
    assert tp.TypeParameter("java.Foo.T1") in assignments

    path = filter_types(path)

    assert path == [
        b.build_class_node(docs["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]

def test3():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS2)
    path, assignments, _ = api_graph.find_API_path(
        b.build_class_node(DOCS2["java.Set"]))
    assert tp.TypeParameter("java.Foo.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert tp.TypeParameter("java.Set.T1") in assignments
    assert len(set(assignments.values())) == 1

    path = filter_types(path)

    assert path == [
        b.build_class_node(DOCS2["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]

    docs = copy.deepcopy(DOCS2)
    docs["java.Foo"]["methods"][0]["return_type"] = "java.List<java.lang.String>"
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(docs)
    path, assignments, _ = api_graph.find_API_path(
        b.build_class_node(DOCS2["java.Set"]))
    assert tp.TypeParameter("java.Foo.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert assignments[tp.TypeParameter("java.List.T1")] == b.parse_type(
        "java.lang.String")
    assert assignments[tp.TypeParameter("java.Set.T1")] == b.parse_type(
        "java.lang.String")

    path = filter_types(path)

    assert path == [
        b.build_class_node(DOCS2["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]


def test4():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS5)
    assert api_graph.find_API_path(
        b.build_class_node(DOCS5["java.Foo.List"]),
        with_constraints={tp.TypeParameter("java.Foo.T1"): jt.Integer}) is None

    path, assignments, _ = api_graph.find_API_path(
        b.build_class_node(DOCS5["java.Foo.List"]),
        with_constraints={tp.TypeParameter("java.Foo.T1"): jt.String})
    path = filter_types(path)
    assert path == [
        ag.Method("java.Foo.makeList", "java.Foo", [], []),
        ag.Constructor("java.Foo.List", [])
    ]
    assert assignments == {
        tp.TypeParameter("java.Foo.T1"): jt.String
    }

    docs = copy.deepcopy(DOCS5)
    docs["java.Foo"]["methods"].append({
        "name": "java.Foo",
        "is_static": False,
        "is_constructor": True,
        "parameters": [],
        "access_mod": "public",
        "type_parameters": [],
        "return_type": None
    })
    api_graph = b.build(docs)
    path, assignments, _ = api_graph.find_API_path(
        b.build_class_node(docs["java.Foo.List"]),
        with_constraints={tp.TypeParameter("java.Foo.T1"): jt.Integer})
    path = filter_types(path)
    assert path == [
        ag.Constructor("java.Foo", []),
        ag.Constructor("java.Foo.List", [])
    ]
    assert assignments == {
        tp.TypeParameter("java.Foo.T1"): jt.Integer
    }


def test_get_function_refs_of():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS3)

    refs = api_graph.get_function_refs_of(
        b.parse_type("java.Producer<java.lang.Object>"))
    assert refs == [
        (
            ag.Method("m1", "java.Foo", [], []),
            {}
        ),
        (
            ag.Method("apply", "java.Producer", [], []),
            {
                tp.TypeParameter("java.Producer.T1"): b.parse_type(
                    "java.lang.Object")
            }
        )
    ]

    refs = api_graph.get_function_refs_of(
        b.parse_type("java.Function<java.lang.String,java.lang.Object>"),
    )
    assert refs == [
        (
            ag.Method("m2", "java.Foo", [
                ag.Parameter(b.parse_type("java.lang.String"), False)], []),
            {}
        ),
        (
            ag.Method("m4", "java.List", [
                ag.Parameter(b.parse_type("java.lang.String"), False)], []),
            {}
        ),
        (
            ag.Method("apply", "java.Function",
                      [ag.Parameter(tp.TypeParameter("java.Function.T1"), False)], []),
            {
                tp.TypeParameter("java.Function.T1"): b.parse_type("java.lang.String"),
                tp.TypeParameter("java.Function.T2"): b.parse_type("java.lang.Object"),
            }
        )

    ]

    refs = api_graph.get_function_refs_of(
        b.parse_type("java.Producer<java.List<java.lang.Integer>>")
    )
    assert refs == [
        (
            ag.Method("m3", "java.Foo", [],
                      [tp.TypeParameter("java.Foo.m3.T1")]),
            {
                tp.TypeParameter("java.Foo.m3.T1"): b.parse_type("java.lang.Integer")
            }
        ),
        (
            ag.Method("apply", "java.Producer", [], []),
            {
                tp.TypeParameter("java.Producer.T1"): b.parse_type(
                    "java.List<java.lang.Integer>")
            }
        )
    ]


    refs = api_graph.get_function_refs_of(
        b.parse_type("java.Producer<java.Foo<java.lang.Integer>>")
    )
    assert refs == [
        (
            ag.Constructor("java.Foo", []),
            {
                tp.TypeParameter("java.Foo.T1"): b.parse_type("java.lang.Integer")
            }
        ),
        (
            ag.Method("apply", "java.Producer", [], []),
            {
                tp.TypeParameter("java.Producer.T1"): b.parse_type(
                    "java.Foo<java.lang.Integer>")
            }
        )
    ]

    refs = api_graph.get_function_refs_of(b.parse_type("java.lang.Object"))
    assert refs == []


def test_get_functional_type():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS4)

    assert api_graph.get_functional_type(b.parse_type("java.lang.String")) is None
    assert api_graph.get_functional_type(b.parse_type(
        "java.Producer<java.lang.Integer>")) == jt.FunctionType(0).new([tp.TypeParameter("java.Producer.T1")])
    assert api_graph.get_functional_type(
        b.parse_type("java.Foo")) == jt.FunctionType(0).new([jt.String])
