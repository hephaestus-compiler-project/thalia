import os
import json

from bs4 import BeautifulSoup


def file2html(path):
    with open(path, 'r') as f:
        return BeautifulSoup(f, "html.parser")


def dict2json(outdir, data):
    if data is None:
        # Nothing to store.
        return
    path = os.path.join(outdir, data["name"]) + ".json"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
