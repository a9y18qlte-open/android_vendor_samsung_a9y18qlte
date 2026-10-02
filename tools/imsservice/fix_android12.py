#!/usr/bin/env python3
"""Make Samsung's Android 10 IMS work on Android 12.

Usage: fix_android12.py <smali dir>

Run on the baksmali output of imsmanager.jar and of imsservice.apk; each fix is
applied to whichever of them contains its class.

imsmanager.jar - TelephonyManagerExt reads
  TelephonyManager.ACTION_PRECISE_DATA_CONNECTION_STATE_CHANGED by reflection.
  Android 12 removed that hidden constant, so the field ends up null and
  RegistrationManagerBase.<init> crashes in IntentFilter.addAction(null). Fall
  back to the action string when reflection finds nothing.

imsservice.apk - ImsConfigImpl.setFeatureValue() only logs and never answers the
  listener. Android 12's MmTelFeatureCompatAdapter waits up to 2s for that
  answer on com.android.phone's main thread for every capability change, which
  ANRs the phone process in a loop. Report success to the listener.
"""

import os
import sys

EXT_FIELD = 'Lcom/sec/ims/extensions/TelephonyManagerExt;->ACTION_PRECISE_DATA_CONNECTION_STATE_CHANGED:Ljava/lang/String;'

FIXES = [
    (
        'com/sec/ims/extensions/TelephonyManagerExt.smali',
        ':precise_data_action_ok',
        """    check-cast v0, Ljava/lang/String;

    sput-object v0, %s
""" % EXT_FIELD,
        """    check-cast v0, Ljava/lang/String;

    if-nez v0, :precise_data_action_ok

    const-string v0, "android.intent.action.PRECISE_DATA_CONNECTION_STATE_CHANGED"

    :precise_data_action_ok
    sput-object v0, %s
""" % EXT_FIELD,
    ),
    (
        'com/google/ims/ImsConfigImpl.smali',
        ':set_feature_no_listener',
        """    const-string/jumbo v1, "setFeatureValue"

    invoke-static {v0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 508
    return-void
""",
        """    const-string/jumbo v1, "setFeatureValue"

    invoke-static {v0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 508
    if-eqz p4, :set_feature_no_listener

    const/4 v0, 0x0

    invoke-interface {p4, p1, p2, p3, v0}, Lcom/android/ims/ImsConfigListener;->onSetFeatureResponse(IIII)V

    :set_feature_no_listener
    return-void
""",
    ),
]


def main(smali_dir):
    found = False
    for rel, marker, old, new in FIXES:
        path = os.path.join(smali_dir, rel)
        if not os.path.exists(path):
            continue
        found = True
        s = open(path).read()
        if marker in s:
            print('%s: already patched' % rel)
            continue
        if s.count(old) != 1:
            sys.exit('%s: expected code not found' % rel)
        open(path, 'w').write(s.replace(old, new))
        print('%s: patched' % rel)
    if not found:
        sys.exit('%s: none of the patched classes found' % smali_dir)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
