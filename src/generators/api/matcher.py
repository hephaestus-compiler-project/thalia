from abc import ABC, abstractmethod
from collections import namedtuple
from typing import List
import json
import os
import re


class Pattern(ABC):
    def __init__(self, *args):
        self.args = args

    @abstractmethod
    def match(self, segment):
        pass


class AnyPattern(Pattern):
    def match(self, segment):
        return True

    def __repr__(self):
        return "<ANY>"

    __str__ = __repr__


class Prefix(Pattern):
    def __init__(self, prefix):
        self.prefix = prefix

    def __repr__(self):
        return "Prefix({prefix!r})".format(prefix=self.prefix)

    __str__ = __repr__

    def match(self, segment):
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

    def match(self, segment):
        segment_type = type(segment)
        if isinstance(segment_type, str):
            return self.matcher.match(segment) is not None
        elif isinstance(segment, AnyPattern):
            return True
        else:
            m = "Comparison between Regex and {segment!r} not supported"
            m = m.format(segment=segment)
            raise NotImplementedError(m)
            return False


class Literal(Pattern):
    def __init__(self, segment):
        self.segment = segment

    def __repr__(self):
        return "Literal({literal!r})".format(literal=self.segment)

    __str__ = __repr__

    def match(self, segment):
        return self.segment == segment


class And(Pattern):
    def __init__(self, pattern):
        self.patterns = parse_pattern(x for x in pattern.split('&'))

    def match(self, segment):
        return all(x.match(segment) for x in self.patterns)


class Or(Pattern):
    def __init__(self, pattern):
        self.patterns = parse_pattern(x for x in pattern.split('|'))

    def match(self, segment):
        return any(x.match(segment) for x in self.patterns)


class Inverse(Pattern):
    def __init__(self, pattern):
        self.pattern = parse_pattern(pattern)

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
    def __init__(self, column_names, rules=()):
        self.column_names = tuple(column_names)
        self.Row = namedtuple("MatcherRow", self.column_names)
        self.rules_set = {self.Row(*r) for r in rules}

    def _check_row_type(self, row):
        if not isinstance(row, self.Row):
            m = "rows must be of type Matcher.Row, not {row!r}"
            m = m.format(row=row)
            raise TypeError(m)

    def match(self, row):
        row = self.Row(*row)
        self._check_row_type(row)
        results = set()
        for tab_row in self.rules_set:
            item = {}
            for name in self.column_names:
                tab_val = getattr(tab_row, name)
                row_val = getattr(row, name)

                if tab_val.match(row_val):
                    item[name] = row_val
                else:
                    item = None
                    break

            if item is not None:
                val = self.Row(**item)
                results.add(val)

        return results


def parse_rule_file(filepath: str) -> List[List[Pattern]]:
    if not os.path.isfile(filepath):
        msg = "The given filepath {f!r} does not exit"
        msg.format(f=filepath)
        raise IOError(msg)

    with open(filepath, 'r') as f:
        data = json.load(f)

    column_names = data.get("column_names")
    if column_names is None:
        msg = "Rules must specify column names"
        raise ValueError(msg)

    rules = data.get("rules")
    rule_set = [
        [
            parse_pattern(pattern)
            for pattern in rule
        ]
        for rule in rules
    ]
    return Matcher(column_names, rule_set)
