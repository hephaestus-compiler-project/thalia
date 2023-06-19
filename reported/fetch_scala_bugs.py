"""Fetch scala/dotty bugs.

"""
import argparse
import requests
import os
import json
import re
from copy import deepcopy
from datetime import datetime


COMPILER = "dotty"
LANGUAGE = "Scala"
SCHEMA = {
    "date": "",
    "language": LANGUAGE,
    "compiler": COMPILER,
    "version": "",
    "bugid": "",
    "title": "",
    "links": {
        "issuetracker": "",
        "fix": ""
    },
    "oracle": "",
    "mutator": "",
    "severity": "",
    "reporter": "",
    "status": "",
    "resolution": "",
    "resolutiondate": "",
    "symptom": "",
    "bugtype": "",
    "resolvedin": "",
    "test": [],
    "chars": {
        "characteristics": []
    },
    "errormsg": [],
    "comment": ""
}


def get_code_fragments(text):
    matches = re.findall('(?:```)(.*?)(?:```)', text, flags=re.I | re.DOTALL)
    res = []
    for m in matches:
        res.append([x.replace('\t', '  ') for x in m.splitlines()
                    if x.strip() not in ('', 'scala')])
        res = [r for r in res if len(r) > 0]
    return res


def get_data(lookup, later_than):
    page = 1
    max_per_request = 100
    base = "https://api.github.com/repos/lampepfl/dotty/issues"
    url1 = "{base}?state=all&creator={creator}&per_page={pp}&page={p}".format(
        base=base,
        creator="theosotr",
        pp=max_per_request,
        p=page
    )
    url2 = "{base}?state=all&creator={creator}&per_page={pp}&page={p}".format(
        base=base,
        creator="stefanoschaliasos",
        pp=max_per_request,
        p=page
    )
    response = requests.get(url1).json()
    response.extend(requests.get(url2).json())
    results = []
    dotty_github_url = "https://github.com/lampepfl/dotty/issues/"
    for item in response:
        created = datetime.strptime(
            item['created_at'], "%Y-%m-%dT%H:%M:%S%z")
        if later_than and created.date() < later_than.date():
            continue
        try:
            resolution = datetime.strptime(
                item['closed_at'], "%Y-%m-%dT%H:%M:%S.%f%z")
        except:
            resolution = None
        passed = resolution - created if resolution else None
        reporter = item['user']['login']
        bugid = str(item['number'])
        if bugid in lookup:
            bug = lookup[bugid]
        else:
            bug = deepcopy(SCHEMA)
        bug['date'] = str(created)
        bug['resolutiondate'] = str(resolution)
        bug['resolvedin'] = str(passed)
        bug['bugid'] = bugid
        bug['title'] = item['title']
        bug['links']['issuetracker'] = dotty_github_url + bugid
        bug['reporter'] = reporter
        bug['status'] = str(item['state'].capitalize())

        description = item['body']
        code_fragments = get_code_fragments(description)
        if len(code_fragments) >= 1:
            if not len(lookup.get(bug['bugid'], {}).get('test', [])) >= 1:
                bug['test'] = code_fragments[0]
        if len(code_fragments) >= 2:
            if not len(lookup.get(bug['bugid'], {}).get('errormsg', [])) >= 1:
                bug['errormsg'] = code_fragments[1]
        if len(code_fragments) != 2:
            print("{}: code fragments {}".format(
                bug['bugid'], len(code_fragments)
            ))
        if bug.get('chars', None) is None:
            bug['chars'] = SCHEMA['chars']
        results.append(bug)
    # Add bugs in lookup but not in current set (e.g. from another tracker)
    ids = {bug['bugid'] for bug in results}
    for bug_id, bug in lookup.items():
        if bug_id not in ids:
            if bug.get('chars', None) is None:
                bug['chars'] = SCHEMA['chars']
            results.append(bug)
    return results


def get_args():
    parser = argparse.ArgumentParser(
        description='Fetch kotlin front-end bugs.')
    parser.add_argument("output", help="File to save the bugs.")
    parser.add_argument("--later-than", type=str, required=False)
    return parser.parse_args()


def main():
    args = get_args()
    lookup = {}
    if os.path.isfile(args.output):
        with open(args.output) as f:
            tmp = json.load(f)
            for bug in tmp:
                lookup[bug['bugid']] = bug
    if args.later_than:
        later_than = datetime.strptime(args.later_than,
                                       "%Y-%m-%d")
    data = get_data(lookup, later_than)
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
    main()
