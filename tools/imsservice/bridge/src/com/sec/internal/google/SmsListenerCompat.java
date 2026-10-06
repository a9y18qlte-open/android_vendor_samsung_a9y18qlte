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
import android.telephony.ims.aidl.IImsSmsListener;
import android.telephony.ims.stub.ImsSmsImplBase;

/**
 * ImsSmsImpl was built against Android 10's IImsSmsListener (plus a Samsung-only
 * onSendSmsResponse). Its calls to methods Android 12 no longer has are redirected here.
 */
public final class SmsListenerCompat {
    private SmsListenerCompat() {}

    public static void onSendSmsResult(IImsSmsListener listener, int token, int messageRef,
            int status, int reason) throws RemoteException {
        listener.onSendSmsResult(token, messageRef, status, reason,
                ImsSmsImplBase.RESULT_NO_NETWORK_ERROR);
    }

    public static void onSendSmsResponse(IImsSmsListener listener, int token, int messageRef,
            int status, int reason, int errorCause, int errorClass) throws RemoteException {
        listener.onSendSmsResult(token, messageRef, status, reason,
                status == ImsSmsImplBase.SEND_STATUS_OK
                        ? ImsSmsImplBase.RESULT_NO_NETWORK_ERROR : errorCause);
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
