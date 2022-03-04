import json
import sys
import cfg
import dominators
import data_flow
from collections import defaultdict


DEBUG = False


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
                defs[var] |= {name}
    for var, blocks in defs.items():
        defs[var] = list(blocks)
    return defs


def get_var_types(func):
    var_types = {}
    for instr in func['instrs']:
        if 'dest' in instr and 'type' in instr:
            var_types[instr['dest']] = instr['type']
    if 'args' in func:
        for arg in func['args']:
            if 'type' in arg:
                var_types[arg['name']] = arg['type']
    return var_types


def func_to_ssa(func, func_prefix):
    # Insert a new entry label to make sure that we can use phi statements
    entry_label = 'b0'
    arg_name = f"{func['name']}.arg"
    if 'label' not in func['instrs'][0]:
        func['instrs'].insert(0, {'label': entry_label})
    else:
        entry_label = func['instrs'][0]['label']

    blocks, successors = cfg.make_func_cfg(func, func_prefix)
    assert f'{func_prefix}entry' in blocks
    dom = dominators.make_dominators(successors)
    dom_tree = dominators.dominance_tree(dom)
    frontier = dominators.dominance_frontier(successors, dom)
    reach_in, _, _ = data_flow.func_run_worklist_algorithm(
        func, data_flow.REACHABILITY, func_prefix
    )
    var_types = get_var_types(func)
    variable_definitions = get_defs(blocks)
    debug_print(f"Reachable: {reach_in}")
    debug_print(f"Frontier: {frontier}")

    # If we're trying to talk about an argument in the entry block, fix it
    added_new_entry = False
    new_entry_label = f'new_{entry_label}'

    # First, construct all the phi nodes
    named_phi_defs = defaultdict(lambda : {})
    phi_def_names = defaultdict(lambda : {})
    for var, definitions in variable_definitions.items():
        for block_name in definitions:
            for frontier_block in frontier[block_name]:
                if var not in named_phi_defs[frontier_block]:
                    in_blocks = reach_in[frontier_block][var]# - {frontier_block}
                    if len(in_blocks) > 0:
                        named_phi_defs[frontier_block][var] = {}
                        phi_def_names[frontier_block][var] = None
                        if frontier_block not in definitions:
                            definitions.append(frontier_block)
                        debug_print(f"in_blocks for {var}: {in_blocks}")
                        for in_block in in_blocks - {frontier_block}:
                            var_name = None
                            def_block = in_block
                            if in_block == arg_name:
                                var_name = var
                                def_block = entry_label
                                if frontier_block == entry_label:
                                    added_new_entry = True
                                    def_block = new_entry_label
                            named_phi_defs[frontier_block][var][def_block] = var_name
                        # We need to add the successor for the frontier blocks
                        if frontier_block in in_blocks:
                            for succ in successors[frontier_block]:
                                named_phi_defs[frontier_block][var][succ] = None

    debug_print(f"Phi definitions: {dict(named_phi_defs)}")
    debug_print(f"Phi def destinations: {dict(phi_def_names)}")

    var_name_stack = defaultdict(lambda : [])
    var_def_count = defaultdict(lambda : 0)
    if 'args' in func:
        for arg in func['args']:
            var_name_stack[arg['name']].append(arg['name'])

    """
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
        block_successors = list(successors[block_name])
        for successor in block_successors:
            debug_print(f"{block_name}'s successor {successor}, {named_phi_defs[successor]}")
            debug_print(f"\t Vars: {named_phi_defs[successor]}")
            for var in named_phi_defs[successor]:
                if block_name in named_phi_defs[successor][var] and var in var_name_stack:
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

    rename(f'{func_prefix}entry')

    for block_name, instrs in blocks.items():
        for var, named_defs in named_phi_defs[block_name].items():
            dest = phi_def_names[block_name][var]
            labels = []
            names = []
            for label, var_name in named_defs.items():
                if var_name is None:
                    var_name = '__undefined'
                labels.append(label)
                names.append(var_name)
                debug_print(f"{block_name}/{var}: {var_name} for {label}")

            instr = {
                'op': 'phi',
                'dest': dest,
                'args': names,
                'labels': labels
            }
            if var in var_types:
                instr['type'] = var_types[var]
            idx = 0
            if instrs and 'label' in instrs[0]:
                idx = 1
            if dest is not None: #and len(names) > 1:
                instrs.insert(idx, instr)

    func['instrs'] = []
    if added_new_entry:
        func['instrs'].append({'label': new_entry_label})
    for _, block in blocks.items():
        func['instrs'] += block

    return func


def to_ssa(prog):
    ssa_funcs = []
    for func in prog['functions']:
        ssa_funcs.append(func_to_ssa(func, cfg.func_prefix(func, prog)))
    prog['functions'] = ssa_funcs
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