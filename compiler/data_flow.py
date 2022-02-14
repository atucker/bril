import json
import sys

"""
in[entry] = init
out[*] = init

worklist = all blocks
while worklist is not empty:
    b = pick any block from worklist
    in[b] = merge(out[p] for every predecessor p of b)
    out[b] = transfer(b, in[b])
    if out[b] changed:
        worklist += successors of b
"""


def do_liveness():
    prog = json.load(sys.stdin)
    

if __name__ == "__main__":
    do_liveness()