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

import java.io.FileInputStream;
import java.io.IOException;
import java.util.zip.CRC32;

/** Samsung's SystemProperties wrapper, as used by EpdgService. */
public final class SemSystemProperties {
    // EpdgService and its MAPCON provider reload these into their databases when
    // Samsung's firmware version (ro.build.PDA) changes. AOSP has none, and the build
    // date is not updated by every build, so it is a checksum of the files themselves:
    // they are reloaded exactly when they change.
    private static final String[] DATA_FILES = {
            "/system/etc/epdg_apns_conf.xml",
            "/system/etc/mapconprovider.xml",
    };
    private static String sDataVersion;

    private SemSystemProperties() {}

    public static String get(String key, String def) {
        if ("ro.build.PDA".equals(key)) {
            return getDataVersion();
        }
        return SystemProperties.get(key, def);
    }

    private static synchronized String getDataVersion() {
        if (sDataVersion == null) {
            CRC32 crc = new CRC32();
            byte[] buf = new byte[65536];
            for (String path : DATA_FILES) {
                try (FileInputStream in = new FileInputStream(path)) {
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        crc.update(buf, 0, n);
                    }
                } catch (IOException e) {
                    // Missing file: it simply does not count.
                }
            }
            sDataVersion = "data-" + Long.toHexString(crc.getValue());
        }
        return sDataVersion;
    }
}
