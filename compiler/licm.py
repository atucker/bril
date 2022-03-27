import sys
import json
import cfg
import dominators
import data_flow
import cache
from collections import defaultdict


DEBUG = False


def debug_msg(*args):
    if DEBUG:
        print(*args, file=sys.stderr)


def find_loop_content(header, end, predecessors, dom):
    # Get every predecessor to end which is dominated by the header,
    # and return None if we hit something not dominated by the header
    contents = set(predecessors[end]) | {header, end}
    worklist = list(contents)

    # Gradually building up a worklist gets us the smallest set
    changed = True
    while changed:
        changed = False
        while len(worklist) > 0:
            node = worklist.pop()
            #debug_msg(f"Checking node {node}")
            for pred in predecessors[node]:
                if node != header:
                    if header not in dom[pred] :
                        #debug_msg(f"Header {header} not dominating"
                        #          f"predecessor {pred} of node {node}")
                        return None
                    elif pred not in contents and pred != header:
                        #debug_msg(f"Adding predecessor {pred}")
                        worklist.append(pred)
                        contents |= {pred}
                        changed = True

    # This checks that for every v in L,
    # either all the predecessors of v are in L or v=B
    for node in contents:
        assert node == header or set(predecessors[node]).issubset(contents)

    return contents


def find_loop_func(func, analysis=None):
    if analysis is None:
        analysis = {}
    blocks, predecessors, successors, dom = cache.func_ensure_analysis(
        func, analysis, [
            cache.BLOCKS, cache.PREDECESSORS, cache.SUCCESSORS,  cache.DOM
        ]
    )

    # First, find all the backedges
    possible_loops = {}
    for node, doms in dom.items():
        for dominator in doms:
            if dominator in successors[node]:
                if dominator not in possible_loops:
                    possible_loops[dominator] = set()
                possible_loops[dominator] |= {node}


    # Now find all the loops
    loops = []
    for header, ends in possible_loops.items():
        for end in ends:
            content = find_loop_content(header, end, predecessors, dom)
            if content is not None:
                loops.append({
                    'header': header,
                    'end': end,
                    'content': content
                })

    analysis['loops'] = loops
    return blocks, analysis, loops


def rename_labels(instrs, rename_from, rename_to):
    last_instr = instrs[-1]
    #debug_msg(f"last instr {last_instr}")
    if 'op' in last_instr and last_instr['op'] in {'jmp', 'br'}:
        labels = last_instr['labels']
        last_instr['labels'] = []
        for label in labels:
            if label == rename_from:
                last_instr['labels'].append(rename_to)
            else:
                last_instr['labels'].append(label)


def reconstitute_instrs(blocks, predecessors, preheaders, loop):
    instrs = []
    for name, code in blocks.items():
        if name in preheaders:
            header = name
            # Rename predecessors' labels
            for pred in predecessors[header]:
                if pred not in loop:
                    rename_labels(blocks[pred], header, f'{header}_preheader')
            instrs += [{'label': f'{header}_preheader'}]
            instrs += preheaders[header]
            instrs += code
        else:
            instrs += code
    return instrs


def licm(blocks, analysis, loop):
    """
    Perform loop invariant code movement

    We do this in two ways
    1) Returning a preheader with all the loop invariant code moved into it
    2) Mutating the blocks so that they don't have the loop invariant code
    """
    assert 'reach' in analysis
    assert 'dom' in analysis
    assert cache.SUCCESSORS in analysis
    block_in, block_out, _ = analysis['reach']
    for node, vars in block_in.items():
        for v, defs in vars.items():
            vars[v] = set(defs)

    # Do a quick usage analysis
    uses = defaultdict(lambda : defaultdict(lambda : []))
    for node, instrs in blocks.items():
        for i, instr in enumerate(instrs):
            if 'args' in instr:
                for arg in instr['args']:
                    uses[arg][node].append(i)

    # Also do a quick definition analysis
    defs = defaultdict(lambda : defaultdict(lambda : []))
    for node, instrs in blocks.items():
        for i, instr in enumerate(instrs):
            if 'dest' in instr:
                defs[instr['dest']][node].append(i)

    loop_invariant_lines = defaultdict(lambda : set())
    debug_instrs = []

    loop = loop['content']

    # Figure out our loop exits...
    exits = set()
    successors = analysis[cache.SUCCESSORS]
    for node in loop:
        if not set(successors[node]).issubset(loop):
            exits |= {node}

    """
    Finding LICM code:
    iterate to convergence:
    for every instruction in the loop:
        mark it as LI iff, for all arguments x, either:
            all reaching definitions of x are outside of the loop, or
            there is exactly one definition, and it is already marked as
                loop invariant
    """

    changed = True
    while changed:
        changed = False
        for node, instrs in blocks.items():
            if node in loop:
                for i, instr in enumerate(instrs):
                    debug_msg(node, i, instr)
                    line_is_loop_invariant = False
                    if 'op' in instr and instr['op'] == 'const':
                        line_is_loop_invariant = True

                    elif 'args' in instr:
                        # for all arguments in x
                        for arg in instr['args']:
                            if arg in block_in[node]:
                                reaching_defs = block_in[node][arg]
                                if len(reaching_defs) == 1:
                                    (def_block,) = reaching_defs
                                    if def_block in loop:
                                        arg_defs = defs[arg][def_block]
                                        marked_li = loop_invariant_lines[def_block]
                                        if arg_defs:
                                            if max(arg_defs) not in marked_li:
                                                # def is not marked loop invariant
                                                break
                                    else:
                                        # def_block not in loop -> defined out
                                        # of loop, and therefore okay
                                        pass
                                elif any(d in loop for d in reaching_defs):
                                    # arg has definition from within loop
                                    break
                            else:
                                arg_defs = defs[arg][node]
                                arg_defs = [d for d in arg_defs if d < i]
                                marked_li = loop_invariant_lines[node]
                                if arg_defs and max(arg_defs) not in marked_li:
                                    # def is not marked loop invariant
                                    break
                        else: # runs only if we don't break out of loop
                            line_is_loop_invariant = True

                    debug_msg(node, i, instr, line_is_loop_invariant)
                    if line_is_loop_invariant:
                        if i not in loop_invariant_lines[node]:
                            loop_invariant_lines[node] |= {i}
                            debug_instrs.append((node, i, instr))
                            changed = True
                            debug_msg(f"Adding {(node, i)}: {instr} to loop invariant")

    debug_msg(f"Loop invariant: {debug_instrs}")
    preheader = []
    """
    Safe to move to preheader if     
    1) The definition dominates all of its uses
    2) No other definitions of the same variable exist in the loop
    3) The instruction dominates all loop exits.
    """
    dom = analysis['dom']
    moved = defaultdict(lambda : [])
    for block, instrs in blocks.items():
        for i, instr in enumerate(instrs):
            if 'dest' in instr and i in loop_invariant_lines[block]:
                var = instr['dest']
                dom_uses = all(block in dom[node] for node in uses[var].keys())
                no_other_defs = len(defs[var]) == 1
                dom_exits = all(block in dom[node] for node in exits)
                debug_msg(f"Thinking of moving {(block, i)}: {instr}")
                debug_msg(f"dom uses: {dom_uses}, other defs: {no_other_defs}, dom exits: {dom_exits}")
                if dom_uses and no_other_defs  and dom_exits:
                    moved[block].append(i)
                    preheader.append(instr)

    for block, instrs in blocks.items():
        counter = 0
        for i in moved[block]:
            del instrs[i - counter]
            counter += 1

    return preheader


def find_loops(prog):
    for func in prog['functions']:
        blocks, analysis, loops = find_loop_func(func)
        debug_msg(f"Loops: {loops}")
        preheaders = {}
        analysis['reach'] = reach = data_flow.func_reachability(func, analysis)
        block_in, block_out, _ = reach
        for block, vars in block_in.items():
            for var in vars.keys():
                vars[var] = list(vars[var])

        debug_msg(loops)
        debug_msg(analysis[cache.SUCCESSORS])

        for loop in loops:
            preheaders[loop['header']] = licm(blocks, analysis, loop)

            func['instrs'] = reconstitute_instrs(
                blocks, analysis['predecessors'], preheaders, loop['content']
            )
    return prog


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'find_loop'
    if len(sys.argv) == 2:
        mode = sys.argv[1]
    if mode == 'find_loop':
        print(json.dumps(find_loops(prog), indent=2))