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

import android.content.ContentValues;
import android.content.Context;
import android.database.ContentObserver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyManager;
import android.telephony.ims.ImsMmTelManager;
import android.util.Log;
import android.util.SparseIntArray;

/**
 * Copies the framework's Wi-Fi Calling settings into EpdgService's own provider.
 *
 * EpdgService and imsservice take the Wi-Fi Calling switch and preferred mode from
 * EpdgService's provider, one table per SIM slot, which Samsung's call settings write.
 * On AOSP the user sets them in the framework (Settings, ImsMmTelManager).
 *
 * The switch always follows the framework. The preferred mode is only copied when it
 * changes in the framework: Samsung has modes the framework does not (5), and the
 * carrier's default in epdg_apns_conf.xml stays until the user picks one.
 */
final class WfcSync extends ContentObserver {
    private static final String TAG = "EpdgWfcSync";

    private static final Uri SETTINGS = Uri.parse("content://iwlansettings/todos");
    private static final Uri[] VOWIFI_SETTINGS = {
            Uri.withAppendedPath(SETTINGS, "vowifisetting"),
            Uri.withAppendedPath(SETTINGS, "vowifisetting2"),
    };
    private static final String ENABLE = "wifi_call_enable";
    private static final String PREFERRED = "wifi_call_preferred";

    // Samsung's wifi_call_preferred values.
    private static final int SEC_WIFI_PREFERRED = 1;
    private static final int SEC_CELLULAR_PREFERRED = 2;
    private static final int SEC_WIFI_ONLY = 3;

    private final Context mContext;
    // Per slot: the subscription and framework mode seen last.
    private final SparseIntArray mSubIds = new SparseIntArray();
    private final SparseIntArray mModes = new SparseIntArray();

    WfcSync(Context context) {
        super(new Handler(Looper.getMainLooper()));
        mContext = context;
    }

    void start() {
        // The framework settings live in the subscription table; EpdgService fills its
        // own tables from epdg_apns_conf.xml when a SIM loads.
        mContext.getContentResolver().registerContentObserver(
                SubscriptionManager.CONTENT_URI, true, this);
        mContext.getContentResolver().registerContentObserver(SETTINGS, true, this);
        onChange(false);
    }

    @Override
    public void onChange(boolean selfChange) {
        int slots = Math.min(VOWIFI_SETTINGS.length,
                mContext.getSystemService(TelephonyManager.class).getActiveModemCount());
        for (int slot = 0; slot < slots; slot++) {
            try {
                sync(slot);
            } catch (RuntimeException e) {
                Log.w(TAG, "slot " + slot + ": " + e);
            }
        }
    }

    private void sync(int slot) {
        int[] subIds = mContext.getSystemService(SubscriptionManager.class)
                .getSubscriptionIds(slot);
        int subId = subIds != null && subIds.length > 0
                ? subIds[0] : SubscriptionManager.INVALID_SUBSCRIPTION_ID;
        if (!SubscriptionManager.isValidSubscriptionId(subId)) {
            mSubIds.delete(slot);
            return;
        }
        ImsMmTelManager mmTel = ImsMmTelManager.createForSubscriptionId(subId);
        write(slot, ENABLE, mmTel.isVoWiFiSettingEnabled() ? 1 : 0);

        int mode = mmTel.getVoWiFiModeSetting();
        boolean known = mSubIds.get(slot, SubscriptionManager.INVALID_SUBSCRIPTION_ID) == subId;
        if (known && mModes.get(slot) != mode) {
            int preferred = toSecMode(mode);
            if (preferred > 0) {
                write(slot, PREFERRED, preferred);
            }
        }
        mSubIds.put(slot, subId);
        mModes.put(slot, mode);
    }

    private static int toSecMode(int mode) {
        switch (mode) {
            case ImsMmTelManager.WIFI_MODE_WIFI_PREFERRED:
                return SEC_WIFI_PREFERRED;
            case ImsMmTelManager.WIFI_MODE_CELLULAR_PREFERRED:
                return SEC_CELLULAR_PREFERRED;
            case ImsMmTelManager.WIFI_MODE_WIFI_ONLY:
                return SEC_WIFI_ONLY;
            default:
                return -1;
        }
    }

    private void write(int slot, String column, int value) {
        Uri uri = VOWIFI_SETTINGS[slot];
        try (Cursor c = mContext.getContentResolver().query(uri, new String[] {column},
                null, null, null)) {
            // No row until EpdgService has set up the slot; this runs again then.
            if (c == null || !c.moveToFirst() || c.getColumnIndex(column) < 0
                    || c.getInt(c.getColumnIndex(column)) == value) {
                return;
            }
        }
        ContentValues values = new ContentValues();
        values.put(column, value);
        mContext.getContentResolver().update(uri, values, null, null);
        Log.i(TAG, "slot " + slot + ": " + column + " = " + value);
    }
}
