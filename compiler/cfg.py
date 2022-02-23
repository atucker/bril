import json
import sys
from collections import OrderedDict

TERMINATORS = {'jmp', 'br', 'ret'}


def make_blocks(body):
    cur_block = []
    for instr in body:
        if 'op' in instr:
            cur_block.append(instr)
            if instr['op'] in TERMINATORS:
                if cur_block: yield cur_block
                cur_block = []
        elif 'label' in instr:
            if cur_block: yield cur_block
            cur_block = [instr]
        else:
            assert False, f"{instr} has neither an op nor label"
    if cur_block: yield cur_block


def name_blocks(func_name, blocks):
    named_blocks = OrderedDict()
    for block in blocks:
        name = f"{func_name}b{len(named_blocks)}"
        if 'label' in block[0]:
            name = f"{func_name}{block[0]['label']}"
        elif len(named_blocks) == 0:
            name = f"{func_name}entry"
        named_blocks[name] = block
    return named_blocks


def make_func_cfg(func, func_name=''):
    cfg = OrderedDict()
    named_blocks = OrderedDict()

    func_blocks = name_blocks(func_name, make_blocks(func['instrs']))
    for name, block in func_blocks.items():
        named_blocks[name] = block

    for i, (name, block) in enumerate(named_blocks.items()):
        if 'op' in block[-1] and block[-1]['op'] in {'jmp', 'br'}:
            cfg[name] = [f"{func_name}{l}" for l in block[-1]['labels']]
        elif 'op' in block[-1] and block[-1]['op'] == 'ret':
            cfg[name] = []
        else:
            if i + 1 < len(named_blocks):
                cfg[name] = [list(named_blocks.keys())[i + 1]]
            else:
                cfg[name] = []

    return cfg, named_blocks


def make_cfg(prog):
    cfg = OrderedDict()
    named_blocks = OrderedDict()
    for func in prog['functions']:
        func_name = f"{func['name']}." if len(prog['functions']) > 1 else ''
        func_cfg, func_blocks = make_func_cfg(func, func_name)
        for key, value in func_cfg.items():
            cfg[key] = value
        for key, value in func_blocks.items():
            named_blocks[key] = value

    return named_blocks, cfg


if __name__ == "__main__":
    print(make_cfg(json.load(sys.stdin))[1])
