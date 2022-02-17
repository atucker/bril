import json
import sys
import cfg
from collections import defaultdict, OrderedDict
from functools import reduce

FORWARD = "FORWARD"
BACKWARD = "BACKWARD"
NULL = "∅"


class Spec:
    def __init__(self, *, direction, init, merge, transfer, stringify):
        """
        init should mutate inputs
        merge and transfer should not mutate inputs
        """
        assert direction in {FORWARD, BACKWARD}
        self.direction = direction
        self.init = init
        self.merge = merge
        self.transfer = transfer
        self.stringify = stringify


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


def get_used(instrs):
    used = set()
    for instr in instrs:
        if 'args' in instr:
            used = used | set(instr['args'])
    return used


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
    for var in sorted(var_varsion_set.keys()):
        versions = var_varsion_set[var]
        assert len(versions) > 0
        for ver in sorted(versions):
            ans += f"{var}/{ver}, "
    return ans[:-2]


def stringify_vars(var_varsion_set):
    ans = ""
    if len(var_varsion_set.keys()) == 0:
        return NULL
    for var in sorted(var_varsion_set.keys()):
        ans += f"{var}, "
    return ans[:-2]


def copy_var_version_set(var_version_set):
    ans = {}
    for var, versions in var_version_set.items():
        ans[var] = set(versions)
    return ans


def run_worklist_algorithm(spec):
    prog = json.load(sys.stdin)
    blocks, successors = cfg.make_cfg(prog)
    predecessors = get_predecessors(successors)

    block_in = {}
    block_out = {}
    for name in blocks.keys():
        block_in[name] = {}
        block_out[name] = {}

    spec.init(prog, block_in, block_out)

    worklist = [*blocks.keys()]
    while len(worklist) > 0:
        name = worklist.pop()
        print(f"{name}")
        print(f"\tBefore:")
        print(f"\t\t{block_in[name]}")
        print(f"\t\t{block_out[name]}")

        instrs = blocks[name]
        if spec.direction == FORWARD:
            prev_str = spec.stringify(block_out[name])
            block_in[name] = inpt = spec.merge(
                block_in[name],
                [copy_var_version_set(block_out[p]) for p in predecessors[name]]
            )
            block_out[name] = outpt = spec.transfer(
                copy_var_version_set(inpt), name, instrs
            )
            if prev_str != spec.stringify(outpt):
                for succ in successors[name]:
                    if succ not in worklist:
                        worklist.append(succ)
        elif spec.direction == BACKWARD:
            prev_str = spec.stringify(block_in[name])
            block_out[name] = outpt = spec.merge(
                block_out[name],
                [copy_var_version_set(block_in[p]) for p in successors[name]]
            )
            block_in[name] = inpt = spec.transfer(
                copy_var_version_set(outpt), name, instrs
            )
            if prev_str != spec.stringify(inpt):
                print(predecessors[name])
                for pred in predecessors[name]:
                    if pred not in worklist:
                        worklist.append(pred)
        else:
            raise NotImplementedError()
        print(f"\tAfter:")
        print(f"\t\t{block_in[name]}")
        print(f"\t\t{block_out[name]}")

    for name in blocks.keys():
        print(f"{name}:")
        print(f"  in:  {spec.stringify(block_in[name])}")
        print(f"  out: {spec.stringify(block_out[name])}")


def init_add_args(prog, inpt, outpt):
    for func in prog['functions']:
        key = f"{func['name']}.entry"
        if len(prog['functions']) == 1:
            key = 'entry'

        inpt[key] = {}
        if 'args' in func:
            for arg in func['args']:
                inpt[key][arg['name']] = {f"{func['name']}.arg"}


def merge(start_input, inpts):
    return reduce(join_vars, inpts, start_input)


def reachability_transfer(inpt, name, instrs):
    outpt = copy_var_version_set(inpt)
    defined = get_defined(instrs)
    for var in defined:
        # If it's already there, overwrite
        # If it's not, add it
        outpt[var] = {name}
    return outpt


def live_transfer(outpt, name, instrs):
    inpt = copy_var_version_set(outpt)
    used = set()
    defined = set()
    # order matters so I have to do a loop that does both of these
    for instr in instrs:
        if 'args' in instr:
            for var in instr['args']:
                if var not in defined:
                    used |= {var}
        if 'dest' in instr:
            dest = instr['dest']
            if dest in inpt:
                del inpt[dest]
            defined |= {dest}

    for var in used:
        if var not in inpt:
            inpt[var] = set()
        inpt[var] |= {name}

    return inpt


def route_worklists():
    assert len(sys.argv) in {1, 2}
    mode = sys.argv[1]
    print(mode)
    if mode == 'reachability':
        run_worklist_algorithm(Spec(
            direction=FORWARD,
            init=init_add_args,
            merge=merge,
            transfer=reachability_transfer,
            stringify=stringify_var_version_set
        ))
    elif mode == 'live':
        run_worklist_algorithm(Spec(
            direction=BACKWARD,
            init=lambda *args: None,
            merge=merge,
            transfer=live_transfer,
            stringify=stringify_var_version_set
        ))
    else:
        raise NotImplementedError()


if __name__ == "__main__":
    route_worklists()