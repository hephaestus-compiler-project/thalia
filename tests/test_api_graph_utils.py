import networkx as nx

from src.config import cfg
from src.ir import types as tp, kotlin_types as kt
from src.generators.api import utils as au, nodes


def test_compute_assignment_graph():
    # Case 1
    graph = nx.DiGraph()
    node1 = tp.TypeParameter("T1")
    node2 = tp.TypeParameter("T2")
    node3 = tp.TypeParameter("T3")
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    graph.add_edge(node1, node2, constraint={node2: node1})
    graph.add_edge(node2, node3, constraint={node3: node2})

    path = [(node1, node2), (node2, node3)]
    assign_graph = au.compute_assignment_graph(graph, path)
    assert assign_graph[node2] == node1
    assert assign_graph[node3] == node1
    assert len(assign_graph) == 2

    # Case 2
    graph = nx.DiGraph()
    node1 = tp.TypeParameter("T1")
    node2 = tp.TypeParameter("T2")
    node3 = tp.TypeParameter("T3")
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    graph.add_edge(node1, node2, constraint={node2: tp.SimpleClassifier("F")})
    graph.add_edge(node2, node3, constraint={node3: node2})

    assign_graph = au.compute_assignment_graph(graph, path)
    assert assign_graph[node2] == tp.SimpleClassifier("F")
    assert assign_graph[node3] == node2
    assert len(assign_graph) == 2

    # Case 3
    graph = nx.DiGraph()
    node1 = tp.TypeParameter("T1")
    node2 = tp.TypeParameter("T2")
    node3 = tp.TypeParameter("T3")
    type_con = tp.TypeConstructor("F", type_parameters=[tp.TypeParameter("T")])
    t = type_con.new([node2])
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    graph.add_edge(node1, node2, constraint={node2: node1})
    graph.add_edge(node2, node3, constraint={node3: t})
    assign_graph = au.compute_assignment_graph(graph, path)
    assert assign_graph[node2] == node1
    assert assign_graph[node3] == type_con.new([node1])
    assert len(assign_graph) == 2

    # Case 4
    graph = nx.DiGraph()
    node1 = tp.TypeParameter("T1")
    node2 = tp.TypeParameter("T2")
    node3 = tp.TypeParameter("T3")
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    graph.add_edge(node1, node2, constraint={node2: tp.SimpleClassifier("F")})
    graph.add_edge(node2, node3, constraint={node3: tp.SimpleClassifier("F2")})

    assign_graph = au.compute_assignment_graph(graph, path)
    assert assign_graph[node2] == tp.SimpleClassifier("F")
    assert assign_graph[node3] == tp.SimpleClassifier("F2")
    assert len(assign_graph) == 2

    # Case 5
    graph = nx.DiGraph()
    node1 = tp.TypeParameter("T1")
    node2 = tp.TypeParameter("T2")
    node3 = tp.TypeParameter("T3")
    node4 = tp.TypeParameter("T4")
    node5 = tp.TypeParameter("T5")
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    graph.add_node(node4)
    graph.add_node(node5)
    graph.add_edge(node1, node2, constraint={node2: node1})
    graph.add_edge(node2, node3, constraint={node3: kt.String})
    graph.add_edge(node3, node4, constraint={node4: node2})
    graph.add_edge(node4, node5, constraint={node5: node4})

    path = [(node1, node2), (node2, node3), (node3, node4), (node4, node5)]
    assign_graph = au.compute_assignment_graph(graph, path)
    assert assign_graph[node2] == node1
    assert assign_graph[node3] == kt.String
    assert assign_graph[node4] == node1
    assert assign_graph[node5] == node1
    assert len(assign_graph) == 4


def test_collect_constraints():
    # Case 1
    # T1:
    # T2 <- T1
    # T3 <- T2

    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    assignment_graph = {t2: t1, t3: t2}
    target = tp.SimpleClassifier("T")
    assert au.collect_constraints(target, [t1, t2, t3],
                                  assignment_graph) == {
                                      t1: set(),
                                      t2: {au.EqualityConstraint(t1)},
                                      t3: {au.EqualityConstraint(t2)}
                                  }

    # Case 2
    # T1:
    # T2 <: Number
    # T3 <- T2
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2", bound=kt.Number)
    t3 = tp.TypeParameter("T3")
    assignment_graph = {t3: t2}
    target = tp.SimpleClassifier("T")
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: set(),
            t2: {au.UpperBoundConstraint(kt.Number)},
            t3: {au.EqualityConstraint(t2)}}

    # Case 3
    # T1:
    # T2 <: Number
    # T2 <- T1
    # T3 <- T2
    # target = Foo<String>
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2", bound=kt.Number)
    t3 = tp.TypeParameter("T3")
    assignment_graph = {t2: t1, t3: t1}
    target = tp.TypeConstructor("F", [t3]).new([kt.String])
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.String)},
            t2: {au.UpperBoundConstraint(kt.Number), au.EqualityConstraint(t1)},
            t3: {au.EqualityConstraint(t1)}}


    # Case 4
    # T1: String
    # T2: String
    # T3:
    # target = Foo<Integer>
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    assignment_graph = {t1: kt.String, t2: kt.String}
    target = tp.TypeConstructor("F", [t3]).new([kt.Integer])
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.String)},
            t2: {au.EqualityConstraint(kt.String)},
            t3: {au.EqualityConstraint(kt.Integer)}}

    # Case 5
    # T1: String
    # T2: String
    # T3:
    # target = Foo<Integer>
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    assignment_graph = {t1: kt.String, t2: kt.String, t3: kt.String}
    target = tp.TypeConstructor("F", [t3]).new([kt.Integer])
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.String)},
            t2: {au.EqualityConstraint(kt.String)},
            t3: {au.EqualityConstraint(kt.Integer), au.EqualityConstraint(kt.String)}}


    # Case 6
    # T1:
    # T2 <- T1
    # T3: kt.String
    # T4 <- T2
    # T5 <- T4
    t1 = tp.TypeParameter("T1", bound=kt.Number)
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    t4 = tp.TypeParameter("T4")
    t5 = tp.TypeParameter("T5")
    assignment_graph = {t2: t1, t3: kt.String, t4: t1, t5: t1}
    target = tp.TypeConstructor("F", [t5]).new([kt.Integer])
    assert au.collect_constraints(
        target, [t1, t2, t3, t4, t5], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.Integer), au.UpperBoundConstraint(kt.Number)},
            t2: {au.EqualityConstraint(t1)},
            t3: {au.EqualityConstraint(kt.String)},
            t4: {au.EqualityConstraint(t1)},
            t5: {au.EqualityConstraint(t1)},
        }

    # Case 7
    # T1:
    # T1 <- T1
    t1 = tp.TypeParameter("T1", bound=kt.Number)
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    t4 = tp.TypeParameter("T4")
    t5 = tp.TypeParameter("T5")
    assignment_graph = {t2: t1, t3: kt.String, t4: t1, t5: t1}
    target = tp.TypeConstructor("F", [t5]).new([kt.Integer])
    assert au.collect_constraints(
        target, [t1, t2, t3, t4, t5], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.Integer), au.UpperBoundConstraint(kt.Number)},
            t2: {au.EqualityConstraint(t1)},
            t3: {au.EqualityConstraint(kt.String)},
            t4: {au.EqualityConstraint(t1)},
            t5: {au.EqualityConstraint(t1)},
        }



def test_collect_constraints_parameterized():
    # Case 1
    # T1:
    # T2 <- F<T1>
    # T3: kt.String
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2")
    t3 = tp.TypeParameter("T3")
    t4 = tp.TypeParameter("T4")
    t = tp.TypeConstructor("F", [t4]).new([t1])
    assignment_graph = {t2: t, t3: t}
    target = tp.TypeConstructor("T", [t3]).new([kt.String])
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: set(),
            t2: set(),
            t3: {au.EqualityConstraint(kt.String), au.EqualityConstraint(t)}
        }

    # Case 2
    # T1:
    # T2 <- F<T1>
    # T3: F<Integer>
    target = tp.TypeConstructor("T", [t3]).new([
        t.t_constructor.new([kt.Integer])])
    assert au.collect_constraints(
        target, [t1, t2, t3], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.Integer)},
            t2: set(),
            t3: set()
        }


def test_collect_constraints_wildcard():
    # Case 1
    # T1
    # T2 <- T1
    # T2: ?
    t1 = tp.TypeParameter("T1")
    t2 = tp.TypeParameter("T2")
    target = tp.TypeConstructor("T", [t2]).new([tp.WildCardType()])
    assignment_graph = {t2: t1}
    assert au.collect_constraints(
        target, [t1, t2], assignment_graph) == {
            t1: set(),
            t2: {au.EqualityConstraint(t1)},
        }

    # Case 2
    # T1
    # T2 <- T1
    # T2: ? extends Number
    target = tp.TypeConstructor("T", [t2]).new([tp.WildCardType(
        bound=kt.Number, variance=tp.Covariant)])
    assignment_graph = {t2: t1}
    assert au.collect_constraints(
        target, [t1, t2], assignment_graph) == {
            t1: {au.EqualityConstraint(kt.Number)},
            t2: {au.EqualityConstraint(t1)},
        }


def test_is_typing_sequence_ambiguous_simple_classifier():
    t1 = tp.SimpleClassifier("A")
    t2 = tp.SimpleClassifier("B")
    t3 = tp.SimpleClassifier("C", [t1])

    method1 = nodes.Method("m", "", [], [], {})
    method2 = nodes.Method("m", "", [], [], {})
    typing_seq = (0,)
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [nodes.Parameter(t1, False)], [], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(t2, False)], [], {})
    typing_seq = [t1]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [nodes.Parameter(t3, False)], [], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(t1, False)], [], {})
    typing_seq = [t3]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    t3 = tp.SimpleClassifier("C", [t1, t2])
    method1 = nodes.Method("m", "", [nodes.Parameter(t1, False)], [], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(t2, False)], [], {})
    typing_seq = [t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [nodes.Parameter(t1, False),
                                     nodes.Parameter(t2, False)], [], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(t2, False),
                                     nodes.Parameter(t1, False)], [], {})
    typing_seq = [t3, t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})


def test_is_typing_sequence_ambiguous_parameterized():
    cfg.bt_factory = kt.KotlinBuiltinFactory()
    t1 = tp.SimpleClassifier("A")
    t2 = tp.SimpleClassifier("B")
    p1 = tp.TypeParameter("T", bound=t1)
    p2 = tp.TypeParameter("T", bound=t2)

    # <T extends A> m(T)
    # <T extends B> m(T)
    # m(A())
    method1 = nodes.Method("m", "", [nodes.Parameter(p1, False)], [p1], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(p2, False)], [p2], {})
    typing_seq = [t1]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq,
                                          {p1: t1})

    # <T extends A> m(T)
    # <T extends B> m(T)
    # m(C())
    t3 = tp.SimpleClassifier("C", supertypes=[t1, t2])
    typing_seq = [t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {p1: t3})


    # <T> m(List<T>)
    # <T exnteds List<String>> m(T)
    # m(List<String>())
    type_param = tp.TypeParameter("T")
    list_t = tp.TypeConstructor("List", [type_param])
    p1 = list_t.new([type_param])
    p2 = tp.TypeParameter("T", bound=list_t.new([kt.String]))
    method1 = nodes.Method("m", "", [nodes.Parameter(p1, False)], [type_param],
                           {})
    method2 = nodes.Method("m", "", [nodes.Parameter(p2, False)], [p2], {})
    typing_seq = [list_t.new([kt.String])]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq,
                                          {type_param: kt.String})
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, None)


    # <T> m(List<T>)
    # <T> m(T)
    # m(List<String>())
    p1 = list_t.new([type_param])
    p2 = tp.TypeParameter("T")
    method1 = nodes.Method("m", "", [nodes.Parameter(p1, False)], [type_param],
                           {})
    method2 = nodes.Method("m", "", [nodes.Parameter(p2, False)], [p2], {})
    typing_seq = [list_t.new([kt.String])]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq,
                                          {type_param: kt.String})
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq, None)


    # <T> m(T)
    # <T> m(List<T>)
    # m("df")
    typing_seq = [kt.String]
    assert not au.is_typing_seq_ambiguous(method2, method1, typing_seq,
                                          {p2: kt.String})

    # <T> m(T, A)
    # <T> m(T, B)
    # m("fd", C())
    method1 = nodes.Method("m", "", [nodes.Parameter(type_param, False),
                                     nodes.Parameter(t1, False)], [type_param],
                           {})
    method2 = nodes.Method("m", "", [nodes.Parameter(type_param, False),
                                     nodes.Parameter(t2, False)], [type_param],
                           {})
    typing_seq = [kt.String, t3]
    assert au.is_typing_seq_ambiguous(method2, method1, typing_seq,
                                      {type_param: kt.String})

    # <T> m(T, A)
    # <T> m(T, B)
    # m("fd", B())
    typing_seq = [kt.String, t2]
    assert not au.is_typing_seq_ambiguous(method2, method1, typing_seq,
                                          {type_param: kt.String})
    assert not au.is_typing_seq_ambiguous(method2, method1, typing_seq, None)

    # <T extends A> m(T)
    # <T extends C> m(T)
    # m(C())
    type_param1 = tp.TypeParameter("T", bound=t1)
    type_param2 = tp.TypeParameter("T", bound=t3)
    method1 = nodes.Method("m", "", [nodes.Parameter(type_param1, False)],
                           [type_param1], {})
    method2 = nodes.Method("m", "", [nodes.Parameter(type_param2, False)],
                           [type_param2], {})
    typing_seq = [t3]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq,
                                          {type_param1: t1})
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, None)


def test_is_typing_sequence_ambiguous_mul_args():
    t1 = tp.SimpleClassifier("A")
    t2 = tp.SimpleClassifier("B")
    t3 = tp.SimpleClassifier("C", [t1, t2])

    method1 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.String, False),
        nodes.Parameter(t1, False)
    ], [], {})
    method2 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.String, False),
        nodes.Parameter(t2, False)
    ], [], {})
    typing_seq = [kt.Integer, kt.String, t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.Any, False),
        nodes.Parameter(t1, False)
    ], [], {})
    method2 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.String, False),
        nodes.Parameter(t1, False)
    ], [], {})
    typing_seq = [kt.Integer, kt.String, t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.String, False),
        nodes.Parameter(t1, False)
    ], [], {})
    method2 = nodes.Method("m", "", [
        nodes.Parameter(kt.Any, False),
        nodes.Parameter(kt.Any, False),
        nodes.Parameter(t1, False)
    ], [], {})
    typing_seq = [kt.Integer, kt.String, t3]
    assert not au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})

    method1 = nodes.Method("m", "", [
        nodes.Parameter(kt.Integer, False),
        nodes.Parameter(kt.String, False),
        nodes.Parameter(t1, False)
    ], [], {})
    method2 = nodes.Method("m", "", [
        nodes.Parameter(kt.Any, False),
        nodes.Parameter(kt.Any, False),
        nodes.Parameter(t2, False)
    ], [], {})
    typing_seq = [kt.Integer, kt.String, t3]
    assert au.is_typing_seq_ambiguous(method1, method2, typing_seq, {})
