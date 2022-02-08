import json
import sys
from collections import defaultdict

COMMUTATIVE = {'add', 'mul'}
var_to_idx = dict()
value_to_idx = dict()
table = [] # idx is #, then contains tuples of (value, home)


def insert_var(var, value):
    # If it's not already in the table, add it
    if value not in value_to_idx:
        idx = len(table)
        table.append((value, var))
        value_to_idx[value] = idx

    # always map the variable to the index
    var_to_idx[var] = value_to_idx[value]


def idx_to_home_var(idx):
    return table[idx][1]


def idx_to_value(idx):
    return table[idx][0]


def count_variables(func):
    ans = defaultdict(lambda : 0)
    for instr in func['instrs']:
        if 'dest' in instr:
            ans[instr['dest']] += 1
    return ans


def make_value(instr):
    op = instr['op']

    # Replace every arg with its variable index
    if 'args' in instr:
        args = []
        for arg in instr['args']:
            assert arg in var_to_idx, f"Variable {arg} not previously defined"
            args.append(var_to_idx[arg])
    elif 'value' in instr:
        args = [instr['value']]
    else:
        assert False, f"idk what to do with {instr}"

    if op == 'id':
        assert len(args) == 1
        return idx_to_value(args[0])

    # Transform args to canonical ordering if op is commutative
    if op in COMMUTATIVE:
        args = sorted(args)

    return op, *args


def maybe_rename_dest_store_old(var_counts, dest, value):
    var_counts[dest] -= 1
    if var_counts[dest] > 0:
        # Insert old value so we know what it was when we try to use it
        insert_var(dest, value)
        dest = f'_{dest}_{var_counts[dest] + 1}'
        assert dest not in var_counts, \
            f"Alas, {dest} is not a unique variable name"
    return dest


def make_lookup(dest, type, value):
    if value[0] == 'const':
        return {
            'dest': dest,
            'op': 'const',
            'value': value[1],
            'type': type
        }
    else:
        return {
            'dest': dest,
            'op': 'id',
            'args': [idx_to_home_var(value_to_idx[value])],
            'type': type
        }


def do_lvn():
    prog = json.load(sys.stdin)
    # does this happen within a function or across a program?
    for func in prog['functions']:
        if 'args' in func:
            for arg in func['args']:
                insert_var(arg['name'], arg['name'])

        var_counts = count_variables(func)
        new_instrs = []
        for instr in func['instrs']:
            for key in instr.keys():
                assert key in {'op', 'dest', 'args', 'type', 'funcs', 'value', 'label', 'labels'}, \
                   f"Unrecognized instruction key {key}, code might not work..."

            if 'op' in instr and instr['op'] not in {'jmp', 'br'}:
                value = make_value(instr)

                if 'dest' in instr:
                    dest = instr['dest']

                    # If the value is already there, replace instruction with lookup
                    if value in value_to_idx:
                        instr = make_lookup(dest, instr['type'], value)
                        value = make_value(instr)
                        print(instr, file=sys.stderr)

                    # If variable is going to be overwritten again...
                    dest = maybe_rename_dest_store_old(var_counts, dest, value)

                    # Put the value in the destination
                    insert_var(dest, value)
                    instr['dest'] = dest

                if 'args' in instr:
                    new_args = [idx_to_home_var(idx) for idx in value[1:]]
                    # Replace arg indices with their home variables
                    instr['args'] = new_args
                elif 'value' in instr:
                    instr['value'] = value[1]
                new_instrs.append(instr)

            else: # if its not an op, then just put it back unchanged
                new_instrs.append(instr)

        func['instrs'] = new_instrs
    print(json.dumps(prog))


if __name__ == '__main__':
    do_lvn()