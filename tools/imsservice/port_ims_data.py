#!/usr/bin/env python3
"""Port newer Samsung IMS carrier data into this device's older imsservice.

Usage: port_ims_data.py <old raw dir> <new raw dir> <old smali dir> <out raw dir>

Reads imsprofile.json, mnomap.json and globalsettings.json from both res/raw
directories and writes merged copies to <out raw dir>. Carriers the new data
has but the old code does not know (com/sec/internal/ims/util/Mno) are added
to Mno.smali in <old smali dir> when they have a VoLTE profile and the old code
already knows a carrier in the same country.

Rules:
- A carrier known to the old code takes its profiles, global settings and
  mnomap entries from the new data; carriers only the old data has keep theirs.
- Network types the old ImsProfile$NETWORK_TYPE cannot parse (e.g. "nr") are
  dropped: one unknown type makes the old loader discard the whole profile.
- Keys the old entry had and the new one dropped are carried over.
"""

import json
import os
import re
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


def flat(entry, keep=()):
    """Drop object values and lists of objects (newer keys such as
    simmobility_update): the old loaders only take plain values and lists of
    them, and GlobalSettingsRepoBase.save() crashes on anything else."""
    def ok(v):
        if isinstance(v, dict):
            return False
        if isinstance(v, list):
            return all(not isinstance(x, (dict, list)) for x in v)
        return True
    return {k: v for k, v in entry.items() if k in keep or ok(v)}


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


def convert_profile(profile, old):
    networks = []
    for net in profile.get('network', []):
        types = [t for t in net.get('type', '').split(',') if t.strip() in OLD_NETWORK_TYPES]
        if types:
            net = dict(net)
            net['type'] = ','.join(types)
            networks.append(net)
    if profile.get('network') and not networks:
        return None
    out = flat(profile, keep=('network',))
    if 'network' in profile:
        out['network'] = networks
    out.pop('$schema', None)
    for key, conv in (('auth_algo', old_auth_algo), ('enc_algo', old_enc_algo)):
        if isinstance(out.get(key), str):
            value = conv(out[key])
            if value is None:
                del out[key]
            else:
                out[key] = value
    if old:
        for k, v in old.items():
            out.setdefault(k, v)
    return out


def merge_by_mno(old_entries, new_entries, known, carry_keys=True):
    """New entries for known carriers, old entries for carriers new lacks."""
    new_mnos = {str(e['mnoname']).split(':')[0] for e in new_entries}
    old_by_mno = {str(e['mnoname']): e for e in old_entries}
    out = []
    for e in new_entries:
        if str(e['mnoname']).split(':')[0] not in known:
            continue
        old = old_by_mno.get(str(e['mnoname'])) if carry_keys else None
        merged = flat(e)
        if old:
            for k, v in old.items():
                merged.setdefault(k, v)
        out.append(merged)
    out += [e for e in old_entries if str(e['mnoname']).split(':')[0] not in new_mnos]
    return out


def main(old_raw, new_raw, smali_dir, out_raw):
    mno_path = os.path.join(smali_dir, 'com/sec/internal/ims/util/Mno.smali')
    smali = open(mno_path).read()
    old_mnos = parse_mnos(smali)
    known = set(old_mnos)

    old_prof = load(os.path.join(old_raw, 'imsprofile.json'))['profile']
    new_prof = load(os.path.join(new_raw, 'imsprofile.json'))['profile']

    # Carriers to add: VoLTE profile in the new data, unknown to the old code,
    # and a known carrier in the same country to copy region/country from.
    by_suffix = {}
    for name, (region, country) in old_mnos.items():
        if region and country and '_' in name:
            by_suffix.setdefault(name.rsplit('_', 1)[1], (region, country))
    added = {}
    for p in new_prof:
        name = str(p['mnoname']).split(':')[0]
        if name in known or name in added or not is_volte(p) or '_' not in name:
            continue
        if not re.fullmatch(r'[A-Za-z0-9_+&.-]+', name) or 'LAB' in name.upper():
            continue
        rc = by_suffix.get(name.rsplit('_', 1)[1])
        if rc:
            added[name] = rc
    known |= set(added)

    if added:
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
        smali = smali[:first_field] + fields + smali[first_field:]
        open(mno_path, 'w').write(smali)

    # imsprofile.json
    old_by_name = {p['name']: p for p in old_prof}
    new_mnos = set()
    profiles = []
    dropped = []
    for p in new_prof:
        name = str(p['mnoname']).split(':')[0]
        if name not in known:
            continue
        conv = convert_profile(p, old_by_name.get(p['name']))
        if conv is None:
            dropped.append(p['name'])
            continue
        profiles.append(conv)
        new_mnos.add(name)
    kept_old = [p for p in old_prof if str(p['mnoname']).split(':')[0] not in new_mnos]
    profiles += kept_old

    # globalsettings.json
    old_gs = load(os.path.join(old_raw, 'globalsettings.json'))
    new_gs = load(os.path.join(new_raw, 'globalsettings.json'))
    gs = {
        'defaultsetting': flat(new_gs['defaultsetting']),
        'nohitsetting': flat(new_gs['nohitsetting']),
        'globalsetting': merge_by_mno(old_gs['globalsetting'], new_gs['globalsetting'], known),
    }
    for k in ('defaultsetting', 'nohitsetting'):
        for key, v in old_gs[k].items():
            gs[k].setdefault(key, v)

    # mnomap.json
    old_map = load(os.path.join(old_raw, 'mnomap.json'))
    new_map = load(os.path.join(new_raw, 'mnomap.json'))
    special = {'DEFAULT', 'LABSIM'}

    def key(m):
        return tuple(m.get(k, '') for k in ('mccmnc', 'subset', 'gid1', 'gid2', 'spname'))
    entries = [m for m in new_map['mnomap']
               if m['mnoname'].split(':')[0] in known | special]
    seen = {key(m) for m in entries}
    entries += [m for m in old_map['mnomap'] if key(m) not in seen]
    mnomap = {k: v for k, v in old_map.items() if k != 'mnomap'}
    mnomap['mnomap'] = entries

    os.makedirs(out_raw, exist_ok=True)
    for name, data in (('imsprofile.json', {'profile': profiles}),
                       ('globalsettings.json', gs),
                       ('mnomap.json', mnomap)):
        with open(os.path.join(out_raw, name), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')

    print('old code carriers: %d, added: %d (%s)' % (
        len(old_mnos), len(added), ', '.join(sorted(added))))
    print('profiles: %d from new data, %d kept from old, %d dropped (no usable network)' % (
        len(profiles) - len(kept_old), len(kept_old), len(dropped)))
    print('globalsettings: %d carriers, mnomap: %d entries' % (
        len(gs['globalsetting']), len(entries)))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
