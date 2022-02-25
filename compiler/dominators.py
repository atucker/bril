from functools import reduce
from collections import OrderedDict
import cfg
import json
import sys


def make_dominators(successors):
    predecessors = cfg.get_predecessors(successors)
    all_keys = set(predecessors.keys())
    dom = {}
    for node in predecessors.keys():
        dom[node] = all_keys

    changed = True
    while changed:
        changed = False
        for node, preds in predecessors.items():
            old_dom = dom[node]
            if preds:
                dom_preds = [dom[p] for p in preds]
            else:
                dom_preds = [set()]
            merged = reduce(lambda a, b: a & b, dom_preds, all_keys)
            dom[node] = {node} | merged
            if old_dom != dom[node]:
                changed = True

    return dom


def dominance_tree(dom):
    pass


def dominance_frontier(func_cfg, node):
    pass


def sort_dom(dom):
    sorted_dom = OrderedDict()
    for key in sorted(dom.keys()):
        sorted_dom[key] = sorted(list(dom[key]))
    return sorted_dom


if __name__ == "__main__":
    print(json.dumps(sort_dom(make_dominators(cfg.make_cfg(json.load(sys.stdin))[1])), indent=2))