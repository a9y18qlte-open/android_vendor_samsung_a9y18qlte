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

import android.os.RemoteException;
import android.telephony.SmsManager;
import android.telephony.ims.aidl.IImsSmsListener;
import android.telephony.ims.stub.ImsSmsImplBase;

import com.sec.ims.sms.ISmsServiceEventListener;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ImsSmsImpl was built against Android 10's IImsSmsListener (plus a Samsung-only
 * onSendSmsResponse). Its calls to methods Android 12 no longer has are redirected here.
 *
 * SmsServiceModule's acks to ImsSmsImpl also pass through here: ImsSmsImpl only
 * recognises SIP failure codes and reports an SMS the network answered with an
 * RP-ERROR as sent, so the message shows as sent but never arrives.
 */
public final class SmsListenerCompat {
    // RP-ERROR, network to MS (3GPP TS 24.011 8.2.2).
    private static final int RP_MTI_ERROR_N2MS = 5;
    // SmsServiceModule reports an RP-ERROR as this plus the RP-Cause
    // (GsmSmsUtil.RIL_CODE_RP_ERROR), with the TPDU it carried as the data.
    private static final int RIL_CODE_RP_ERROR = 0x8000;

    // TP-MR of a message the network answered with an RP-ERROR -> its RP-Cause.
    private static final Map<Integer, Integer> sRpErrors = new ConcurrentHashMap<>();

    private SmsListenerCompat() {}

    public static void onReceiveSMSAck(ISmsServiceEventListener listener, int messageRef,
            int reasonCode, String contentType, byte[] pdu, int retryAfter)
            throws RemoteException {
        if (reasonCode > RIL_CODE_RP_ERROR && reasonCode <= RIL_CODE_RP_ERROR + 0xff) {
            sRpErrors.put(messageRef, reasonCode - RIL_CODE_RP_ERROR);
        } else if (pdu != null && pdu.length >= 4 && (pdu[0] & 0x07) == RP_MTI_ERROR_N2MS) {
            // The raw RP-ERROR: RP-MTI, RP-MR, then the RP-Cause element (length, cause).
            sRpErrors.put(messageRef, pdu[3] & 0x7f);
        } else {
            sRpErrors.remove(messageRef);
        }
        listener.onReceiveSMSAck(messageRef, reasonCode, contentType, pdu, retryAfter);
    }

    public static void onSendSmsResult(IImsSmsListener listener, int token, int messageRef,
            int status, int reason) throws RemoteException {
        onSendSmsResult(listener, token, messageRef, status, reason,
                ImsSmsImplBase.RESULT_NO_NETWORK_ERROR);
    }

    public static void onSendSmsResponse(IImsSmsListener listener, int token, int messageRef,
            int status, int reason, int errorCause, int errorClass) throws RemoteException {
        onSendSmsResult(listener, token, messageRef, status, reason,
                status == ImsSmsImplBase.SEND_STATUS_OK
                        ? ImsSmsImplBase.RESULT_NO_NETWORK_ERROR : errorCause);
    }

    private static void onSendSmsResult(IImsSmsListener listener, int token, int messageRef,
            int status, int reason, int networkErrorCode) throws RemoteException {
        Integer rpCause = sRpErrors.remove(messageRef);
        if (rpCause != null && status == ImsSmsImplBase.SEND_STATUS_OK) {
            status = ImsSmsImplBase.SEND_STATUS_ERROR;
            reason = SmsManager.RESULT_ERROR_GENERIC_FAILURE;
            networkErrorCode = rpCause;
        }
        listener.onSendSmsResult(token, messageRef, status, reason, networkErrorCode);
    }

    public static void onSmsStatusReportReceived(IImsSmsListener listener, int token,
            int messageRef, String format, byte[] pdu) throws RemoteException {
        if (listener instanceof BridgeSms.Listener) {
            ((BridgeSms.Listener) listener).onSmsStatusReportReceived(token, messageRef, format,
                    pdu);
            return;
        }
        listener.onSmsStatusReportReceived(token, format, pdu);
    }
}
