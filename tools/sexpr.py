"""Minimal S-expression reader/writer for KiCad files.

Parsed form: a list is a Python list, an atom is a Sym (bare word) or a str
(quoted string). Numbers stay as Sym so they round-trip exactly.
"""


class Sym(str):
    """Bare (unquoted) atom."""


def parse(text):
    """Parse one S-expression document, return the top-level list."""
    pos = 0
    n = len(text)
    stack = [[]]
    while pos < n:
        c = text[pos]
        if c in ' \t\r\n':
            pos += 1
        elif c == '(':
            stack.append([])
            pos += 1
        elif c == ')':
            done = stack.pop()
            stack[-1].append(done)
            pos += 1
        elif c == '"':
            pos += 1
            buf = []
            while text[pos] != '"':
                if text[pos] == '\\':
                    pos += 1
                    buf.append({'n': '\n', 't': '\t'}.get(text[pos], text[pos]))
                else:
                    buf.append(text[pos])
                pos += 1
            pos += 1
            stack[-1].append(''.join(buf))
        else:
            start = pos
            while pos < n and text[pos] not in ' \t\r\n()':
                pos += 1
            stack[-1].append(Sym(text[start:pos]))
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError('unbalanced S-expression')
    return stack[0][0]


def _atom(a):
    if isinstance(a, Sym):
        return str(a)
    if isinstance(a, bool):
        return 'yes' if a else 'no'
    if isinstance(a, (int, float)):
        return fmt_num(a)
    s = a.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return f'"{s}"'


def fmt_num(v):
    """KiCad number format: up to 4 decimals, no trailing zeros."""
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def dump(node, indent=0):
    """Write in KiCad's style: one list per line, tabs, short lists inline."""
    if not isinstance(node, list):
        return _atom(node)
    tab = '\t' * indent
    if not any(isinstance(x, list) for x in node):
        return tab + '(' + ' '.join(_atom(x) for x in node) + ')'
    head = []
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(_atom(node[i]))
        i += 1
    lines = [tab + '(' + ' '.join(head)]
    for x in node[i:]:
        if isinstance(x, list):
            lines.append(dump(x, indent + 1))
        else:
            lines.append('\t' * (indent + 1) + _atom(x))
    lines.append(tab + ')')
    return '\n'.join(lines)


def find(node, key):
    """First child list whose head is key, or None."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
