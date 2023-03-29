import os
import json

from bs4 import BeautifulSoup


def file2html(path):
    with open(path, 'r') as f:
        return BeautifulSoup(f, "html.parser")


def dict2json(outdir, data, name=None):
    if data is None:
        # Nothing to store.
        return
    path = os.path.join(outdir, name or data["name"]) + ".json"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def top_level_split(s: str, delimiters=("<", ">")):
    """
    Split `s` by top-level commas only.
    Commas within signs are ignored.

    Taken from: https://stackoverflow.com/a/33527583
    """
    # Parse the string tracking whether the current character is within
    # parentheses.
    balance = 0
    parts = []
    part = ''
    start, end = delimiters

    for c in s:
        part += c
        if c == start:
            balance += 1
        elif c == end:
            balance -= 1
        elif c == ',' and balance == 0:
            parts.append(part[:-1].strip())
            part = ''
    # Capture last part
    if len(part):
        parts.append(part.strip())

    return parts
