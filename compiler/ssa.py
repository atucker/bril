import json
import sys
import cfg
import dominators
import data_flow
from collections import defaultdict


DEBUG = True


def debug_print(s):
    if DEBUG:
        print(s, file=sys.stderr)


def get_defs(named_blocks):
    defs = {}
    for name, block in named_blocks.items():
        for instr in block:
            if 'dest' in instr:
                var = instr['dest']
                if var not in defs:
                    defs[var] = set()
                defs[var] |= {block}
    return defs


def get_defined_variables(named_blocks):
    defined_variables = {}
    for name, block in named_blocks.items():
        defined_variables[name] = set()
        for instr in block:
            if 'dest' in instr:
                defined_variables[name] |= {instr['dest']}
    return defined_variables


def get_used_variables(named_blocks):
    used_variables = {}
    for name, block in named_blocks.items():
        used_variables[name] = data_flow.get_used(block)
    return used_variables


def get_var_types(prog):
    # TODO: Handle args
    var_types = {}
    for func in prog['functions']:
        for instr in func['instrs']:
            if 'dest' in instr:
                var_types[instr['dest']] = instr['type']
    return var_types


def to_ssa(prog):
    # We can fix this in the future maybe
    assert len(prog['functions']) == 1

    """
    Implements to ssa.

    It is intended to handle programs consisting of a single function, but
    unfortunately accepts a single program as an argument.
    """
    """
    Converting to SSA

    To convert to SSA, we want to insert ϕ-nodes whenever there are distinct paths containing distinct definitions of a variable. We don’t need ϕ-nodes in places that are dominated by a definition of the variable. So what’s a way to know when control reachable from a definition is not dominated by that definition? The dominance frontier!

    We do it in two steps. First, insert ϕ-nodes:

    for v in vars:
       for d in Defs[v]:  # Blocks where v is assigned.
         for block in DF[d]:  # Dominance frontier.
           Add a ϕ-node to block,
             unless we have done so already.
           Add block to Defs[v] (because it now writes to v!),
             unless it's already in there.
    """
    blocks, successors = cfg.make_cfg(prog)
    assert 'entry' in blocks
    dom = dominators.make_dominators(successors)
    dom_tree = dominators.dominance_tree(dom)
    reach_in, _ = data_flow.run_worklist_algorithm(
        prog, data_flow.REACHABILITY, print_output=False
    )
    debug_print(f"Reaching defs: {reach_in}")
    defined_variables = get_defined_variables(blocks)
    debug_print(f"Defined variables: {defined_variables}")
    used_variables = get_used_variables(blocks)
    var_types = get_var_types(prog)

    # First, construct all the phi nodes from our reachability definitiong
    named_phi_defs = {}
    phi_def_names = {}
    for block_name, reaching_defs in reach_in.items():
        named_phi_defs[block_name] = {}
        phi_def_names[block_name] = {}
        for var in defined_variables[block_name] | used_variables[block_name]:
            if var in reaching_defs:
                reaching_defs[var] -= {block_name}
            if var in reaching_defs and len(reaching_defs[var]) > 1:
                named_phi_defs[block_name][var] = {}
                phi_def_names[block_name][var] = None
                for in_block in reaching_defs[var]:
                    named_phi_defs[block_name][var][in_block] = None
    debug_print(f"Reaching defs: {reach_in}")
    debug_print(f"phi_def_names: {phi_def_names}")
    """
    stack[v] is a stack of variable names (for every variable v)

    def rename(block):
      for instr in block:
        replace each argument to instr with stack[old name]

        replace instr's destination with a new name
        push that new name onto stack[old name]

      for s in block's successors:
        for p in s's ϕ-nodes:
          Assuming p is for a variable v, make it read from stack[v].

      for b in blocks immediately dominated by block:
        # That is, children in the dominance tree.
        rename(b)

      pop all the names we just pushed onto the stacks

    rename(entry)
    """
    var_name_stack = defaultdict(lambda : [])
    var_def_count = defaultdict(lambda : 0)

    def rename(block_name):
        var_name_depths = dict(
            (key, len(value)) for key, value in var_name_stack.items()
        )
        pops = defaultdict(lambda : 0)

        def rename_var(var):
            var_name = f"{var}.{var_def_count[var]}"
            var_name_stack[var].append(var_name)
            var_def_count[var] += 1
            pops[var] += 1
            return var_name

        # First, name all of our phi definitions since they happen as soon as
        # we enter the block
        for var in named_phi_defs[block_name]:
            phi_def_names[block_name][var] = rename_var(var)

        # Now, rename all of the variables in instructions
        for instr in blocks[block_name]:
            if 'args' in instr:
                renamed_args = []
                for arg in instr['args']:
                    assert arg in var_name_stack
                    assert len(var_name_stack[arg]) > 0
                    renamed_args.append(var_name_stack[arg][-1])
                instr['args'] = renamed_args
            if 'dest' in instr:
                instr['dest'] = rename_var(instr['dest'])

        # Now, tell our successors' phi definitions about our new block names
        for successor in successors[block_name]:
            debug_print(f"{block_name}'s successor {successor}, {named_phi_defs[successor]}")
            debug_print(f"\t Vars: {named_phi_defs[successor]}")
            for var in named_phi_defs[successor]:
                if block_name in named_phi_defs[successor][var]:
                    new_name = var_name_stack[var][-1]
                    named_phi_defs[successor][var][block_name] = new_name
                    debug_print(f'{successor}: {var}/{block_name} -> {new_name}')

        # Now, get our immediate dominands renamed
        for dom_successor in dom_tree[block_name]:
            rename(dom_successor)

        # Now pop off all our new variable names, and integrity check
        for var in pops:
            while pops[var] > 0:
                var_name_stack[var].pop()
                pops[var] -= 1

        for var in var_name_stack:
            if var in var_name_depths:
                assert var_name_depths[var] == len(var_name_stack[var])
            else:
                assert len(var_name_stack[var]) == 0

    rename('entry')

    for block_name, instrs in blocks.items():
        for var, named_defs in named_phi_defs[block_name].items():
            dest = phi_def_names[block_name][var]
            labels = []
            names = []
            for label, var_name in named_defs.items():
                labels.append(label)
                names.append(var_name)
                #debug_print(f"{block_name, var, named_defs, reach_in[block_name]}")
                #assert var_name is not None
            instr = {
                'op': 'phi',
                'type': var_types[var],
                'dest': dest,
                'args': names,
                'labels': labels
            }
            idx = 0
            if instrs and 'label' in instrs[0]:
                idx = 1
            instrs.insert(idx, instr)

    # put the program back together with phis
    for func in prog['functions']:
        func['instrs'] = []
        for _, block in blocks.items():
            func['instrs'] += block

    return prog


def from_ssa(prog):
    """
    Eventually, we need to convert out of SSA form to generate efficient code
    for real machines that don’t have phi-nodes and do have finite space for
    variable storage.

    The basic algorithm is pretty straightforward. If you have a ϕ-node:

    v = phi .l1 x .l2 y;
    Then there must be assignments to x and y (recursively) preceding this
    statement in the CFG. The paths from x to the phi-containing block and from
    y to the same block must “converge” at that block. So insert code into the
    phi-containing block’s immediate predecessors along each of those two
    paths: one that does v = id x and one that does v = id y. Then you can
    delete the phi instruction.
    """
    pass


def route_commands():
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'to'
    if len(sys.argv) == 2:
        mode = sys.argv[1]
    if mode == 'to':
        print(json.dumps(to_ssa(prog)))
    elif mode == 'from':
        print(json.dumps(from_ssa(prog)))
    else:
        raise NotImplementedError


if __name__ == "__main__":
    route_commands()

    blah = [
    {"label": "entry"},
    {"dest": "i.0", "op": "const", "type": "int", "value": 1},
    {"labels": ["loop"], "op": "jmp"},
    {"label": "loop"},
    {"op": "phi", "type": "int", "dest": "i.1", "args": ["i.2", "i.0"], "labels": ["body", "entry"]},
    {"dest": "max.0", "op": "const", "type": "int", "value": 10},
    {"args": ["i.1", "max.0"], "dest": "cond.0", "op": "lt", "type": "bool"},
    {"args": ["cond.0"], "labels": ["body", "exit"], "op": "br"},
    {"label": "body"},
    {"args": ["i.1", "i.1"], "dest": "i.2", "op": "add", "type": "int"},
    {"labels": ["loop"], "op": "jmp"},
    {"label": "exit"},
    {"op": "phi", "type": "int", "dest": "i.3", "args": [null, null], "labels": ["body", "entry"]},
    {"args": ["i.3"], "op": "print"}
]