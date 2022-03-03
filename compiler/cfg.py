import json
import sys
from collections import OrderedDict
import int_string

TERMINATORS = {'jmp', 'br', 'ret'}


def make_blocks(body):
    yielded = False
    cur_block = []
    for instr in body:
        if 'op' in instr:
            cur_block.append(instr)
            if instr['op'] in TERMINATORS:
                if cur_block or not yielded:
                    yielded = True
                    yield cur_block
                cur_block = []
        elif 'label' in instr:
            if cur_block or not yielded:
                yielded = True
                yield cur_block
            cur_block = [instr]
        else:
            assert False, f"{instr} has neither an op nor label"
    if cur_block: yield cur_block


def name_blocks(func_name, blocks):
    named_blocks = OrderedDict()
    for block in blocks:
        name = f"{func_name}b{len(named_blocks)}"
        if block and 'label' in block[0]:
            name = f"{func_name}{block[0]['label']}"
        elif len(named_blocks) == 0:
            name = f"{func_name}entry"
        named_blocks[name] = block
    return named_blocks


def get_predecessors(successors):
    ans = {}
    for name, _ in successors.items():
        ans[name] = []
    for name, ss in successors.items():
        for successor in ss:
            ans[successor].append(name)
    return ans


def make_func_cfg(func, func_name=''):
    cfg = OrderedDict()
    named_blocks = OrderedDict()

    func_blocks = name_blocks(func_name, make_blocks(func['instrs']))
    for name, block in func_blocks.items():
        named_blocks[name] = block

    for i, (name, block) in enumerate(named_blocks.items()):
        if block and 'op' in block[-1] and block[-1]['op'] in {'jmp', 'br'}:
            cfg[name] = [f"{func_name}{l}" for l in block[-1]['labels']]
        elif block and 'op' in block[-1] and block[-1]['op'] == 'ret':
            cfg[name] = []
        else:
            if i + 1 < len(named_blocks):
                cfg[name] = [list(named_blocks.keys())[i + 1]]
            else:
                cfg[name] = []

    return named_blocks, cfg


def add_cfg_prints(named_blocks):
    for name, block in named_blocks.items():
        name = name.lower()
        if len(name) > 10:
            print(f"Warning, truncating name {name} to {name[:10]}", file=sys.stderr)

        print_instrs = int_string.print_str(name[:10])
        idx = 0
        if block and 'label' in block[0]:
            idx = 1
        block.insert(idx, print_instrs[1])
        block.insert(idx, print_instrs[0])


def make_cfg(prog):
    cfg = OrderedDict()
    named_blocks = OrderedDict()
    for func in prog['functions']:
        func_name = f"{func['name']}." if len(prog['functions']) > 1 else ''
        func_blocks, func_cfg = make_func_cfg(func, func_name)
        for key, value in func_cfg.items():
            cfg[key] = value
        for key, value in func_blocks.items():
            named_blocks[key] = value

    return named_blocks, cfg


def annotate_program(prog):
    for func in prog['functions']:
        func_name = f"{func['name']}." if len(prog['functions']) > 1 else ''
        blocks, _ = make_func_cfg(func, func_name)
        add_cfg_prints(blocks)
        func['instrs'] = []
        for _, block in blocks.items():
            func['instrs'] += block
    return prog


def route_commands():
    prog = json.load(sys.stdin)
    assert len(sys.argv) in {1, 2}
    mode = 'cfg'
    if len(sys.argv) == 2:
        mode = sys.argv[1]
    if mode == 'cfg':
        print(make_cfg(prog)[1])
    elif mode == 'annotate':
        print(json.dumps(annotate_program(prog)))


if __name__ == "__main__":
    route_commands()
