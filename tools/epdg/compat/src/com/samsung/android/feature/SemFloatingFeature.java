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

package com.samsung.android.feature;

import android.os.SystemProperties;

/**
 * Samsung floating features EpdgService reads. Only the dual IMS mode is used; on AOSP it
 * comes from persist.ril.config.dualims (device vendor.prop), like for imsservice.
 */
public final class SemFloatingFeature {
    private static final SemFloatingFeature sInstance = new SemFloatingFeature();

    private SemFloatingFeature() {}

    public static SemFloatingFeature getInstance() {
        return sInstance;
    }

    public String getString(String tag, String def) {
        if ("SEC_FLOATING_FEATURE_COMMON_CONFIG_DUAL_IMS".equals(tag)) {
            return SystemProperties.get("persist.ril.config.dualims", def);
        }
        return def;
    }
}
