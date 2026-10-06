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

package android.os;

/** Samsung's SystemProperties wrapper, as used by EpdgService. */
public final class SemSystemProperties {
    private SemSystemProperties() {}

    public static String get(String key, String def) {
        // EpdgService reloads epdg_apns_conf.xml into its database when Samsung's
        // firmware version changes. AOSP has no ro.build.PDA; use the build time, so
        // that every ROM build counts as a firmware update.
        if ("ro.build.PDA".equals(key)) {
            key = "ro.build.date.utc";
        }
        return SystemProperties.get(key, def);
    }
}
