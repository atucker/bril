import json
import sys
import cfg
import dominators


def get_defs(named_blocks):
    defs = {}
    for name, block in named_blocks.items():
        for instr in block:
            if 'dest' in instr:
                var = instr['dest']
                if var not in defs:
                    defs[var] = set()
                defs[var] |= {block}
    return defs


def to_ssa(prog):
    """
    Converting to SSA

    To convert to SSA, we want to insert ϕ-nodes whenever there are distinct paths containing distinct definitions of a variable. We don’t need ϕ-nodes in places that are dominated by a definition of the variable. So what’s a way to know when control reachable from a definition is not dominated by that definition? The dominance frontier!

    We do it in two steps. First, insert ϕ-nodes:

    for v in vars:
       for d in Defs[v]:  # Blocks where v is assigned.
         for block in DF[d]:  # Dominance frontier.
           Add a ϕ-node to block,
             unless we have done so already.
           Add block to Defs[v] (because it now writes to v!),
             unless it's already in there.
    Then, rename variables:

    stack[v] is a stack of variable names (for every variable v)

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
    blocks, successors = cfg.make_cfg(prog)
    dom = dominators.make_dominators(successors)
    frontier = dominators.dominance_frontier(successors, dom)




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
        print(to_ssa(prog))
    elif mode == 'from':
        print(from_ssa(prog))
    else:
        raise NotImplementedError


if __name__ == "__main__":
    route_commands()