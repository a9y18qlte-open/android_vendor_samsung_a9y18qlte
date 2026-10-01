#!/usr/bin/env python3
"""Make supplementary services over Ut (XCAP) work on AOSP.

Usage: fix_ut.py <smali dir>

On Android 10 call forwarding, call waiting and call barring go to IMS Ut as
soon as the phone is registered for VoLTE. Three things kept the stack's Ut
from working:

- samsung-ims-patches made ImsMmtelFeature.getUtInterface() return an empty
  AOSP ImsUtImplBase ("FORCED_GET_UT_INTERFACE_BASE"), whose methods all
  fail, so the settings failed with "turn on the radio"
  (ImsReasonInfo CODE_UT_SERVICE_UNAVAILABLE). Return an ImsUtImplBase whose
  getInterface() is the IImsUt the stack itself serves
  (GoogleImsService.getUtInterface(serviceId), Samsung's ImsUtImpl), and keep
  the empty one if the stack has none for this feature's session.
- The XCAP APN lookup filters on Samsung's per-slot column current1, which
  AOSP's carriers table lacks (SQLiteException).
- The XCAP PDN is requested with NET_CAPABILITY_XCAP, which Android 10 maps
  to no APN type, so it never comes up. Request NET_CAPABILITY_CBS instead;
  the device's SamsungImsHelper gives the SIM's XCAP APN type "xcap,cbs".
"""

import os
import sys

FEATURE = 'com/sec/internal/google/ImsMmtelFeature.smali'
UT_MODULE = 'com/sec/internal/ims/ss/UtServiceModule.smali'
PDN = 'com/sec/internal/ims/imsservice/PdnController.smali'
FWD = 'com/sec/internal/google/ForwardingImsUt.smali'

OLD = """.method public getUtInterface()Landroid/telephony/ims/stub/ImsUtImplBase;
    .registers 3

    const-string v0, "ImsMmTelFeature"

    const-string v1, "FORCED_GET_UT_INTERFACE_BASE"

    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    new-instance v0, Landroid/telephony/ims/stub/ImsUtImplBase;

    invoke-direct {v0}, Landroid/telephony/ims/stub/ImsUtImplBase;-><init>()V

    return-object v0
.end method"""

NEW = """.method public getUtInterface()Landroid/telephony/ims/stub/ImsUtImplBase;
    .registers 4

    :try_start
    iget-object v0, p0, Lcom/sec/internal/google/ImsMmtelFeature;->mMainSvc:Lcom/google/ims/GoogleImsService;

    iget v1, p0, Lcom/sec/internal/google/ImsMmtelFeature;->mServiceId:I

    invoke-virtual {v0, v1}, Lcom/google/ims/GoogleImsService;->getUtInterface(I)Lcom/android/ims/internal/IImsUt;

    move-result-object v0

    if-eqz v0, :fallback

    new-instance v1, Lcom/sec/internal/google/ForwardingImsUt;

    invoke-direct {v1, v0}, Lcom/sec/internal/google/ForwardingImsUt;-><init>(Lcom/android/ims/internal/IImsUt;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :fallback

    return-object v1

    :fallback
    const-string v0, "ImsMmTelFeature"

    const-string v1, "getUtInterface: no Ut for this session"

    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    new-instance v0, Landroid/telephony/ims/stub/ImsUtImplBase;

    invoke-direct {v0}, Landroid/telephony/ims/stub/ImsUtImplBase;-><init>()V

    return-object v0
.end method"""

FWD_CLASS = """.class public Lcom/sec/internal/google/ForwardingImsUt;
.super Landroid/telephony/ims/stub/ImsUtImplBase;
.source "ForwardingImsUt.java"


# Passes the IMS stack's own IImsUt binder to the framework.
.field private final mUt:Lcom/android/ims/internal/IImsUt;


.method public constructor <init>(Lcom/android/ims/internal/IImsUt;)V
    .registers 2

    invoke-direct {p0}, Landroid/telephony/ims/stub/ImsUtImplBase;-><init>()V

    iput-object p1, p0, Lcom/sec/internal/google/ForwardingImsUt;->mUt:Lcom/android/ims/internal/IImsUt;

    return-void
.end method

.method public getInterface()Lcom/android/ims/internal/IImsUt;
    .registers 2

    iget-object v0, p0, Lcom/sec/internal/google/ForwardingImsUt;->mUt:Lcom/android/ims/internal/IImsUt;

    return-object v0
.end method
"""


APN_FILTERS = ('    const-string v7, " AND current1 = 1"\n',
               '    const-string v7, " AND current = 1"\n')

# getNetworkCapability(): TYPE_MOBILE_XCAP (27) -> NET_CAPABILITY_XCAP (9)
CAP_OLD = """    :cond_17
    const/16 v0, 0x9
"""
CAP_NEW = """    :cond_17
    const/4 v0, 0x5
"""


def replace_once(path, old, new, what):
    s = open(path).read()
    assert s.count(old) == 1, what + ' not found'
    open(path, 'w').write(s.replace(old, new))


def replace_in_method(path, method, old, new):
    s = open(path).read()
    a = s.index('.method private %s' % method)
    b = s.index('.end method', a)
    m = s[a:b]
    assert m.count(old) == 1, method + ': ' + old.strip() + ' not found'
    open(path, 'w').write(s[:a] + m.replace(old, new) + s[b:])


def main(smali_dir):
    path = os.path.join(smali_dir, FEATURE)
    s = open(path).read()
    assert s.count(OLD) == 1, 'FORCED_GET_UT_INTERFACE_BASE stub not found'
    open(path, 'w').write(s.replace(OLD, NEW))
    open(os.path.join(smali_dir, FWD), 'w').write(FWD_CLASS)

    # The XCAP APN lookup adds Samsung's per-slot column current1, which
    # AOSP's carriers table lacks, and current, which AOSP only sets for one
    # SIM. SIM_APN_URI/<subId> already limits the query to the SIM's own APNs.
    path = os.path.join(smali_dir, UT_MODULE)
    for f in APN_FILTERS:
        replace_once(path, f, '    const-string v7, ""\n', f.strip())

    # XCAP PDN with NET_CAPABILITY_CBS.
    replace_in_method(os.path.join(smali_dir, PDN), 'getNetworkCapability(I)I',
                      CAP_OLD, CAP_NEW)
    print('Ut: real IImsUt, XCAP APN lookup without current1, XCAP PDN over CBS')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
