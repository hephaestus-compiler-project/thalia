from src.generators.api import matcher as mt


def test_patterns():
    assert mt.AnyPattern().match("str")
    assert mt.Prefix("foo").match("foofoo")
    assert mt.Prefix("foo").match("foobar")
    assert not mt.Prefix("foo").match("barfoo")
    assert mt.Regex("^foob[de]r").match("foobdr")
    assert not mt.Regex("^foob[de]r").match("foobqww")
    assert mt.Literal("foo").match("foo")
    assert not mt.Literal("foo").match("fooo")
    assert not mt.And("foo&bar").match("foo")
    assert mt.And("foo&foo").match("foo")
    assert mt.Or("foo|bar").match("bar")
    assert mt.Or("foo|foo").match("foo")
    assert not mt.Or("foo|bar").match("baz")
    assert not mt.Inverse("?^foob[de]r").match("foobdr")
    assert mt.Inverse("?^foob[de]r").match("random")


def test_parse_pattern():
    assert mt.parse_pattern("foo") == mt.Literal("foo")
    assert mt.parse_pattern("=foo") == mt.Literal("foo")
    assert mt.parse_pattern("_foo") == mt.Prefix("foo")
    assert mt.parse_pattern("*") == mt.AnyPattern()
    assert mt.parse_pattern("?regex") == mt.Regex("regex")
    assert mt.parse_pattern("!=foo") == mt.Inverse("=foo")
    assert mt.parse_pattern("&foo&bar") == mt.And("foo&bar")
    assert mt.parse_pattern("|foo|bar") == mt.Or("foo|bar")


def test_matcher():
    spec = {
        "column_names": ["col1", "col2"],
        "rules": [
            ("=foo", "*"),
            ("?^f.*", "!=add"),
            ("_f", "rem")
        ]
    }

    matcher = mt.parse_rule_spec(spec)
    assert matcher.match(matcher.Row("foo", "b"))
    assert matcher.match(matcher.Row("fdb", "rem"))
    assert not matcher.match(matcher.Row("ffd", "add"))
