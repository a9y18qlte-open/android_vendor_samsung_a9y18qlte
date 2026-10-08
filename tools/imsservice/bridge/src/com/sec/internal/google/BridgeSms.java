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

import android.os.Handler;
import android.os.Looper;
import android.os.RemoteException;
import android.telephony.PhoneNumberUtils;
import android.telephony.SmsManager;
import android.telephony.SubscriptionManager;
import android.telephony.ims.aidl.IImsSmsListener;
import android.telephony.ims.stub.ImsSmsImplBase;
import android.util.Log;
import android.util.SparseArray;

import com.google.ims.GoogleImsService;

/**
 * SMS over IMS through Samsung's GoogleImsService, which on Samsung's own framework is
 * driven by the phone process. Results and incoming messages come back through
 * {@link #mListener}; ImsSmsImpl's Android 10 listener calls are routed to it by
 * {@link SmsListenerCompat}.
 */
public class BridgeSms extends ImsSmsImplBase {
    private static final String TAG = "BridgeSms";

    // ImsSmsImpl drops a message without a result when it fails internally; give the
    // framework a fallback result so it retries over CS instead of waiting forever. Longer
    // than the RP timers (TR1M), so a slow but working network does not get a duplicate.
    private static final long SEND_TIMEOUT_MS = 90000;

    private final GoogleImsService mImsService;
    private final int mSlotId;
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private final SparseArray<Runnable> mSendTimeouts = new SparseArray<>();
    // Status report token -> ImsSmsImpl's message id, which the report ack has to carry.
    private final SparseArray<Integer> mStatusReportIds = new SparseArray<>();
    private volatile boolean mReady;

    private final Listener mListener = new Listener();

    class Listener extends IImsSmsListener.Stub {
        @Override
        public void onSendSmsResult(int token, int messageRef, int status, int reason,
                int networkErrorCode) {
            cancelSendTimeout(token);
            try {
                if (status == SEND_STATUS_OK) {
                    onSendSmsResultSuccess(token, messageRef);
                } else {
                    onSendSmsResultError(token, messageRef, status, reason, networkErrorCode);
                }
            } catch (RuntimeException e) {
                Log.w(TAG, "onSendSmsResult: " + e.getMessage());
            }
        }

        void onSmsStatusReportReceived(int token, int messageId, String format, byte[] pdu) {
            synchronized (mStatusReportIds) {
                mStatusReportIds.put(token, messageId);
            }
            onSmsStatusReportReceived(token, format, pdu);
        }

        @Override
        public void onSmsStatusReportReceived(int token, String format, byte[] pdu) {
            try {
                BridgeSms.this.onSmsStatusReportReceived(token, format, pdu);
            } catch (RuntimeException e) {
                Log.w(TAG, "onSmsStatusReportReceived: " + e.getMessage());
            }
        }

        @Override
        public void onMemoryAvailableResult(int token, int result, int networkErrorCode) {
            // Android 14. ImsSmsImpl predates it and never calls it.
            try {
                BridgeSms.this.onMemoryAvailableResult(token, result, networkErrorCode);
            } catch (RuntimeException e) {
                Log.w(TAG, "onMemoryAvailableResult: " + e.getMessage());
            }
        }

        @Override
        public void onSmsReceived(int token, String format, byte[] pdu) {
            try {
                BridgeSms.this.onSmsReceived(token, format, pdu);
            } catch (RuntimeException e) {
                Log.w(TAG, "onSmsReceived: " + e.getMessage());
            }
        }
    }

    public BridgeSms(GoogleImsService imsService, int slotId) {
        mImsService = imsService;
        mSlotId = slotId;
    }

    @Override
    public void onReady() {
        try {
            mImsService.setSmsListener(mSlotId, mListener);
            mImsService.onSmsReady(mSlotId);
            mReady = true;
            Log.i(TAG, "onReady: slot " + mSlotId);
        } catch (RemoteException e) {
            Log.w(TAG, "onReady: " + e.getMessage());
        }
    }

    @Override
    public void sendSms(int token, int messageRef, String format, String smsc, boolean isRetry,
            byte[] pdu) {
        if (mReady) {
            // ImsSmsImpl expects the SMSC as a hex encoded SC address and rejects a PDU
            // without one; the framework passes null for the default SMSC.
            if (smsc == null || !smsc.matches("([0-9a-fA-F]{2})+") || smsc.equals("00")) {
                smsc = getDefaultSmsc();
            }
            Runnable timeout = () -> {
                synchronized (mSendTimeouts) {
                    mSendTimeouts.remove(token);
                }
                Log.w(TAG, "sendSms: no result for token " + token + ", falling back");
                onSendSmsResultError(token, messageRef, SEND_STATUS_ERROR_FALLBACK,
                        SmsManager.RESULT_ERROR_GENERIC_FAILURE, RESULT_NO_NETWORK_ERROR);
            };
            synchronized (mSendTimeouts) {
                mSendTimeouts.put(token, timeout);
            }
            mHandler.postDelayed(timeout, SEND_TIMEOUT_MS);
            try {
                mImsService.sendSms(mSlotId, token, messageRef, format, smsc, isRetry, pdu);
                return;
            } catch (RemoteException e) {
                Log.w(TAG, "sendSms: " + e.getMessage());
            }
            cancelSendTimeout(token);
        }
        onSendSmsResultError(token, messageRef, SEND_STATUS_ERROR_FALLBACK,
                SmsManager.RESULT_ERROR_GENERIC_FAILURE, RESULT_NO_NETWORK_ERROR);
    }

    private String getDefaultSmsc() {
        try {
            int[] subIds = SubscriptionManager.getSubId(mSlotId);
            if (subIds != null && subIds.length > 0) {
                String address = SmsManager.getSmsManagerForSubscriptionId(subIds[0])
                        .getSmscAddress();
                if (address != null) {
                    // Some RILs report the AT+CSCA form: "+123456",145
                    address = address.replace("\"", "").trim();
                    boolean international = false;
                    int comma = address.indexOf(',');
                    if (comma >= 0) {
                        international = address.substring(comma + 1).trim().equals("145");
                        address = address.substring(0, comma).trim();
                    }
                    // Samsung's RIL drops the type of number. ImsSmsImpl turns the SC address
                    // into the SIP target, so an international number has to keep its "+".
                    if (!address.startsWith("+") && (international
                            || (address.length() > 0 && address.charAt(0) != '0'))) {
                        address = "+" + address;
                    }
                    byte[] sca = PhoneNumberUtils.networkPortionToCalledPartyBCDWithLength(
                            address);
                    if (sca != null && sca.length > 1) {
                        StringBuilder hex = new StringBuilder();
                        for (byte b : sca) {
                            hex.append(String.format("%02x", b & 0xff));
                        }
                        return hex.toString();
                    }
                }
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "getDefaultSmsc: " + e.getMessage());
        }
        Log.w(TAG, "getDefaultSmsc: no SMSC for slot " + mSlotId);
        return "00";
    }

    private void cancelSendTimeout(int token) {
        Runnable timeout;
        synchronized (mSendTimeouts) {
            timeout = mSendTimeouts.get(token);
            mSendTimeouts.remove(token);
        }
        if (timeout != null) {
            mHandler.removeCallbacks(timeout);
        }
    }

    @Override
    public void acknowledgeSms(int token, int messageRef, int result) {
        // ImsSmsImpl matches the deliver report to the incoming message by messageRef, which
        // Samsung's framework sets to the message id passed as token; AOSP always passes 0.
        if (messageRef == 0) {
            messageRef = token;
        }
        try {
            mImsService.acknowledgeSms(mSlotId, token, messageRef, result);
        } catch (RemoteException e) {
            Log.w(TAG, "acknowledgeSms: " + e.getMessage());
        }
    }

    @Override
    public void acknowledgeSmsReport(int token, int messageRef, int result) {
        synchronized (mStatusReportIds) {
            Integer messageId = mStatusReportIds.get(token);
            if (messageId != null) {
                messageRef = messageId;
                mStatusReportIds.remove(token);
            }
        }
        try {
            mImsService.acknowledgeSmsReport(mSlotId, token, messageRef, result);
        } catch (RemoteException e) {
            Log.w(TAG, "acknowledgeSmsReport: " + e.getMessage());
        }
    }

    @Override
    public String getSmsFormat() {
        try {
            String format = mImsService.getSmsFormat(mSlotId);
            if (format != null) {
                return format;
            }
        } catch (RemoteException e) {
            Log.w(TAG, "getSmsFormat: " + e.getMessage());
        }
        return super.getSmsFormat();
    }
}
