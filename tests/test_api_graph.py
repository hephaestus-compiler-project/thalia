import copy

from src.ir import types as tp
from src.generators import api_graph as ag


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
            "return_type": "java.List"


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
        "type_parameters": ["T extends Number"]
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


def test1():
    b = ag.JavaAPIGraphBuilder("java")
    api_graph = b.build(DOCS1)
    path, assignments = api_graph.find_API_path(
        ag.TypeNode(b.parse_type("java.Set")))
    assert assignments == {}

    assert path == [
        ag.TypeNode(b.parse_type("java.Foo")),
        ag.Method("makeList", "java.Foo", []),
        ag.TypeNode(b.parse_type("java.List")),
        ag.Method("toSet", "java.List", []),
        ag.TypeNode(b.parse_type("java.Set"))
    ]


def test2():
    docs = copy.deepcopy(DOCS1)
    docs["java.Foo"]["type_parameters"] = ["T"]
    b = ag.JavaAPIGraphBuilder("java")
    api_graph = b.build(docs)
    path, assignments = api_graph.find_API_path(
        ag.TypeNode(b.parse_type("java.Set")))
    assert tp.TypeParameter("java.Foo.T0") in assignments

    assert path == [
        b.construct_class_type(docs["java.Foo"]),
        ag.Method("makeList", "java.Foo", []),
        ag.TypeNode(b.parse_type("java.List")),
        ag.Method("toSet", "java.List", []),
        ag.TypeNode(b.parse_type("java.Set"))
    ]
