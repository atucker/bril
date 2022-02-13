import json
import sys
from collections import defaultdict


def count_consts():
    prog = json.load(sys.stdin)
    consts = defaultdict(lambda : 0)

    for func in prog['functions']:
        for instr in func['instrs']:
            if 'op' in instr and instr['op'] == 'const':
                consts[instr['value']] += 1

    total = 0
    for key, count in consts.items():
        print(f"{key} was used {count} times")
        total += count
    print(f"{total} constants were used")


if __name__ == '__main__':
    count_consts()