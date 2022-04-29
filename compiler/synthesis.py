import z3
import lark
import sys

GRAMMAR = """
?start: sum
  | sum "?" sum ":" sum -> if

?sum: term
  | sum "+" term        -> add
  | sum "-" term        -> sub
  | sum "|" term        -> or
  | sum "&" term        -> and   

?term: item
  | term "*"  item      -> mul
  | term "/"  item      -> div
  | term ">>" item      -> shr
  | term "<<" item      -> shl

?item: NUMBER           -> num
  | "-" item            -> neg
  | CNAME               -> var
  | "(" start ")"


%import common.NUMBER
%import common.WS
%import common.CNAME
%ignore WS
""".strip()
PARSER = lark.Lark(GRAMMAR)


def solve(phi):
    solver = z3.Solver()
    solver.add(phi)
    solver.check()
    try:
        return solver.model()
    except z3.Z3Exception:
        return None


def merge_dicts(d1, d2):
    new = dict(**d1)
    for key, value in d2.items():
        if key not in new:
            new[key] = value
        else:
            assert value == d1[key]
    return new


def z3_interp(tree, lookup=None, readonly=False):
    op = tree.data
    if op in ('add', 'sub', 'mul', 'div', 'shl', 'shr', 'or', 'and'):
        lhs, lhvars = z3_interp(tree.children[0], lookup)
        rhs, rhvars = z3_interp(tree.children[1], lookup)
        if op == 'add':
            return lhs + rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'sub':
            return lhs - rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'mul':
            return lhs * rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'div':
            return lhs / rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'shl':
            return lhs << rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'shr':
            return lhs >> rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'or':
            return lhs | rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
        elif op == 'and':
            return lhs & rhs, lookup if readonly else merge_dicts(lhvars, rhvars)
    elif op == 'neg':
        sub, vs = z3_interp(tree.children[0], lookup)
        return -sub, vs
    elif op == 'num':
        if not readonly:
            return int(tree.children[0]), dict(**lookup) if lookup else {}
        else:
            return int(tree.children[0]), lookup
    elif op == 'var':
        name = tree.children[0]
        var = lookup[name] if lookup and name in lookup else z3.BitVec(name, 64)
        return var, lookup if readonly else {name: var}
    elif op == 'if':
        cond, cvars = z3_interp(tree.children[0], lookup)
        true, tvars = z3_interp(tree.children[1], lookup)
        false, fvars = z3_interp(tree.children[2], lookup)
        expr = (cond != 0) * true + (cond == 0) * false
        return expr, lookup if readonly else merge_dicts(cvars, merge_dicts(tvars, fvars))
    assert False

def interp(tree):
    output, vars = z3_interp(tree)
    return output


def substitute_solution(sketch_expr, sketch_vars, model):
    variables = {}
    for key, item in sketch_vars.items():
        variables[key] = model.eval(item)
    return z3_interp(sketch_expr, variables)[0]


def synthesize(spec, sketch):
    spec_tree = PARSER.parse(spec)
    sketch_tree = PARSER.parse(sketch)
    spec_expr, spec_vars = z3_interp(spec_tree)
    sketch_expr, sketch_vars = z3_interp(sketch_tree, spec_vars)

    plain_vars = dict(
        (key, value) for key, value in sketch_vars.items()
        if not key.startswith('h')
    )
    goal = z3.ForAll(
        list(plain_vars.values()),  # For every valuation of variables...
        spec_expr == sketch_expr,  # ...the two expressions produce equal results.
    )

    model = solve(goal)
    if model is None:
        return None
    for key, item in sketch_vars.items():
        plain_vars[key] = model.eval(item)
    return z3_interp(sketch_expr, plain_vars)[0]


if __name__ == "__main__":
    spec = sys.stdin.readline()
    sketch = sys.stdin.readline()
    ans = synthesize(spec, sketch)

