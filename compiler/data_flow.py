import json
import sys
import cfg
from collections import defaultdict, OrderedDict
from functools import reduce

FORWARD = "FORWARD"
BACKWARD = "BACKWARD"
NULL = "∅"


class Spec:
    def __init__(self, *, direction, init, merge, transfer, copy, stringify):
        """
        init should mutate inputs
        merge and transfer should not mutate inputs
        """
        assert direction in {FORWARD, BACKWARD}
        self.direction = direction
        self.init = init
        self.merge = merge
        self.transfer = transfer
        self.copy = copy
        self.stringify = stringify


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


def run_worklist_algorithm(prog, spec, print_output=True):
    blocks, successors = cfg.make_cfg(prog)
    predecessors = cfg.get_predecessors(successors)

    block_in, block_out = spec.init(prog, blocks)

    if spec.direction == BACKWARD:
        block_in, block_out = block_out, block_in
        predecessors, successors = successors, predecessors

    worklist = [*blocks.keys()]
    while len(worklist) > 0:
        name = worklist.pop()

        prev_str = spec.stringify(block_out[name])
        block_in[name] = inpt = spec.merge(
            block_in[name],
            [spec.copy(block_out[p]) for p in predecessors[name]]
        )
        block_out[name] = outpt = spec.transfer(
            spec.copy(inpt), name, blocks[name]
        )
        if prev_str != spec.stringify(outpt):
            for succ in successors[name]:
                if succ not in worklist:
                    worklist.append(succ)

    if spec.direction == BACKWARD:
        block_in, block_out = block_out, block_in

    if print_output:
        for name in blocks.keys():
            print(f"{name}:")
            print(f"  in:  {spec.stringify(block_in[name])}")
            print(f"  out: {spec.stringify(block_out[name])}")

    return block_in, block_out


def init_add_args_var_version_set(prog, blocks):
    block_in = {}
    block_out = {}
    for name in blocks.keys():
        block_in[name] = {}
        block_out[name] = {}

    for func in prog['functions']:
        key = f"{func['name']}.entry"
        if len(prog['functions']) == 1:
            key = 'entry'

        block_in[key] = {}
        if 'args' in func:
            for arg in func['args']:
                block_in[key][arg['name']] = {f"{func['name']}.arg"}

    return block_in, block_out


def join_var_version_set(left, right):
    ans = {}
    for key in left.keys():
        ans[key] = set(left[key])
    for key in right.keys():
        if key in ans:
            ans[key] |= right[key]
        else:
            ans[key] = set(right[key])
    return ans


def merge_var_version_set(start_input, inpts):
    return reduce(join_var_version_set, inpts, start_input)


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


def copy_var_version_set(var_version_set):
    ans = {}
    for var, versions in var_version_set.items():
        ans[var] = set(versions)
    return ans


def reachability_transfer(outpt, name, instrs):
    defined = get_defined(instrs)
    for var in defined:
        # If it's already there, overwrite
        # If it's not, add it
        outpt[var] = {name}
    return outpt


def init_var_set(prog, blocks):
    block_in = {}
    block_out = {}
    for name in blocks.keys():
        block_in[name] = set()
        block_out[name] = set()

    return block_in, block_out


def merge_var_set(start_input, inpts):
    return reduce(lambda left, right: left | right, inpts, start_input)


def stringify_var_set(var_set):
    if len(var_set) == 0:
        return NULL
    return ', '.join(sorted(var_set))


def copy_var_set(var_set):
    return set(var_set)


def live_transfer(outpt, name, instrs):
    inpt = copy_var_set(outpt)
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
            inpt -= {dest}
            defined |= {dest}

    return inpt | used


REACHABILITY = Spec(
    direction=FORWARD,
    init=init_add_args_var_version_set,
    merge=merge_var_version_set,
    transfer=reachability_transfer,
    copy=copy_var_version_set,
    stringify=stringify_var_version_set
)


def route_worklists():
    assert len(sys.argv) in {1, 2}
    mode = sys.argv[1]
    print(mode)
    prog = json.load(sys.stdin)
    if mode == 'reachability':
        run_worklist_algorithm(prog, REACHABILITY)
    elif mode == 'live':
        run_worklist_algorithm(prog, Spec(
            direction=BACKWARD,
            init=init_var_set,
            merge=merge_var_set,
            transfer=live_transfer,
            copy=copy_var_set,
            stringify=stringify_var_set
        ))
    else:
        raise NotImplementedError()


if __name__ == "__main__":
    route_worklists()