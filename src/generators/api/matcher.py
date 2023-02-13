from abc import ABC, abstractmethod
from collections import namedtuple
from typing import List, NamedTuple, Tuple, Set, Any
import json
import os
import re


class Pattern(ABC):
    def __init__(self, *args):
        self.args = args

    @abstractmethod
    def match(self, segment: str) -> bool:
        pass


class AnyPattern(Pattern):
    def match(self, segment: str) -> bool:
        return True

    def __repr__(self):
        return "<ANY>"

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__))

    def __eq__(self, other):
        return self.__class__ == other.__class__


class Prefix(Pattern):
    def __init__(self, prefix: str):
        self.prefix = prefix

    def __repr__(self):
        return "Prefix({prefix!r})".format(prefix=self.prefix)

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + self.prefix)

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.prefix == other.prefix
        )

    def match(self, segment: str) -> bool:
        startswith = getattr(segment, 'startswith', None)
        if startswith is not None:
            return startswith(self.prefix)
        elif isinstance(segment, AnyPattern):
            return True
        elif isinstance(segment, Regex):
            m = "Comparison between Prefix and Regex not supported"
            raise NotImplementedError(m)
        else:
            return False

    def startswith(self, prefix):
        return self.prefix.startswith(prefix)


class Regex(Pattern):
    def __init__(self, pattern):
        self.pattern = pattern
        self.matcher = re.compile(pattern)

    def __repr__(self):
        return "Regex({pattern!r})".format(pattern=self.pattern)

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + self.pattern)

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.pattern == other.pattern
        )

    def match(self, segment):
        if isinstance(segment, str):
            return self.matcher.match(segment) is not None
        elif isinstance(segment, AnyPattern):
            return True
        else:
            return False


class Literal(Pattern):
    def __init__(self, segment):
        self.segment = segment

    def __repr__(self):
        return "Literal({literal!r})".format(literal=self.segment)

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + self.segment)

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.segment == other.segment
        )

    def match(self, segment):
        return self.segment == segment


class And(Pattern):
    def __init__(self, pattern):
        self.patterns = [parse_pattern(x) for x in pattern.split('&')]

    def __repr__(self):
        return "And({patterns!r})".format(patterns=",".join(
            str(p) for p in self.patterns))

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + ",".join(
            str(p) for p in self.patterns))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.patterns == other.patterns
        )

    def match(self, segment):
        return all(x.match(segment) for x in self.patterns)


class Or(Pattern):
    def __init__(self, pattern):
        self.patterns = [parse_pattern(x) for x in pattern.split('|')]

    def __repr__(self):
        return "Or({patterns!r})".format(patterns=",".join(
            str(p) for p in self.patterns))

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + ",".join(
            str(p) for p in self.patterns))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.patterns == other.patterns
        )

    def match(self, segment):
        return any(x.match(segment) for x in self.patterns)


class Inverse(Pattern):
    def __init__(self, pattern):
        self.pattern = parse_pattern(pattern)

    def __repr__(self):
        return "Inverse({pattern!r})".format(pattern=self.pattern)

    __str__ = __repr__

    def __hash__(self):
        return hash(str(self.__class__) + str(self.pattern))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.pattern == other.pattern
        )

    def match(self, segment):
        return not self.pattern.match(segment)


_pattern_prefixes = {
    '*': AnyPattern,
    '?': Regex,
    '!': Inverse,
    '_': Prefix,
    '&': And,
    '|': Or,
    '=': Literal,
}


def parse_pattern(string):
    prefix = string[:1]
    if prefix in _pattern_prefixes:
        pattern = string[1:]
    else:
        # Fail back to literal for rule readability.
        pattern = string
        prefix = '='

    return _pattern_prefixes[prefix](pattern)


class Matcher(object):
    def __init__(self, column_names: List[str], rule: Tuple[Pattern]):
        self.column_names = tuple(column_names)
        self.Row = namedtuple("MatcherRow", self.column_names)
        self.rule = self.Row(*rule)

    def match(self, row: Any) -> bool:
        for name in self.column_names:
            tab_val = getattr(self.rule, name)
            row_val = getattr(row, name, None)

            if not tab_val.match(row_val):
                return False

        return True


class AllMatcher(Matcher):
    def __init__(self, matchers: Set[Matcher]):
        self.column_names = list(matchers)[0].column_names
        self.Row = namedtuple("MatcherRow", self.column_names)
        self.matchers = matchers

    def match(self, row: Any) -> bool:
        return all(matcher.match(row) for matcher in self.matchers)


class AnyMatcher(Matcher):
    def __init__(self, matchers: Set[Matcher]):
        self.column_names = list(matchers)[0].column_names
        self.Row = namedtuple("MatcherRow", self.column_names)
        self.matchers = matchers

    def match(self, row: Any) -> bool:
        return any(matcher.match(row) for matcher in self.matchers)


class NotMatcher(Matcher):
    def __init__(self, matcher: Matcher):
        self.column_names = matcher.column_names
        self.Row = namedtuple("MatcherRow", self.column_names)
        self.matcher = matcher

    def match(self, row: Any) -> bool:
        return not self.matcher.match(row)


_aggr_funcs = {
    "any": AnyMatcher,
    "all": AllMatcher,
}


def get_aggr_func(string: str, matchers: Set[Matcher]) -> Matcher:
    if string.startswith("!"):
        return NotMatcher(get_aggr_func(string[1:]))
    if string not in _aggr_funcs.keys():
        msg = "Aggregate function {func!r} is not supported"
        msg = msg.format(func=string)
        raise ValueError(msg)
    return _aggr_funcs[string](matchers)


def parse_rule_spec(spec: dict) -> List[List[Pattern]]:
    column_names = spec.get("column_names")
    if column_names is None:
        msg = "Rules must specify column names"
        raise ValueError(msg)

    rules = spec.get("rules")
    matchers = [
        Matcher(column_names, [
            parse_pattern(pattern)
            for pattern in rule
        ])
        for rule in rules
    ]
    return get_aggr_func(spec.get("func", "any"), matchers)


def parse_rule_file(filepath: str) -> List[List[Pattern]]:
    if not os.path.isfile(filepath):
        msg = "The given filepath {f!r} does not exit"
        msg.format(f=filepath)
        raise IOError(msg)

    with open(filepath, 'r') as f:
        data = json.load(f)
    return parse_rule_spec(data)
