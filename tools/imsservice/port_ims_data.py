#!/usr/bin/env python3
"""Port a newer Samsung imsservice's carrier data into this device's older one.

Usage: port_ims_data.py <old apktool dir> <new apktool dir> <out dir>

Takes res/raw imsprofile.json, globalsettings.json, mnomap.json,
localconfig.json, rcspolicy.json and res/xml dmconfig.xml,
userconfiguration.xml from the newer release (decoded with apktool) and writes
them to <out dir>/res, changed only where the old code needs it. Carriers the
newer data has a VoLTE profile for, the old code does not know
(com/sec/internal/ims/util/Mno) and that share their country with a known
carrier are added to a copy of Mno.smali in <out dir>/smali.

- Entries: the newer release's only. Carriers it dropped are dropped, entries
  of carriers still unknown to the old code are left out.
- Keys: the ones the old code reads, i.e. that appear as a string in its smali,
  maybe with a phone id appended (the settings classes read every key by
  name). localconfig.json is walked as
  a tree instead, so all of its keys are kept.
- Values: the newer ones, unless the old data has the same key with another
  JSON type; the old code reads them with typed Gson getters (getAsBoolean() ...).
- Object values and lists of objects are dropped from profiles and global
  settings: the old loaders only take plain values and lists of them, and
  GlobalSettingsRepoBase.save() crashes on anything else.
- Network types the old ImsProfile$NETWORK_TYPE cannot parse (e.g. "nr") are
  dropped: one unknown type makes the old loader discard the whole profile.
- IPsec auth_algo/enc_algo lists become the single keywords the old stack takes.
- mnomap.json's @BLOCKGC flags are dropped from carrier names.
- dmconfig.xml and userconfiguration.xml are copied: the old code reads the
  same dmconfig indexes and userconfiguration attributes.
"""

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsonc import load  # noqa: E402

# ImsProfile$NETWORK_TYPE.toString() values in the old code.
OLD_NETWORK_TYPES = {
    'unknown', 'gprs', 'edge', 'umts', 'cdma', 'evdo_0', 'evdo_a', '1xrtt',
    'hsdpa', 'hsupa', 'hspa', 'evdo_b', 'lte', 'ehrpd', 'hspa+', 'gsm',
    'tdscdma', 'wifi', 'all',
}

MNO = 'Lcom/sec/internal/ims/util/Mno;'
MNO_SMALI = 'smali/com/sec/internal/ims/util/Mno.smali'


def smali_strings(apk_dir):
    """Every string literal in the old code."""
    strings = set()
    for d in os.listdir(apk_dir):
        if not d.startswith('smali'):
            continue
        for root, _, files in os.walk(os.path.join(apk_dir, d)):
            for f in files:
                with open(os.path.join(root, f), encoding='utf-8') as s:
                    strings.update(re.findall(r'"((?:[^"\\]|\\.)*)"', s.read()))
    return strings


def json_type(v):
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, (int, float)):
        return 'number'
    return type(v).__name__


def types_by_path(obj, path='', out=None):
    """{key path: JSON types} over all entries; list indexes are left out."""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = path + '/' + k
            out.setdefault(p, set()).add(json_type(v))
            types_by_path(v, p, out)
    elif isinstance(obj, list):
        for x in obj:
            types_by_path(x, path, out)
    return out


def plain(v):
    if isinstance(v, dict):
        return False
    if isinstance(v, list):
        return all(not isinstance(x, (dict, list)) for x in v)
    return True


def read_by_code(key, strings):
    """A string of the old code, or one with a phone id appended
    ("volte_regi_icon_id" + 1)."""
    m = re.fullmatch(r'(.+?)\d+', key)
    return key in strings or bool(m and m.group(1) in strings)


def strip(obj, old_types, strings, path='', flat=False, keep_objects=()):
    """Keys the old code reads, values of the type it reads them as."""
    if isinstance(obj, list):
        return [strip(x, old_types, strings, path, flat, keep_objects) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        p = path + '/' + k
        if strings is not None and not read_by_code(k, strings):
            continue
        if p in old_types and json_type(v) not in old_types[p]:
            continue
        if flat and k not in keep_objects and not plain(v):
            continue
        out[k] = strip(v, old_types, strings, p)
    return out


def mno_of(entry):
    return str(entry['mnoname']).split(':')[0]


def parse_mnos(smali):
    """Return {name: (region, country)} for every Mno built in <clinit>."""
    mnos = {}
    for block in re.findall(r'new-instance v\d+, ' + re.escape(MNO) + r'(.*?)sput-object',
                            smali, re.S):
        strings = dict(re.findall(r'const-string(?:/jumbo)? (v\d+), "([^"]*)"', block))
        call = re.search(r'invoke-direct \{v\d+, (v\d+)', block)
        if not call or call.group(1) not in strings:
            continue
        region = re.search(r'Mno\$Region;->(\w+):', block)
        country = re.search(r'Mno\$Country;->(\w+):', block)
        mnos[strings[call.group(1)]] = (region and region.group(1),
                                        country and country.group(1))
    return mnos


def add_mnos(smali, added):
    fields = ''.join('.field public static PORTED_%d:%s\n\n' % (i, MNO)
                     for i in range(len(added)))
    code = ''
    for i, (name, (region, country)) in enumerate(sorted(added.items())):
        code += (
            '    new-instance v0, %s\n\n'
            '    sget-object v1, Lcom/sec/internal/ims/util/Mno$Region;->%s:'
            'Lcom/sec/internal/ims/util/Mno$Region;\n\n'
            '    sget-object v2, Lcom/sec/internal/ims/util/Mno$Country;->%s:'
            'Lcom/sec/internal/ims/util/Mno$Country;\n\n'
            '    const-string v4, "%s"\n\n'
            '    const-string v5, ""\n\n'
            '    invoke-direct {v0, v4, v5, v1, v2}, %s-><init>(Ljava/lang/String;'
            'Ljava/lang/String;Lcom/sec/internal/ims/util/Mno$Region;'
            'Lcom/sec/internal/ims/util/Mno$Country;)V\n\n'
            '    sput-object v0, %s->PORTED_%d:%s\n\n'
        ) % (MNO, region, country, name, MNO, MNO, i, MNO)
    start = smali.index('.method static constructor <clinit>()V')
    end = smali.index('.end method', start)
    ret = smali.rindex('    return-void', start, end)
    smali = smali[:ret] + code + smali[ret:]
    first_field = smali.index('.field ')
    return smali[:first_field] + fields + smali[first_field:]


def is_volte(profile):
    return profile.get('pdn') == 'ims' and any(
        'mmtel' in n.get('services', []) for n in profile.get('network', []))


def old_auth_algo(value):
    """New lists ("hmac-md5-96,hmac-sha-1-96,hmac-sha-2-...") to the old
    stack's single keywords; it puts other values into Security-Client as is,
    which the network rejects (400 Bad header field: security-client)."""
    algos = {a.strip() for a in value.split(',')} & {'hmac-md5-96', 'hmac-sha-1-96'}
    if len(algos) == 2:
        return 'both'
    return algos.pop() if algos else None


def old_enc_algo(value):
    """Same for encryption: none, aes-cbc, des-ede3-cbc, both (both ciphers)
    or all (also null). The old stack has no aes-gcm."""
    algos = {a.strip() for a in value.split(',')}
    null = bool(algos & {'null', 'none'})
    ciphers = algos & {'aes-cbc', 'des-ede3-cbc'}
    if null:
        return 'all' if ciphers else 'none'
    if len(ciphers) == 2:
        return 'both'
    return ciphers.pop() if ciphers else None


def convert_profile(profile):
    networks = []
    for net in profile.get('network', []):
        types = [t for t in net.get('type', '').split(',') if t.strip() in OLD_NETWORK_TYPES]
        if types:
            net = dict(net)
            net['type'] = ','.join(types)
            networks.append(net)
    if profile.get('network') and not networks:
        return None
    out = dict(profile)
    if 'network' in profile:
        out['network'] = networks
    for key, conv in (('auth_algo', old_auth_algo), ('enc_algo', old_enc_algo)):
        if isinstance(out.get(key), str):
            value = conv(out[key])
            if value is None:
                del out[key]
            else:
                out[key] = value
    return out


def write_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def main(old_dir, new_dir, out_dir):
    strings = smali_strings(old_dir)
    smali = open(os.path.join(old_dir, MNO_SMALI)).read()
    old_mnos = parse_mnos(smali)

    def raw(d, name):
        return load(os.path.join(d, 'res/raw', name))

    def old_types(name):
        return types_by_path(raw(old_dir, name))

    new_prof = raw(new_dir, 'imsprofile.json')['profile']

    # Carriers to add: VoLTE profile in the new data, unknown to the old code,
    # and a known carrier in the same country to copy region/country from.
    by_suffix = {}
    for name, (region, country) in old_mnos.items():
        if region and country and '_' in name:
            by_suffix.setdefault(name.rsplit('_', 1)[1], (region, country))
    added = {}
    for p in new_prof:
        name = mno_of(p)
        if name in old_mnos or name in added or not is_volte(p) or '_' not in name:
            continue
        if not re.fullmatch(r'[A-Za-z0-9_+&.-]+', name) or 'LAB' in name.upper():
            continue
        rc = by_suffix.get(name.rsplit('_', 1)[1])
        if rc:
            added[name] = rc
    known = set(old_mnos) | set(added)

    os.makedirs(os.path.join(out_dir, os.path.dirname(MNO_SMALI)), exist_ok=True)
    with open(os.path.join(out_dir, MNO_SMALI), 'w') as f:
        f.write(add_mnos(smali, added) if added else smali)
    out_raw = os.path.join(out_dir, 'res/raw')
    out_xml = os.path.join(out_dir, 'res/xml')
    os.makedirs(out_raw, exist_ok=True)
    os.makedirs(out_xml, exist_ok=True)

    # imsprofile.json
    types = old_types('imsprofile.json')
    profiles = []
    dropped = []
    for p in new_prof:
        if mno_of(p) not in known:
            continue
        conv = convert_profile(p)
        if conv is None:
            dropped.append(p['name'])
            continue
        profiles.append(strip(conv, types, strings, '/profile', flat=True,
                              keep_objects=('network',)))
    write_json({'profile': profiles}, os.path.join(out_raw, 'imsprofile.json'))

    # globalsettings.json
    types = old_types('globalsettings.json')
    gs = {}
    for k, v in raw(new_dir, 'globalsettings.json').items():
        if k not in strings:
            continue
        if k == 'globalsetting':
            v = [e for e in v if mno_of(e) in known]
        gs[k] = strip(v, types, strings, '/' + k, flat=True)
    write_json(gs, os.path.join(out_raw, 'globalsettings.json'))

    # mnomap.json. "Name@BLOCKGC" turns Google's Guest Cloud RCS off for a
    # carrier; this code has no Guest Cloud and takes the whole string as the
    # Mno name, so the flag is dropped.
    new_map = raw(new_dir, 'mnomap.json')
    for m in new_map['mnomap']:
        m['mnoname'] = str(m['mnoname']).split('@')[0]
    new_map['mnomap'] = [m for m in new_map['mnomap']
                         if mno_of(m) in known | {'DEFAULT', 'LABSIM'}]
    mnomap = strip(new_map, old_types('mnomap.json'), strings)
    write_json(mnomap, os.path.join(out_raw, 'mnomap.json'))

    # localconfig.json, rcspolicy.json
    write_json(strip(raw(new_dir, 'localconfig.json'), old_types('localconfig.json'), None),
               os.path.join(out_raw, 'localconfig.json'))
    write_json(strip(raw(new_dir, 'rcspolicy.json'), old_types('rcspolicy.json'), strings),
               os.path.join(out_raw, 'rcspolicy.json'))

    for name in ('dmconfig.xml', 'userconfiguration.xml'):
        shutil.copyfile(os.path.join(new_dir, 'res/xml', name), os.path.join(out_xml, name))

    print('old code carriers: %d, added: %d (%s)' % (
        len(old_mnos), len(added), ', '.join(sorted(added))))
    print('profiles: %d, %d dropped (no usable network)' % (len(profiles), len(dropped)))
    print('globalsettings: %d carriers, mnomap: %d entries' % (
        len(gs['globalsetting']), len(mnomap['mnomap'])))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
