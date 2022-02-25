"""
This is an extremely lazy way to add strings to bril.

Basically the core idea is that we don't actually need to get bril to print out
strings, we just need bril to print out integers that a different program can
turn into strings.

This library makes no promises to work, but is hopefully helpful for debugging.

Bril uses 64 bit integers. This is enough for us to fit 10 characters if we only
have 6 bits/character, achievable by using half of the ascii chart, specifically
SPACE through ? and ` through DEL. This gives us numbers, lowercase, and some
punctuation.

Each string starts with 0101, then is right padded with SPACE.

Currently there is no support for >10 character strings, though plausibly a
decent way of handling them would just be to say that if you want more
characters, end your string with DEL and then we'll keep going.
"""

import sys


def char_to_bits(c):
    i = ord(c)
    if 32 <= i <= 63:
        i -= 32
    elif 96 <= i <= 127:
        i -= 64
    else:
        assert False, f"Invalid character {c}"
    b = bin(i)[2:]
    b = "0" * (6 - len(b)) + b
    return b


def str_to_bits(s):
    assert len(s) <= 10, "String is too long, max length is 10"
    s += " " * (10 - len(s))
    bits = str("".join([char_to_bits(c) for c in s]))
    bits = "0101" + bits
    assert len(bits) == 64
    return bits


def str_to_int(s):
    return int(str_to_bits(s), base=2)


def bits_to_char(b):
    i = int(b, base=2)
    if i < 32:
        i += 32
    elif i >= 32:
        i += 64
    return chr(i)


def int_to_str(i):
    bits = bin(i)[2:]
    bits = '0' * (64 - len(bits)) + bits
    assert len(bits) == 64
    assert bits[:4] == '0101'
    bits = bits[4:]
    assert len(bits) == 60
    ans = ""
    while bits:
        ans += bits_to_char(bits[:6])
        bits = bits[6:]
    return ans.strip()


def print_str(s):
    i = str_to_int(s)
    return [
        {"dest": "string", "op": "const", "type": "int", "value": i},
        {"op": "print", "args": ["string"]}
    ]


if __name__ == "__main__":
    assert len(sys.argv) in {1, 2}

    mode = "decode"
    if len(sys.argv) == 2:
        mode = sys.argv[1]

    # If you're given some lines try to turn them into strings
    for line in sys.stdin:
        line = line.strip()
        try:
            if mode == 'decode':
                line = int_to_str(int(line))
            elif mode == 'encode':
                line = str_to_int(line.strip(line))
            elif mode == 'roundtrip':
                line = int_to_str(str_to_int(line))
            else:
                raise NotImplementedError()
        except AssertionError:
            pass
        except ValueError:
            pass
        print(line.strip())