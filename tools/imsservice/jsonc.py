import json
import re

BACKSLASH = chr(92)


def strip_comments(s):
    """Drop // and /* */ comments outside strings, and trailing commas."""
    out = []
    i = 0
    n = len(s)
    in_str = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if c == BACKSLASH:
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif s.startswith('//', i):
            j = s.find('\n', i)
            i = n if j < 0 else j
        elif s.startswith('/*', i):
            j = s.find('*/', i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return re.sub(r',(\s*[}\]])', r'\1', ''.join(out))


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.loads(strip_comments(f.read()))
