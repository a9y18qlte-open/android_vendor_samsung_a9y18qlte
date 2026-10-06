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
import android.telephony.ims.ImsService;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsConfigImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.util.Log;
import android.util.SparseArray;

import com.android.ims.internal.IImsFeatureStatusCallback;
import com.android.internal.telephony.ims.ImsConfigCompatAdapter;
import com.android.internal.telephony.ims.ImsRegistrationCompatAdapter;
import com.android.internal.telephony.ims.MmTelInterfaceAdapter;
import com.google.ims.GoogleImsService;

/**
 * Android 12 ImsService in front of Samsung's compat MMTelFeature.
 *
 * Does in-process what the framework's ImsServiceControllerCompat does in the phone
 * process, so that the MmTelFeature can also expose SMS over IMS: the compat interface
 * has no SMS, and Samsung's SMS bridge (GoogleImsService) is only reachable in-process.
 */
public class GoogleImsServiceAdapter extends ImsService {
    private static final String TAG = "GoogleImsServiceAdapter";

    private final SparseArray<BridgeMmTelFeature> mMmTelFeatures = new SparseArray<>();
    private final SparseArray<ImsRegistrationCompatAdapter> mRegistrations = new SparseArray<>();
    private final SparseArray<ImsConfigCompatAdapter> mConfigs = new SparseArray<>();

    @Override
    public MmTelFeature createMmTelFeature(int slotId) {
        synchronized (mMmTelFeatures) {
            BridgeMmTelFeature feature = mMmTelFeatures.get(slotId);
            if (feature != null) {
                return feature;
            }
            GoogleImsService imsService = GoogleImsService.getInstance(getApplicationContext());
            ImsMmtelFeature compatFeature = new ImsMmtelFeature(imsService, slotId);
            compatFeature.setContext(this);
            compatFeature.setSlotId(slotId);

            feature = new BridgeMmTelFeature(this, slotId,
                    new MmTelInterfaceAdapter(slotId, compatFeature.getBinder().asBinder()),
                    imsService);
            ImsRegistrationCompatAdapter registration = new ImsRegistrationCompatAdapter();
            try {
                feature.addRegistrationAdapter(registration);
            } catch (RemoteException e) {
                // Only stores the adapter; never thrown.
            }
            mRegistrations.put(slotId, registration);
            mConfigs.put(slotId, new ImsConfigCompatAdapter(feature.getOldConfigInterface()));
            mMmTelFeatures.put(slotId, feature);

            final BridgeMmTelFeature f = feature;
            compatFeature.addImsFeatureStatusCallback(new IImsFeatureStatusCallback.Stub() {
                @Override
                public void notifyImsFeatureStatus(int state) {
                    f.setFeatureState(state);
                }
            });
            Log.i(TAG, "createMmTelFeature: slot " + slotId);
            return feature;
        }
    }

    @Override
    public ImsRegistrationImplBase getRegistration(int slotId) {
        synchronized (mMmTelFeatures) {
            return mRegistrations.get(slotId);
        }
    }

    @Override
    public ImsConfigImplBase getConfig(int slotId) {
        synchronized (mMmTelFeatures) {
            return mConfigs.get(slotId);
        }
    }

    @Override
    public void enableIms(int slotId) {
        BridgeMmTelFeature feature = getFeature(slotId);
        if (feature == null) {
            return;
        }
        try {
            feature.enableIms();
        } catch (RemoteException e) {
            Log.w(TAG, "enableIms: " + e.getMessage());
        }
    }

    @Override
    public void disableIms(int slotId) {
        BridgeMmTelFeature feature = getFeature(slotId);
        if (feature == null) {
            return;
        }
        try {
            feature.disableIms();
        } catch (RemoteException e) {
            Log.w(TAG, "disableIms: " + e.getMessage());
        }
    }

    private BridgeMmTelFeature getFeature(int slotId) {
        synchronized (mMmTelFeatures) {
            BridgeMmTelFeature feature = mMmTelFeatures.get(slotId);
            if (feature == null) {
                Log.w(TAG, "No MmTelFeature for slot " + slotId);
            }
            return feature;
        }
    }
}
