#!/usr/bin/env python3
"""Make Samsung's Android 10 EpdgService run on Android 12.

Usage: add_epdg_compat.py <apktool -r output of EpdgService.apk> <compat smali dir>

EpdgService was built against Samsung's framework. compat/ provides the Samsung
classes it uses (SemSystemProperties, SemFloatingFeature, SemCscFeature,
SemHqmManager) and the Android 10 Inet4AddressUtils, and EpdgCompat stands in
for the framework methods Android 12 lacks: the cellular-only ServiceState
getters, per-subscription TelephonyManager getters, and Samsung's Wi-Fi and netd
extensions. Calls to those methods are redirected to EpdgCompat.

WfcActivityController.IsAvaliableWfcActivity() keeps the ePDG off unless
Samsung's Wi-Fi Calling app (com.sec.unifiedwfc) is installed. On AOSP the
Wi-Fi Calling switch is the framework's own, so a missing app counts as
available; a disabled one still turns the ePDG off.

Samsung's kernel has virtual rmnet<n> interfaces that carry each IWLAN data
call, and its netd redirects them into the ePDG tunnel (enableEpdg). This kernel
has neither, so the data call is reported on the tunnel itself (epdg<n>, the
eris TUN device), and EpdgInterface configures its addresses there. Interface
events for epdg<n> are passed on as rmnet<n>, the name EpdgService tracks the
data call by; without them it tears the tunnel down again. Link down events of
the tunnel are dropped: it is down while eris brings it up, and a lost tunnel is
reported by eris itself. INetworkManagementService.setInterfaceConfig() only sets
IPv4, and apps may not call netd, so EpdgCompat hands the IPv6 addresses of the
tunnel to the device's epdg_addr helper (sys.epdg.tunaddr.<iface>). A handover
from LTE reuses the rmnet<n> interface of the LTE data call on Samsung's kernel;
here the tunnel is a new interface, so a handover without one already up is
brought up like an initial attach.

EpdgService and imsservice take the Wi-Fi Calling switch and preferred mode
from EpdgService's own settings provider, which Samsung's call settings write.
On AOSP they are the framework's (ImsMmTelManager), so EpdgService.onCreate()
starts EpdgCompat.startWfcSync(), which copies them over.

EpdgService and its MAPCON provider reload epdg_apns_conf.xml and
mapconprovider.xml into their databases when Samsung's firmware version
(ro.build.PDA) changes; compat SemSystemProperties answers it with the build
time, so that a new ROM build reloads them.

Android 12 changed INetworkManagementEventObserver.interfaceClassDataActivityChanged();
EpdgNetworkMgmtObserver gets the new signature, which it only logs, like the old one.

Build the compat smali with compat/build.sh and baksmali its classes.dex.
"""

import os
import re
import shutil
import sys

COMPAT = 'Lcom/sec/epdg/compat/EpdgCompat;'
REDIRECTS = {
    'Landroid/telephony/ServiceState;': [
        'getMobileDataRegState()I', 'getMobileVoiceRegState()I', 'getMobileDataRoaming()Z',
        'getRilMobileDataRadioTechnology()I', 'isPsOnlyReg()Z',
    ],
    'Landroid/telephony/TelephonyManager;': [
        'getGroupIdLevel2(I)Ljava/lang/String;',
        'getSubscriberIdForUiccAppType(II)Ljava/lang/String;',
    ],
    'Landroid/net/wifi/WifiManager;': ['callSECApi(Landroid/os/Message;)I'],
    'Landroid/net/ConnectivityManager;': ['removeRouteToHostAddress(ILjava/net/InetAddress;)Z'],
    'Landroid/os/INetworkManagementService;': [
        'enableEpdg(Ljava/lang/String;Ljava/lang/String;)V',
        'disableEpdg(Ljava/lang/String;Ljava/lang/String;)V',
        'setEpdgInterfaceDropRule(Ljava/lang/String;Z)V',
        'addLegacyRouteForNetId(ILandroid/net/RouteInfo;I)V',
    ],
}

OBSERVERS = (
    'com/sec/epdg/interfaceController/EpdgInterfaceController$EpdgInterfaceObserver.smali',
    'com/sec/epdg/EpdgSubScription$EpdgNetworkManagementObserver.smali',
)
TO_MOBILE_IFACE = ('Lcom/sec/epdg/EpdgNetworkMgmtObserver;'
                   '->toMobileIface(Ljava/lang/String;)Ljava/lang/String;')
TUN_IFACE = ('Lcom/sec/epdg/interfaceController/EpdgInterface;->getTunInterface'
             '(Ljava/lang/String;)Ljava/lang/String;')

# (smali file, method, regex within the method, replacement)
PATCHES = [
    (
        'com/sec/epdg/EpdgService.smali',
        '.method public onCreate()V',
        r'(invoke-direct \{p0\}, Lcom/sec/epdg/EpdgService;->initializeEpdgService\(\)V\n)',
        r'''\1
    invoke-static {p0}, Lcom/sec/epdg/compat/EpdgCompat;->startWfcSync(Landroid/content/Context;)V
''',
    ),
    (
        'com/sec/epdg/WfcActivityController.smali',
        '.method public IsAvaliableWfcActivity(Landroid/content/Context;Ljava/lang/String;I)Z',
        r'(\n\s*:catch_0\n\s*move-exception v3\n)',
        r'\1\n    const/4 v0, 0x1\n',
    ),
    (
        'com/sec/epdg/TelephonyAdapter.smali',
        '.method public convertDataCallResponse(Lcom/sec/epdg/EpdgCommands$ApnConnStatusData;)'
        'Landroid/telephony/data/DataCallResponse;',
        r'Lcom/sec/epdg/EpdgUtils;->getMobileInterfaceName\(I\)',
        'Lcom/sec/epdg/EpdgUtils;->getIwlanInterfaceName(I)',
    ),
    (
        'com/sec/epdg/interfaceController/EpdgInterfaceController.smali',
        '.method public updateConnectionStatus(ILcom/sec/epdg/EpdgCommands$ApnConnStatusData;)V',
        r'(invoke-virtual \{v0\}, Lcom/sec/epdg/interfaceController/EpdgInterface;->'
        r'getApnConnStatusData\(\)Lcom/sec/epdg/EpdgCommands\$ApnConnStatusData;\n\n'
        r'    move-result-object v2\n)(?=(?:(?!:cond_0)[\s\S])*:cond_0\n)',
        r'''\1
    if-eqz v2, :cond_0
''',
    ),
    (
        'com/sec/epdg/interfaceController/EpdgInterface.smali',
        '.method private getTunInterface(Ljava/lang/String;)Ljava/lang/String;',
        r'(\.param p1, "radioIface"[^\n]*\n)',
        r'''\1
    const-string v0, "epdg"

    invoke-virtual {p1, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v0

    if-eqz v0, :tun_from_radio_iface

    return-object p1

    :tun_from_radio_iface
''',
    ),
    (
        'com/sec/epdg/interfaceController/EpdgInterface.smali',
        '.method private makeInterfaceUp(Ljava/lang/String;Ljava/util/List;I)V',
        r'(\.local p2, "addresses"[^\n]*\n)',
        r'''\1
    invoke-direct {p0, p1}, %s

    move-result-object p1
''' % TUN_IFACE,
    ),
    (
        'com/sec/epdg/interfaceController/EpdgInterface.smali',
        '.method private makeInterfaceUp(Ljava/lang/String;Ljava/util/List;I)V',
        r'(\n    :goto_0\n)',
        r'''\1
    invoke-static {p1, p2}, Lcom/sec/epdg/compat/EpdgCompat;->addTunnelAddresses(Ljava/lang/String;Ljava/util/List;)V
''',
    ),
    (
        'com/sec/epdg/interfaceController/EpdgInterface.smali',
        '.method private makeInterfaceDown(Ljava/lang/String;)V',
        r'(\.param p1, "iface"[^\n]*\n)',
        r'''\1
    invoke-direct {p0, p1}, %s

    move-result-object p1
''' % TUN_IFACE,
    ),
] + [
    (
        observer,
        '.method public EpdgInterfaceLinkStateChanged(Ljava/lang/String;Z)V',
        r'(\.param p2, "up"[^\n]*\n)',
        r'''\1
    const-string v0, "epdg"

    invoke-virtual {p1, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v0

    if-eqz v0, :epdg_link_state_ok

    if-nez p2, :epdg_link_state_ok

    return-void

    :epdg_link_state_ok
    invoke-static {p1}, %s

    move-result-object p1
''' % TO_MOBILE_IFACE,
    ) for observer in OBSERVERS
] + [
    (
        observer,
        '.method public EpdgAddressUpdated(Landroid/net/LinkAddress;Ljava/lang/String;)V',
        r'(\.param p2, "iface"[^\n]*\n)',
        r'''\1
    invoke-static {p2}, %s

    move-result-object p2
''' % TO_MOBILE_IFACE,
    ) for observer in OBSERVERS
]

# INetd transaction for interfaceAddAddress(String ifName, String addrString, int prefixLength)
# (smali file, method added to the class)
ADDED_METHODS = [
    (
        'com/sec/epdg/EpdgNetworkMgmtObserver.smali',
        """.method public interfaceClassDataActivityChanged(IZJI)V
    .locals 0

    return-void
.end method
""",
    ),
    (
        'com/sec/epdg/EpdgNetworkMgmtObserver.smali',
        """.method protected static toMobileIface(Ljava/lang/String;)Ljava/lang/String;
    .locals 2

    const-string v0, "epdg"

    invoke-virtual {p0, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v0

    if-eqz v0, :not_epdg

    invoke-static {}, Lcom/sec/epdg/EpdgUtils;->getMobileInterfacePrefix()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x4

    invoke-virtual {p0, v1}, Ljava/lang/String;->substring(I)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v0, v1}, Ljava/lang/String;->concat(Ljava/lang/String;)Ljava/lang/String;

    move-result-object p0

    :not_epdg
    return-object p0
.end method
""",
    ),
]


def apply_patches(smali_dir):
    for path, method, pattern, repl in PATCHES:
        path = os.path.join(smali_dir, path)
        text = open(path).read()
        start = text.index(method)
        end = text.index('.end method', start)
        body, n = re.subn(pattern, repl, text[start:end])
        if n != 1:
            sys.exit('%s: patch does not apply' % path)
        open(path, 'w').write(text[:start] + body + text[end:])
    for path, method in ADDED_METHODS:
        path = os.path.join(smali_dir, path)
        text = open(path).read()
        if method.split('\n')[0] in text:
            sys.exit('%s: method already there' % path)
        open(path, 'w').write(text.rstrip('\n') + '\n\n' + method)


def redirect_calls(smali_dir):
    count = 0
    for cls, methods in REDIRECTS.items():
        call = re.compile(r'invoke-(?:virtual|interface)(/range)? (\{[^}]*\}), %s->(%s)'
                          % (re.escape(cls), '|'.join(map(re.escape, methods))))

        def repl(m):
            name, args = m.group(3).split('(', 1)
            return 'invoke-static%s %s, %s->%s(%s%s' % (m.group(1) or '', m.group(2), COMPAT,
                                                      name, cls, args)
        for root, _, files in os.walk(smali_dir):
            for f in files:
                path = os.path.join(root, f)
                text = open(path).read()
                text, n = call.subn(repl, text)
                if n:
                    count += n
                    open(path, 'w').write(text)
    return count


def main(apk_dir, compat_dir):
    dest = os.path.join(apk_dir, 'smali_classes2')
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(compat_dir, dest)
    smali = os.path.join(apk_dir, 'smali')
    apply_patches(smali)
    print('calls redirected: %d' % redirect_calls(smali))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
