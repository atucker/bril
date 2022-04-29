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
MAPPING = {}
for line in GRAMMAR.split('\n'):
    if '->' in line:
        if len(line.split(' "')) == 2:
            symbol, rest = line.split(' "')[1].split('" ')
            word = rest.split('-> ')[1]
            MAPPING[word] = symbol


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

    return substitute_solution(sketch_expr, sketch_vars, model)


class Node:
    def __init__(self, tree, depth):
        self.tree = tree
        self.depth = depth

    @property
    def identifier(self):
        return str(self.tree)

    def __str__(self):
        return self.identifier


class Forest:
    def __init__(self, init_to_depth=5):
        self.ops = ('shl', 'shr')
        self.commutative_ops = ('or', 'and', 'sub', 'add')

        self.n_holes = 0
        self.seen = set()
        self.nodes = {}
        self.frontier = []

        self.x_var = Node(lark.Tree('var', [lark.Token('CNAME', 'x')]), 0)
        self.add(self.x_var)

    def new_hole(self):
        self.n_holes += 1
        name = f"h{self.n_holes}"
        return Node(lark.Tree('var', [lark.Token('CNAME', name)]), 0)

    def add(self, node):
        if node.depth not in self.nodes:
            self.nodes[node.depth] = []

        if node.identifier not in self.seen:
            self.seen.add(node.identifier)
            self.nodes[node.depth].append(node)
            self.frontier.append(node)

    def add_ops(self, node1, node2):
        depth = max(node1.depth, node2.depth) + 1
        for op in self.ops:
            self.add(Node(lark.Tree(op, [node1.tree, node2.tree]), depth))
            self.add(Node(lark.Tree(op, [node1.tree, node2.tree]), depth))
        for op in self.commutative_ops:
            # canonicalize representation
            if node1.identifier < node2.identifier:
                self.add(Node(lark.Tree(op, [node1.tree, node2.tree]), depth))
            else:
                self.add(Node(lark.Tree(op, [node2.tree, node1.tree]), depth))

    def add_leaf(self, node):
        self.add_ops(node, self.x_var)
        self.add_ops(node, self.new_hole())

    def expand_top(self, node):
        for d in [0] + list(range(node.depth)):
            if d == 0:
                self.add_ops(node, self.x_var)
                self.add_ops(node, self.new_hole())
            else:
                for node2 in self.nodes[d]:
                    self.add_ops(node, node2)

    def search(self, expand_fn, spec_expr, spec_vars, stop_depth=None):
        max_depth = 0
        i = 0
        for node in self.frontier:
            i += 1
            expand_fn(node)

            sketch_expr, sketch_vars = z3_interp(node.tree, spec_vars)

            plain_vars = dict(
                (key, value) for key, value in sketch_vars.items()
                if not key.startswith('h')
            )
            goal = z3.ForAll(list(plain_vars.values()), spec_expr == sketch_expr, )
            model = solve(goal)

            if model is not None:
                print("Done")
                return node, sketch_expr, model

            if i % 100 == 0:
                print(f"Evaluated {i} trees")
            if node.depth > max_depth:
                print(f"Entering depth {node.depth}")
                max_depth = node.depth
            if node.depth >= stop_depth:
                return None


def pretty_print(tree, lookup=None):
    op = tree.data
    if op == 'var':
        varname = str(tree.children[0])
        if lookup and varname in lookup:
            return lookup[varname]
        else:
            return varname
    else:
        return f"({pretty_print(tree.children[0])} {MAPPING[op]} {pretty_print(tree.children[1])})"


def force_sketches(spec_expr, spec_vars):
    forest = Forest()
    ans = forest.search(forest.add_leaf, spec_expr, spec_vars, stop_depth=4)
    if ans is not None:
        return ans
    else:
        # Restart the search, and know that we'll skip over everything we already tried since it was seen
        # Note that everything already used is in the node set used to expand the top, so they'll get spliced in
        forest.frontier = []
        forest.add(forest.x_var)
        forest.add(forest.new_hole())
        return forest.search(forest.expand_top, spec_expr, spec_vars, stop_depth=5)


if __name__ == "__main__":
    spec = sys.stdin.readline()
    sketch = sys.stdin.readline()
    ans = synthesize(spec, sketch)
