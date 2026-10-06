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

/**
 * Samsung framework class imsservice reads carrier (CSC) features from; not part of AOSP.
 * Reports every feature as unset, which is what Samsung's own implementation returns for
 * a key the CSC does not define.
 */
public final class SemCscFeature {
    private static final SemCscFeature sInstance = new SemCscFeature();

    private SemCscFeature() {}

    public static SemCscFeature getInstance() {
        return sInstance;
    }

    public boolean getBoolean(String tag) {
        return false;
    }

    public boolean getBoolean(int phoneId, String tag) {
        return false;
    }

    public boolean getBoolean(String tag, boolean defaultValue) {
        return defaultValue;
    }

    public boolean getBoolean(int phoneId, String tag, boolean defaultValue) {
        return defaultValue;
    }

    public String getString(String tag) {
        return "";
    }

    public String getString(int phoneId, String tag) {
        return "";
    }

    public String getString(String tag, String defaultValue) {
        return defaultValue;
    }

    public String getString(int phoneId, String tag, String defaultValue) {
        return defaultValue;
    }

    public int getInt(String tag) {
        return 0;
    }

    public int getInt(int phoneId, String tag) {
        return 0;
    }

    public int getInt(String tag, int defaultValue) {
        return defaultValue;
    }

    public int getInt(int phoneId, String tag, int defaultValue) {
        return defaultValue;
    }
}
