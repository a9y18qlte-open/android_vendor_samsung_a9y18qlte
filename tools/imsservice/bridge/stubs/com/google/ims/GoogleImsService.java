package com.google.ims;

import android.content.Context;
import android.os.RemoteException;
import android.telephony.ims.aidl.IImsSmsListener;

/** Compile-time stub of the class in imsservice.apk; not packaged. */
public class GoogleImsService {
    public static GoogleImsService getInstance(Context context) { return null; }
    public void setSmsListener(int phoneId, IImsSmsListener l) throws RemoteException {}
    public void onSmsReady(int phoneId) throws RemoteException {}
    public void sendSms(int phoneId, int token, int messageRef, String format, String smsc,
            boolean isRetry, byte[] pdu) throws RemoteException {}
    public void acknowledgeSms(int phoneId, int token, int messageRef, int result)
            throws RemoteException {}
    public void acknowledgeSmsReport(int phoneId, int token, int messageRef, int result)
            throws RemoteException {}
    public String getSmsFormat(int phoneId) throws RemoteException { return null; }
}
