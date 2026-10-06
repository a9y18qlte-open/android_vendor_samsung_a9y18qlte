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

/** Samsung CSC features; none are set on AOSP. */
public final class SemCscFeature {
    private static final SemCscFeature sInstance = new SemCscFeature();

    private SemCscFeature() {}

    public static SemCscFeature getInstance() {
        return sInstance;
    }

    public boolean getBoolean(String tag, boolean def) {
        return def;
    }

    public boolean getBoolean(int phoneId, String tag) {
        return false;
    }
}
