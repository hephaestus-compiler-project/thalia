import copy

from src.ir import types as tp
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


def test1():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS1)
    path, assignments = api_graph.find_API_path(b.parse_type("java.Set"))
    assert assignments == {}

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
    path, assignments = api_graph.find_API_path(b.parse_type("java.Set"))
    assert tp.TypeParameter("java.Foo.T1") in assignments

    assert path == [
        b.construct_class_type(docs["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]

def test3():
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS2)
    path, assignments = api_graph.find_API_path(
        b.construct_class_type(DOCS2["java.Set"]))
    assert tp.TypeParameter("java.Foo.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert tp.TypeParameter("java.Set.T1") in assignments
    assert len(set(assignments.values())) == 1

    assert path == [
        b.construct_class_type(DOCS2["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]

    docs = copy.deepcopy(DOCS2)
    docs["java.Foo"]["methods"][0]["return_type"] = "java.List<java.lang.String>"
    b = JavaAPIGraphBuilder("java")
    api_graph = b.build(docs)
    path, assignments = api_graph.find_API_path(
        b.construct_class_type(DOCS2["java.Set"]))
    assert tp.TypeParameter("java.Foo.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert tp.TypeParameter("java.List.T1") in assignments
    assert assignments[tp.TypeParameter("java.List.T1")] == b.parse_type(
        "java.lang.String")
    assert assignments[tp.TypeParameter("java.Set.T1")] == b.parse_type(
        "java.lang.String")

    assert path == [
        b.construct_class_type(DOCS2["java.Foo"]),
        ag.Method("makeList", "java.Foo", [], []),
        ag.Method("toSet", "java.List", [], []),
    ]


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
            ag.Method("m2", "java.Foo", [b.parse_type("java.lang.String")], []),
            {}
        ),
        (
            ag.Method("m4", "java.List", [b.parse_type("java.lang.String")], []),
            {}
        ),
        (
            ag.Method("apply", "java.Function",
                      [tp.TypeParameter("java.Function.T1")], []),
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
            ag.Method("m3", "java.Foo", [], [tp.TypeParameter("java.Foo.m3.T1")]),
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
