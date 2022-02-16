import json
import sys
import cfg
from collections import defaultdict, OrderedDict
from functools import reduce

"""
in[entry] = init
out[*] = init

worklist = all blocks
while worklist is not empty:
    b = pick any block from worklist
    in[b] = merge(out[p] for every predecessor p of b)
    out[b] = transfer(b, in[b])
    if out[b] changed:
        worklist += successors of b
"""

NULL = "∅"


def get_predecessors(successors):
    ans = {}
    for name, _ in successors.items():
        ans[name] = []
    for name, ss in successors.items():
        for successor in ss:
            ans[successor].append(name)
    return ans


def get_defined(instrs):
    defined = set()
    for instr in instrs:
        if 'dest' in instr:
            defined = defined | {instr['dest']}
    return defined


def join_vars(left, right):
    ans = {}
    for key in left.keys():
        ans[key] = set(left[key])
    for key in right.keys():
        if key in ans:
            ans[key] |= right[key]
        else:
            ans[key] = set(right[key])
    return ans


def stringify_var_version_set(var_varsion_set):
    ans = ""
    if len(var_varsion_set.keys()) == 0:
        return NULL
    for var, versions in var_varsion_set.items():
        assert len(versions) > 0
        for ver in sorted(versions):
            ans += f"{var}/{ver}, "
    return ans[:-2]


def do_reachability():
    prog = json.load(sys.stdin)
    blocks, successors = cfg.make_cfg(prog)
    predecessors = get_predecessors(successors)

    assert len(sys.argv) in {1, 2}
    mode = sys.argv[1]
    assert mode.lower() in {'reachability'}

    in_reachable = {}
    # Do this manually instead of using a defaultdict so that the program
    # crashes if I try to access something that isn't there...
    for name in blocks.keys():
        in_reachable[name] = {}
    out_reachable = {}

    # Go through and grab the args for each function...
    for name in blocks.keys():
        out_reachable[name] = {}
    for func in prog['functions']:
        key = f"{func['name']}.entry"
        if len(prog['functions']) == 1:
            key = 'entry'

        in_reachable[key] = {}
        if 'args' in func:
            for arg in func['args']:
                in_reachable[key][arg['name']] = {f"{func['name']}.arg"}

    worklist = [*blocks.items()]
    for name, instrs in worklist:
        # Cache what we had before
        prev_outpt_str = stringify_var_version_set(out_reachable[name])

        # Compute our input
        inpt = reduce(
            join_vars, [out_reachable[p] for p in predecessors[name]], in_reachable[name]
        )

        # Compute our output
        outpt = dict(**inpt) # copy so we don't mutate the inpt
        defined = get_defined(instrs)
        for var in defined:
            # If it's already there, overwrite
            # If it's not, add it
            outpt[var] = {name}

        # Write out the values
        in_reachable[name] = inpt
        out_reachable[name] = outpt

        # Add to the worklist if our results changed
        if prev_outpt_str != stringify_var_version_set(outpt):
            worklist += [(succ, blocks[succ]) for succ in successors[name]]

    for name in blocks.keys():
        print(f"{name}:")
        print(f"  in:  {stringify_var_version_set(in_reachable[name])}")
        print(f"  out: {stringify_var_version_set(out_reachable[name])}")


if __name__ == "__main__":
    do_reachability()