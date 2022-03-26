import sys
import json
import cfg
import dominators


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
            for pred in predecessors[node]:
                if header not in dom[pred]:
                    return None

                if pred not in contents and pred != header:
                    worklist.append(pred)
                    contents |= {pred}
                    changed = True

    # This checks that for every v in L,
    # either all the predecessors of v are in L or v=B
    for node in contents:
        assert node == header or predecessors[node].issubset(contents)

    return contents


def find_loop_func(func):
    blocks, successors = cfg.make_func_cfg(func)
    predecessors = cfg.get_predecessors(successors)
    dom = dominators.make_dominators(successors)

    # First, find all the backedges
    possible_loops = {}
    for node, doms in dom.items():
        for dominator in doms:
            if dominator in successors[node]:
                if dominator not in possible_loops:
                    possible_loops[dominator] = set()
                possible_loops |= {node}

    # Now find all the loops
    loops = []
    for header, ends in possible_loops:
        for end in ends:
            content = find_loop_content(header, end, predecessors, dom)
            if content is not None:
                loops.append({
                    'header': header,
                    'end': end,
                    'content': content
                })
    return blocks, predecessors, loops


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
    return instrs


def find_loops(prog):
    return prog
    for func in prog['functions']:
        blocks, predecessors, loops = find_loop_func(func)
        preheaders = {}
        for loop in loops:
            preheaders[loop['header']] = []
        func['instrs'] = reconstitute_instrs(blocks, predecessors, preheaders)
    return prog


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'find_loop'
    if len(sys.argv) == 2:
        mode = sys.argv[1]
    if mode == 'find_loop':
        print(json.dumps(find_loops(prog)))