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
    # Put the entry points in place
    for node, dominated_by in dom.items():
        if dominated_by == {node}:
            tree[node] = set()

    changed = True
    while changed:
        changed = False
        for pred, ancestors in dom.items():
            for node, dominated_by in dom.items():
                # If you find a node which is dominated by your ancestors +
                # itself, then you've found an immediate successor
                if node != pred and dominated_by == {node} | ancestors:
                    if node not in tree[pred]:
                        tree[pred] = tree[pred] | {node}
                        changed = True
                    if node not in tree:
                        tree[node] = set()
                        changed = True
    return tree


def dominance_frontier(successors, dom):
    dominates = {}
    for key in dom.keys():
        dominates[key] = set()
    for dominand, values in dom.items():
        for dominator in values:
            dominates[dominator] |= {dominand}

    predecessors = cfg.get_predecessors(successors)
    for key, value in predecessors.items():
        predecessors[key] = set(value)

    frontier = {}
    for key in dom.keys():
        frontier[key] = set()
    for dominator, dominands in dominates.items():
        for node, preds in predecessors.items():
            # strict domination
            if node not in dominands - {dominator} and preds & dominands:
                frontier[dominator] |= {node}

    return frontier


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

    successors = cfg.make_cfg(prog)[1]
    dom = make_dominators(successors)
    if mode == 'dom':
        output(dom)
    if mode == 'tree':
        output(dominance_tree(dom))
    elif mode == 'front':
        output(dominance_frontier(successors, dom))


if __name__ == "__main__":
    route_commands()