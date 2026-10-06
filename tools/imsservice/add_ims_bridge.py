#!/usr/bin/env python3
"""Expose imsservice as an Android 12 ImsService so SMS over IMS works.

Usage: add_ims_bridge.py <apktool -r output of imsservice.apk> <bridge smali dir>

Samsung's GoogleImsServiceAdapter is a compat ImsService; Android 12 wraps it in
MmTelFeatureCompatAdapter, which has no SMS, and the SMS methods of Samsung's
GoogleImsService are not part of AOSP's IImsService, so incoming SMS over IMS
stays in SmsServiceModule until it times out. bridge/ replaces the adapter with
an Android 12 ImsService that wraps the compat feature in-process and adds an
ImsSmsImplBase backed by GoogleImsService.

- smali/.../GoogleImsServiceAdapter.smali is replaced by bridge/ (smali_classes2).
- The manifest's intent action of that service becomes
  android.telephony.ims.ImsService (binary string pool edit, so everything else
  in the manifest stays byte-identical).
- ImsSmsImpl calls IImsSmsListener methods that only Android 10 has; they are
  redirected to SmsListenerCompat. Its direct calls to Android 10 / Samsung
  framework methods Android 12 lacks go to TelephonyCompat, and bridge/ also
  provides the Samsung TelephonyFeatures and SemCscFeature classes it uses.

Incoming SMS also needs persist.radio.ims.legacysmsip.enabled=0 (device
vendor.prop), so that ImsSmsImpl registers its own SmsServiceModule listener.

Build the bridge smali with bridge/build.sh and baksmali its classes.dex.
"""

import os
import re
import shutil
import struct
import sys

ADAPTER = 'com/sec/internal/google/GoogleImsServiceAdapter.smali'
OLD_ACTION = 'android.telephony.ims.compat.ImsService'
NEW_ACTION = 'android.telephony.ims.ImsService'

LISTENER = 'Landroid/telephony/ims/aidl/IImsSmsListener;'
COMPAT = 'Lcom/sec/internal/google/SmsListenerCompat;'
TELEPHONY_COMPAT = 'Lcom/sec/internal/google/TelephonyCompat;'
REDIRECTS = {
    'onSendSmsResult(IIII)V': 'onSendSmsResult(%sIIII)V' % LISTENER,
    'onSendSmsResponse(IIIIII)V': 'onSendSmsResponse(%sIIIIII)V' % LISTENER,
    'onSmsStatusReportReceived(IILjava/lang/String;[B)V':
        'onSmsStatusReportReceived(%sIILjava/lang/String;[B)V' % LISTENER,
}

STATIC_REDIRECTS = (
    'Lcom/android/internal/telephony/uicc/IccUtils;->getIccType(I)I',
    'Landroid/telephony/TelephonyManager;->getNetworkClass(I)I',
    'Landroid/telephony/TelephonyManager;->setTelephonyProperty(ILjava/lang/String;'
    'Ljava/lang/String;)V',
)


def patch_manifest_string(path, old, new):
    """Replace one string in the binary XML's UTF-16 string pool."""
    data = bytearray(open(path, 'rb').read())
    xml_type, xml_hdr, xml_size = struct.unpack_from('<HHI', data, 0)
    pool = xml_hdr
    (p_type, p_hdr, p_size, count, styles, flags, strings_start,
     styles_start) = struct.unpack_from('<HHIIIIII', data, pool)
    assert xml_type == 0x0003 and p_type == 0x0001 and styles == 0
    assert not flags & 0x100, 'UTF-8 string pool not handled'

    offsets = struct.unpack_from('<%dI' % count, data, pool + p_hdr)
    base = pool + strings_start
    strings = []
    for off in offsets:
        n = struct.unpack_from('<H', data, base + off)[0]
        assert not n & 0x8000
        strings.append(data[base + off + 2:base + off + 2 + n * 2].decode('utf-16-le'))
    if old not in strings:
        if new in strings:
            return False
        sys.exit('%s: "%s" not in the string pool' % (path, old))
    strings[strings.index(old)] = new

    blob = bytearray()
    new_offsets = []
    for s in strings:
        new_offsets.append(len(blob))
        blob += struct.pack('<H', len(s)) + s.encode('utf-16-le') + b'\0\0'
    blob += b'\0' * (-len(blob) % 4)
    new_strings_start = p_hdr + 4 * count
    new_pool = bytearray(struct.pack('<HHIIIIII', p_type, p_hdr, new_strings_start + len(blob),
                                     count, 0, flags, new_strings_start, 0))
    new_pool += data[pool + 28:pool + p_hdr]
    new_pool += struct.pack('<%dI' % count, *new_offsets) + blob

    rest = data[pool + p_size:]
    out = data[:pool] + new_pool + rest
    struct.pack_into('<I', out, 4, len(out))
    open(path, 'wb').write(out)
    return True


def redirect_calls(smali_dir):
    listener = re.compile(r'invoke-interface(/range)? (\{[^}]*\}), %s->(%s)'
                          % (re.escape(LISTENER), '|'.join(map(re.escape, REDIRECTS))))
    static = re.compile(r'invoke-static(/range)? (\{[^}]*\}), (%s)'
                        % '|'.join(map(re.escape, STATIC_REDIRECTS)))
    counts = [0, 0]
    for root, _, files in os.walk(os.path.join(smali_dir, 'com/google/ims')):
        for name in files:
            path = os.path.join(root, name)
            text = open(path).read()
            text, n = listener.subn(
                lambda m: 'invoke-static%s %s, %s->%s' % (m.group(1) or '', m.group(2), COMPAT,
                                                          REDIRECTS[m.group(3)]), text)
            counts[0] += n
            text, n = static.subn(
                lambda m: 'invoke-static%s %s, %s->%s' % (m.group(1) or '', m.group(2),
                                                          TELEPHONY_COMPAT,
                                                          m.group(3).split('->')[1]), text)
            counts[1] += n
            open(path, 'w').write(text)
    return counts


def main(apk_dir, bridge_dir):
    smali = os.path.join(apk_dir, 'smali')
    adapter = os.path.join(smali, ADAPTER)
    if os.path.exists(adapter):
        os.remove(adapter)
    dest = os.path.join(apk_dir, 'smali_classes2')
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(bridge_dir, dest)

    listener, static = redirect_calls(smali)
    print('listener calls redirected: %d, framework calls redirected: %d' % (listener, static))
    if patch_manifest_string(os.path.join(apk_dir, 'AndroidManifest.xml'), OLD_ACTION, NEW_ACTION):
        print('manifest: %s -> %s' % (OLD_ACTION, NEW_ACTION))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
