/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.sec.epdg.compat;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.RouteInfo;
import android.net.wifi.WifiManager;
import android.os.INetworkManagementService;
import android.os.Message;
import android.os.SystemProperties;
import android.telephony.AccessNetworkConstants;
import android.telephony.NetworkRegistrationInfo;
import android.telephony.ServiceState;
import android.telephony.TelephonyManager;
import android.util.Log;

import java.net.Inet6Address;
import java.net.InetAddress;
import java.util.List;

/**
 * EpdgService was built against Samsung's Android 10 framework. Its calls to methods
 * Android 12 does not have are redirected here.
 */
public final class EpdgCompat {
    private static final String TAG = "EpdgCompat";

    // Read by the device's epdg_addr helper: "<iface> <address/prefix>...". One
    // property per tunnel, so that two SIMs' tunnels do not overwrite each other.
    private static final String TUN_ADDR_PROP = "sys.epdg.tunaddr.";

    private EpdgCompat() {}

    private static NetworkRegistrationInfo getWwanInfo(ServiceState ss, int domain) {
        return ss.getNetworkRegistrationInfo(domain,
                AccessNetworkConstants.TRANSPORT_TYPE_WWAN);
    }

    private static int getWwanRegState(ServiceState ss, int domain) {
        NetworkRegistrationInfo nri = getWwanInfo(ss, domain);
        return nri != null && nri.isInService()
                ? ServiceState.STATE_IN_SERVICE : ServiceState.STATE_OUT_OF_SERVICE;
    }

    // ServiceState: Samsung's "mobile" getters only look at the cellular (WWAN) transport.

    public static int getMobileDataRegState(ServiceState ss) {
        return getWwanRegState(ss, NetworkRegistrationInfo.DOMAIN_PS);
    }

    public static int getMobileVoiceRegState(ServiceState ss) {
        return getWwanRegState(ss, NetworkRegistrationInfo.DOMAIN_CS);
    }

    public static boolean getMobileDataRoaming(ServiceState ss) {
        NetworkRegistrationInfo nri = getWwanInfo(ss, NetworkRegistrationInfo.DOMAIN_PS);
        return nri != null && nri.isRoaming();
    }

    public static int getRilMobileDataRadioTechnology(ServiceState ss) {
        NetworkRegistrationInfo nri = getWwanInfo(ss, NetworkRegistrationInfo.DOMAIN_PS);
        return nri == null ? ServiceState.RIL_RADIO_TECHNOLOGY_UNKNOWN
                : ServiceState.networkTypeToRilRadioTechnology(
                        nri.getAccessNetworkTechnology());
    }

    public static boolean isPsOnlyReg(ServiceState ss) {
        return getMobileVoiceRegState(ss) != ServiceState.STATE_IN_SERVICE
                && getMobileDataRegState(ss) == ServiceState.STATE_IN_SERVICE;
    }

    // TelephonyManager

    // Android 12 has no GID2 getter; it only tells MVNOs apart, which none of the ePDG
    // settings for this device need.
    public static String getGroupIdLevel2(TelephonyManager tm, int subId) {
        return null;
    }

    public static String getSubscriberIdForUiccAppType(TelephonyManager tm, int subId,
            int appType) {
        return tm.createForSubscriptionId(subId).getSubscriberId();
    }

    // Samsung Wi-Fi and netd extensions.

    public static int callSECApi(WifiManager wm, Message msg) {
        return -1;
    }

    public static boolean removeRouteToHostAddress(ConnectivityManager cm, int networkType,
            InetAddress hostAddress) {
        Log.i(TAG, "removeRouteToHostAddress " + hostAddress + " (not supported)");
        return true;
    }

    public static void enableEpdg(INetworkManagementService nms, String iface, String addr) {
        Log.i(TAG, "enableEpdg " + iface + " " + addr + " (not supported)");
    }

    public static void disableEpdg(INetworkManagementService nms, String iface, String addr) {
        Log.i(TAG, "disableEpdg " + iface + " " + addr + " (not supported)");
    }

    public static void setEpdgInterfaceDropRule(INetworkManagementService nms, String iface,
            boolean add) {
        Log.i(TAG, "setEpdgInterfaceDropRule " + iface + " " + add + " (not supported)");
    }

    public static void addLegacyRouteForNetId(INetworkManagementService nms, int netId,
            RouteInfo route, int uid) {
        Log.i(TAG, "addLegacyRouteForNetId " + netId + " " + route + " (not supported)");
    }

    // Called from EpdgService.onCreate(). See WfcSync.
    public static void startWfcSync(Context context) {
        new WfcSync(context).start();
    }

    // IPv6 addresses of the tunnel. INetworkManagementService.setInterfaceConfig() only
    // sets IPv4, and apps may not call netd, so epdg_addr adds them.
    public static void addTunnelAddresses(String iface, List<LinkAddress> addresses) {
        StringBuilder value = new StringBuilder(iface);
        for (LinkAddress address : addresses) {
            InetAddress ip = address.getAddress();
            if (!(ip instanceof Inet6Address) || ip.isLinkLocalAddress()) {
                continue;
            }
            String entry = " " + ip.getHostAddress() + "/" + address.getPrefixLength();
            if (value.length() + entry.length() >= SystemProperties.PROP_VALUE_MAX) {
                Log.w(TAG, "addTunnelAddresses: no room for " + entry);
                break;
            }
            value.append(entry);
        }
        if (value.length() > iface.length()) {
            Log.i(TAG, "addTunnelAddresses " + value);
            SystemProperties.set(TUN_ADDR_PROP + iface, value.toString());
        }
    }
}
