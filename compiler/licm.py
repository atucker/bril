import sys
import json
import cfg
import dominators
import data_flow
import cache


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
    if 'op' in last_instr and last_instr['op'] in {'jmp', 'br'}:
        args = last_instr['args']
        last_instr['args'] = []
        for arg in args:
            if arg == rename_from:
                last_instr['args'].append(rename_to)
            else:
                last_instr['args'].append(arg)


def reconstitute_instrs(blocks, predecessors, preheaders):
    instrs = []
    for name, code in blocks.items():
        if name in preheaders:
            header = name
            # Rename predecessors' labels
            for pred in predecessors[header]:
                rename_labels(blocks[pred], header, f'{header}_preheader')
            instrs += preheaders[header]
            instrs += code
        else:
            instrs += code
    return instrs


def licm(func, analysis, loops):
    """
    Perform loop invariant code movement

    We do this in two ways
    1) Returning a preheader with all the loop invariant code moved into it
    2) Mutating the blocks so that they don't have the loop invariant code
    """
    """
    Finding LICM code:
    iterate to convergence:
    for every instruction in the loop:
        mark it as LI iff, for all arguments x, either:
            all reaching definitions of x are outside of the loop, or
            there is exactly one definition, and it is already marked as
                loop invariant
           
    Safe to move to preheader if     
    1) The definition dominates all of its uses
    2) No other definitions of the same variable exist in the loop
    3) The instruction dominates all loop exits.
    """
    analysis['reach'] = reach = data_flow.func_reachability(func, analysis)
    block_in, block_out = reach
    return []


def find_loops(prog):
    for func in prog['functions']:
        blocks, analysis, loops = find_loop_func(func)
        preheaders = {}
        for loop in loops:
            preheaders[loop['header']] = licm(blocks, loops, analysis)
        func['instrs'] = reconstitute_instrs(
            blocks, analysis['predecessors'], preheaders
        )
    return prog


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'find_loop'
    if len(sys.argv) == 2:
        mode = sys.argv[1]
    if mode == 'find_loop':
        print(json.dumps(find_loops(prog)))