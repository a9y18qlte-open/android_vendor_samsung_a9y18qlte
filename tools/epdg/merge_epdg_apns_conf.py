#!/usr/bin/env python3
"""Update this device's epdg_apns_conf.xml from a newer Samsung release.

Usage: merge_epdg_apns_conf.py <ours> <newer> <output>

The file holds EpdgService's per-carrier ePDG data: <vowifi> (default Wi-Fi
Calling switches), <apn> (IKE/IPsec profile per APN) and <settings> (handover
thresholds, ePDG address, ...), keyed by mnoname (and connname/apnname for
<apn>).

Newer releases only write what differs from the defaults on the section tags
(<iwlansettings ...> for <apn>, <epdgsettings ...> for <settings>); this
EpdgService expects every attribute on every entry. So each newer entry is first
expanded with its section's defaults, then:

- An entry both files have takes the newer values; attributes only ours has are
  kept.
- An entry only the newer file has is added, with the attributes only this
  EpdgService knows taken from our default entry of that kind.
- An entry only ours has is kept.
- Our section tag attributes take the newer section's values.

Where the newer file lists an entry twice, the first one is used.
"""

import re
import sys

SECTIONS = {'apn': 'iwlansettings', 'settings': 'epdgsettings', 'vowifi': 'vowifisettings'}
ELEMENT = re.compile(r'((?:[ \t]*<!--[^\n]*-->\n)?)([ \t]*)<(apn|settings|vowifi)\b(.*?)/>\n?', re.S)
ATTR = re.compile(r'([\w:]+)\s*=\s*"([^"]*)"')


def attrs(text):
    return dict(ATTR.findall(text))


def key(tag, a):
    if tag == 'apn':
        return (tag, a.get('mnoname'), a.get('connname'), a.get('apnname'))
    return (tag, a.get('mnoname'))


def section_defaults(text, section):
    m = re.search(r'<%s\b([^>]*)>' % section, text)
    return attrs(m.group(1)) if m else {}


def element(tag, a, indent='        ', comment=''):
    items = list(a.items())
    lines = ['%s<%s %s="%s"' % (indent, tag, items[0][0], items[0][1])]
    lines += ['%s    %s="%s"' % (indent, k, v) for k, v in items[1:]]
    lines.append('%s/>' % indent)
    return comment + '\n'.join(lines) + '\n'


def main(ours_path, newer_path, output):
    ours = open(ours_path).read()
    newer = open(newer_path).read()

    defaults = {tag: section_defaults(newer, s) for tag, s in SECTIONS.items()}
    new = {}
    order = []
    for m in ELEMENT.finditer(newer):
        tag = m.group(3)
        a = dict(defaults[tag])
        a.update(attrs(m.group(4)))
        k = key(tag, a)
        if k in new:
            continue
        new[k] = (a, m.group(1))
        order.append(k)

    our_defaults = {}
    for m in ELEMENT.finditer(ours):
        a = attrs(m.group(4))
        if a.get('mnoname') == 'default':
            our_defaults.setdefault(m.group(3), a)

    seen = set()
    counts = {'updated': 0, 'added': 0, 'kept': 0}

    def update(m):
        tag = m.group(3)
        a = attrs(m.group(4))
        k = key(tag, a)
        if k not in new:
            counts['kept'] += 1
            return m.group(0)
        seen.add(k)
        merged = dict(a)
        merged.update(new[k][0])
        if merged != a:
            counts['updated'] += 1
        return m.group(1) + element(tag, merged, m.group(2))

    out = ELEMENT.sub(update, ours)

    for tag, section in SECTIONS.items():
        added = ''
        for k in order:
            if k[0] != tag or k in seen:
                continue
            a = {x: v for x, v in our_defaults.get(tag, {}).items() if x != 'mnoname'}
            a.update(new[k][0])
            a = dict([('mnoname', a.pop('mnoname'))] + list(a.items()))
            added += element(tag, a, comment=new[k][1])
            counts['added'] += 1
        close = '    </%s>' % section
        assert out.count(close) == 1, close
        out = out.replace(close, added + close)

        # Section tag attributes (defaults) take the newer values too.
        m = re.search(r'<%s\b([^>]*)>' % section, out)
        if m and m.group(1).strip():
            sa = attrs(m.group(1))
            sa.update(section_defaults(newer, section))
            body = ''.join('\n            %s="%s"' % i for i in sa.items())
            out = out[:m.start()] + '<%s%s>' % (section, body) + out[m.end():]

    open(output, 'w').write(out)
    print('%(updated)d entries updated, %(added)d added, %(kept)d kept as they were' % counts)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
