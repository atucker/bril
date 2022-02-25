from functools import reduce
from collections import OrderedDict
import cfg
import json
import sys
import os
import subprocess


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


def check(dom, in_fname):
    seen = set()
    all_good = True
    for line in open(in_fname, 'r').readlines():
        line = line.strip()
        try: # skip ints
            int(line)
        except ValueError:
            if not dom[line].issubset(seen):
                all_good = False
                print(f"Mistake found: in {line}, saw {seen}, "
                      f"but dominated by {dom[line]}")
            seen |= {line}
    return all_good


def sort_json(data):
    sorted_data = OrderedDict()
    for key in sorted(data.keys()):
        sorted_data[key] = sorted(list(data[key]))
    return sorted_data


def route_commands():
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2, 3}
    mode = 'dom'
    if len(sys.argv) > 1:
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
    elif mode == 'check':
        assert len(sys.argv) == 3
        fname = sys.argv[2]
        trace_fname = fname + ".trace"
        print(check(dom, trace_fname))


if __name__ == "__main__":
    route_commands()