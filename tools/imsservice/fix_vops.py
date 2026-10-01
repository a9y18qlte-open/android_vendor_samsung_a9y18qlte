#!/usr/bin/env python3
"""Make ServiceStateWrapper.getLteImsVoiceAvail() report the network's VoPS.

Usage: fix_vops.py <smali dir>

Samsung's code reads VoPS through Samsung-only ServiceState fields, which do
not exist on AOSP, so samsung-ims-patches stage 07 stubbed the method to
return 2 (supported). The IMS stack then brings up IMS and registers on
networks that told the phone VoPS is not supported (e.g. a SIM without
VoLTE), and a slot stuck registering holds up the other slot's registration.

Read the value AOSP has instead:
  ServiceState.getNetworkRegistrationInfo(DOMAIN_PS, TRANSPORT_TYPE_WWAN)
    .getDataSpecificInfo().getLteVopsSupportInfo().getVopsSupport()
LteVopsSupportInfo uses the same numbers as Samsung's constants (1 not
available, 2 supported, 3 not supported). Only an explicit 3 is passed on;
anything else keeps the stage 07 behaviour (2).
"""

import os
import sys

WRAPPER = 'com/sec/internal/ims/util/os/ServiceStateWrapper.smali'
CLS = 'Lcom/sec/internal/ims/util/os/ServiceStateWrapper;'

OLD = """.method public getLteImsVoiceAvail()I
    .registers 2

    const/4 v0, 0x2

    return v0
.end method"""

NEW = """.method public getLteImsVoiceAvail()I
    .registers 5

    const/4 v0, 0x2

    iget-object v1, p0, %(cls)s->mServiceState:Landroid/telephony/ServiceState;

    if-eqz v1, :done

    :try_start
    const/4 v2, 0x2

    const/4 v3, 0x1

    invoke-virtual {v1, v2, v3}, Landroid/telephony/ServiceState;->getNetworkRegistrationInfo(II)Landroid/telephony/NetworkRegistrationInfo;

    move-result-object v1

    if-eqz v1, :done

    invoke-virtual {v1}, Landroid/telephony/NetworkRegistrationInfo;->getDataSpecificInfo()Landroid/telephony/DataSpecificRegistrationInfo;

    move-result-object v1

    if-eqz v1, :done

    invoke-virtual {v1}, Landroid/telephony/DataSpecificRegistrationInfo;->getLteVopsSupportInfo()Landroid/telephony/LteVopsSupportInfo;

    move-result-object v1

    if-eqz v1, :done

    invoke-virtual {v1}, Landroid/telephony/LteVopsSupportInfo;->getVopsSupport()I

    move-result v1
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :done

    const/4 v2, 0x3

    if-ne v1, v2, :done

    move v0, v1

    :done
    return v0
.end method""" % {'cls': CLS}


def main(smali_dir):
    path = os.path.join(smali_dir, WRAPPER)
    s = open(path).read()
    assert s.count(OLD) == 1, 'stage 07 getLteImsVoiceAvail() stub not found'
    open(path, 'w').write(s.replace(OLD, NEW))
    print('getLteImsVoiceAvail() now reports VoPS not supported from LteVopsSupportInfo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
