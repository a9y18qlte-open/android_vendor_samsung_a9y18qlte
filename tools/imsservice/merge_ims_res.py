#!/usr/bin/env python3
"""Update imsservice's remaining config resources from a newer Samsung release.

Usage: merge_ims_res.py <ours res dir> <newer res dir> <out res dir>

Merges raw/localconfig.json, raw/rcspolicy.json, xml/dmconfig.xml and
xml/userconfiguration.xml (decoded with apktool) and writes them to <out res
dir>. The carrier data (imsprofile.json, globalsettings.json, mnomap.json) is
ported by port_ims_data.py; resources only newer code reads are left out.

- A value both releases have takes the newer one, unless its JSON type changed:
  this code reads them with typed Gson getters (getAsBoolean() ...).
- Keys only one release has are kept; the code reads keys by name and ignores
  the rest.
- localconfig.json and dmconfig.xml group Samsung sales codes ("att,aio,app",
  name="VZW,CCT,TFN"), and newer releases regroup them. They are merged per sales
  code and regrouped: codes with the same merged values share an entry again.
- rcspolicy.json's rcs_policy list is merged per policy_name, userconfiguration.xml
  per configuration name.

The XML files are stored compiled: compile them with aapt2 (aapt2 compile, then
aapt2 link against android.jar with any manifest; aapt2 reproduces the stock
files byte for byte) and replace the four entries in imsservice.apk.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsonc import load  # noqa: E402


def same_type(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return True
    return type(a) is type(b)


def merge(ours, newer):
    if isinstance(ours, dict) and isinstance(newer, dict):
        out = dict(ours)
        for k, v in newer.items():
            out[k] = merge(ours[k], v) if k in ours else v
        return out
    return newer if same_type(ours, newer) else ours


def by_code(groups):
    """{"a,b": x} -> {"a": x, "b": x}, keeping the order of first appearance."""
    out = {}
    for codes, value in groups:
        for code in codes.split(','):
            out[code.strip()] = value
    return out


def regroup(codes):
    """{"a": x, "b": x, "c": y} -> [("a,b", x), ("c", y)]"""
    out = []
    for code, value in codes.items():
        for group in out:
            if group[1] == value:
                group[0].append(code)
                break
        else:
            out.append(([code], value))
    return [(','.join(c), v) for c, v in out]


def merge_codes(ours, newer, merge_value):
    a, b = by_code(ours), by_code(newer)
    merged = {c: merge_value(a[c], b[c]) if c in b else a[c] for c in a}
    merged.update((c, v) for c, v in b.items() if c not in a)
    return regroup(merged)


def merge_localconfig(ours, newer):
    return dict(merge_codes(ours.items(), newer.items(), merge))


def merge_rcspolicy(ours, newer):
    out = merge({k: v for k, v in ours.items() if k != 'rcs_policy'},
                {k: v for k, v in newer.items() if k != 'rcs_policy'})
    policies = {p['policy_name']: p for p in ours['rcs_policy']}
    for p in newer['rcs_policy']:
        name = p['policy_name']
        policies[name] = merge(policies[name], p) if name in policies else p
    out['rcs_policy'] = list(policies.values())
    return out


def dm_items(conf):
    return {(i.get('key'), i.get('type')): i.text for i in conf.findall('item')}


def merge_dmconfig(ours, newer):
    def groups(root):
        return [(c.get('name'), dm_items(c)) for c in root.findall('configuration')]

    def merge_items(a, b):
        # The same key with a different type attribute is the same setting.
        out = {k: v for k, v in a.items() if k[0] not in {x[0] for x in b}}
        out.update(b)
        return out

    root = ET.Element('configurations')
    for name, items in merge_codes(groups(ours), groups(newer), merge_items):
        conf = ET.SubElement(root, 'configuration', name=name)
        for (key, type_), text in items.items():
            item = ET.SubElement(conf, 'item', key=key)
            if type_:
                item.set('type', type_)
            item.text = text
    return root


def merge_userconfiguration(ours, newer):
    confs = {c.get('name'): dict(c.attrib) for c in ours.findall('configuration')}
    for c in newer.findall('configuration'):
        confs[c.get('name')] = {**confs.get(c.get('name'), {}), **c.attrib}
    root = ET.Element('configurations')
    for attrib in confs.values():
        ET.SubElement(root, 'configuration', attrib)
    return root


def write_xml(root, path):
    ET.indent(root)
    with open(path, 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(ET.tostring(root, encoding='utf-8'))
        f.write(b'\n')


def main(ours, newer, out):
    for d in ('raw', 'xml'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    for name, fn in (('localconfig.json', merge_localconfig),
                     ('rcspolicy.json', merge_rcspolicy)):
        merged = fn(load(os.path.join(ours, 'raw', name)), load(os.path.join(newer, 'raw', name)))
        with open(os.path.join(out, 'raw', name), 'w') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write('\n')
    for name, fn in (('dmconfig.xml', merge_dmconfig),
                     ('userconfiguration.xml', merge_userconfiguration)):
        merged = fn(ET.parse(os.path.join(ours, 'xml', name)).getroot(),
                    ET.parse(os.path.join(newer, 'xml', name)).getroot())
        write_xml(merged, os.path.join(out, 'xml', name))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
