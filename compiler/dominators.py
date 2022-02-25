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
    tree = {}
    predecessors = {}
    # Put the entry points in place
    for node, dominated_by in dom.items():
        if dominated_by == {node}:
            tree[node] = set()

    changed = True
    while changed:
        changed = False
        for pred, ancestors in dom.items():
            for node, dominated_by in dom.items():
                if node != pred and dominated_by == {node} | ancestors:
                    if node not in tree[pred]:
                        tree[pred] = tree[pred] | {node}
                        changed = True
                    if node not in tree:
                        tree[node] = set()
                        changed = True
    return tree


def dominance_frontier(dom):
    pass


def sort_json(data):
    sorted_data = OrderedDict()
    for key in sorted(data.keys()):
        sorted_data[key] = sorted(list(data[key]))
    return sorted_data


def route_commands():
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'dom'
    if len(sys.argv) == 2:
        mode = sys.argv[1]

    def output(json_data):
        print(json.dumps(sort_json(json_data), indent=2))

    dom = make_dominators(cfg.make_cfg(prog)[1])
    if mode == 'dom':
        output(dom)
    if mode == 'tree':
        output(dominance_tree(dom))
    elif mode == 'front':
        output(dominance_frontier(dom))


if __name__ == "__main__":
    route_commands()