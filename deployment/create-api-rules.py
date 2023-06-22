#! /usr/bin/env python3
import fileinput
import json
from typing import List


def longest_common_prefix(strs: List[str]) -> str:
    length = len(strs[0])
    for i in range(1, len(strs)):
        length = min(length, len(strs[i]))
        while length > 0 and strs[0][0:length] != strs[i][0:length]:
            length = length - 1
            if length == 0:
                return None
    return strs[0][0:length]


files = [line.replace(".json", "").strip() for line in fileinput.input()]
prefix = longest_common_prefix(files)

if prefix is not None:
    rules = [
        ["_" + prefix, "*"]
    ]
else:
    rules = [
        ["!_java.util", "*"],
        ["!_java.io", "*"],
        ["!_java.lang", "*"],
        ["!_kotlin.collection", "*"],
        ["!_kotlin.", "*"],
        ["!_scala.", "*"],
        ["!_scala.collection", "*"],
    ]

data = {
    "column_names": ["class_", "api_name"],
    "func": "all",
    "rules": rules,
}

print(json.dumps(data, indent=2))
