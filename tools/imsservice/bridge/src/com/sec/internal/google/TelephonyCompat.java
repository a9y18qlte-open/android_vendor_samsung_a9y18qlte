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

package com.sec.internal.google;

import android.os.SystemProperties;
import android.telephony.TelephonyManager;
import android.util.Log;

/**
 * Android 10 and Samsung framework methods that imsservice's SMS code calls directly but
 * Android 12 no longer has; add_ims_bridge.py redirects those calls here.
 */
public final class TelephonyCompat {
    private static final String TAG = "TelephonyCompat";

    private TelephonyCompat() {}

    /** Samsung IccUtils.getIccType(): only consulted for Chinese carriers. */
    public static int getIccType(int phoneId) {
        return 0;
    }

    /** Android 10 TelephonyManager.getNetworkClass(). */
    public static int getNetworkClass(int networkType) {
        switch (networkType) {
            case TelephonyManager.NETWORK_TYPE_GPRS:
            case TelephonyManager.NETWORK_TYPE_GSM:
            case TelephonyManager.NETWORK_TYPE_EDGE:
            case TelephonyManager.NETWORK_TYPE_CDMA:
            case TelephonyManager.NETWORK_TYPE_1xRTT:
            case TelephonyManager.NETWORK_TYPE_IDEN:
                return 1; // NETWORK_CLASS_2_G
            case TelephonyManager.NETWORK_TYPE_UMTS:
            case TelephonyManager.NETWORK_TYPE_EVDO_0:
            case TelephonyManager.NETWORK_TYPE_EVDO_A:
            case TelephonyManager.NETWORK_TYPE_HSDPA:
            case TelephonyManager.NETWORK_TYPE_HSUPA:
            case TelephonyManager.NETWORK_TYPE_HSPA:
            case TelephonyManager.NETWORK_TYPE_EVDO_B:
            case TelephonyManager.NETWORK_TYPE_EHRPD:
            case TelephonyManager.NETWORK_TYPE_HSPAP:
            case TelephonyManager.NETWORK_TYPE_TD_SCDMA:
                return 2; // NETWORK_CLASS_3_G
            case TelephonyManager.NETWORK_TYPE_LTE:
            case TelephonyManager.NETWORK_TYPE_IWLAN:
            case 19: // NETWORK_TYPE_LTE_CA
                return 3; // NETWORK_CLASS_4_G
            case TelephonyManager.NETWORK_TYPE_NR:
                return 4; // NETWORK_CLASS_5_G
            default:
                return 0; // NETWORK_CLASS_UNKNOWN
        }
    }

    /** Android 10 TelephonyManager.setTelephonyProperty(): one comma-separated value per phone. */
    public static void setTelephonyProperty(int phoneId, String property, String value) {
        if (phoneId < 0 || property == null) {
            return;
        }
        String[] values = SystemProperties.get(property, "").split(",", -1);
        int count = Math.max(values.length, phoneId + 1);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < count; i++) {
            if (i > 0) {
                sb.append(',');
            }
            if (i == phoneId) {
                sb.append(value == null ? "" : value);
            } else if (i < values.length) {
                sb.append(values[i]);
            }
        }
        try {
            SystemProperties.set(property, sb.toString());
        } catch (RuntimeException e) {
            Log.w(TAG, "setTelephonyProperty " + property + ": " + e.getMessage());
        }
    }
}
