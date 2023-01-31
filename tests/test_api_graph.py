from src.generators import api_graph as ag


def test_subtypes():
    docs = {
        "java.lang.Object": {
            "name": "java.lang.Object",
            "inherits": [],
            "implements": [],
            "fields": [],
            "methods": [],
            "type_parameters": []
        },
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
    b = ag.JavaAPIGraphBuilder("java")
    api_graph = ag.APIGraph(*b.build(docs))
    subtypes = api_graph.subtypes(ag.TypeNode(b.parse_type(
        "java.util.List<java.lang.Object>")))
    subtypes == {
        b.parse_type("java.util.List<java.lang.Object>"),
        b.parse_type("java.util.LinkedList<java.lang.Object>"),
    }

    subtypes = api_graph.subtypes(ag.TypeNode(b.parse_type(
        "java.util.List<java.lang.String>")))
    subtypes == {
        b.parse_type("java.util.List<java.lang.Object>"),
        b.parse_type("java.util.LinkedList<java.lang.Object>"),
        b.parse_type("java.StringList")
    }

    subtypes = api_graph.subtypes(ag.TypeNode(b.parse_type(
        "java.util.List<java.lang.Integer>")))
    subtypes == {
        b.parse_type("java.util.List<java.lang.Object>"),
        b.parse_type("java.util.LinkedList<java.lang.Object>"),
        b.parse_type("java.IntegerList")
    }
