"""
This is an extremely lazy way to add strings to bril.

Basically the core idea is that we don't actually need to get bril to print out
strings, we just need bril to print out integers that a different program can
turn into strings.

This library makes no promises to work, but is hopefully helpful for debugging.

Bril uses 64 bit integers. This is enough for us to fit 10 characters if we only
have 6 bits/character, achievable by using half of the ascii chart.

Each string starts with 1010, then is right padded with SPACE.

Currently there is no support for >10 character strings, though plausibly a
decent way of handling them would just be to say that if you want more
characters, end your string with DEL and then we'll keep going.
"""


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
    bits = bits[3:]
    assert len(bits) == 60
    ans = ""
    while bits:
        ans += bits_to_char(bits[:6])
        bits = bits[6:]
    return ans.strip()
