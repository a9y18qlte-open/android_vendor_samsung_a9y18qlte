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

package android.net.shared;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

/** The Android 10 helpers EpdgService uses; Android 12 moved them into the modules. */
public final class Inet4AddressUtils {
    private Inet4AddressUtils() {}

    public static Inet4Address intToInet4AddressHTH(int hostAddress) {
        byte[] addressBytes = {
            (byte) ((hostAddress >> 24) & 0xff), (byte) ((hostAddress >> 16) & 0xff),
            (byte) ((hostAddress >> 8) & 0xff), (byte) (hostAddress & 0xff)
        };
        try {
            return (Inet4Address) InetAddress.getByAddress(addressBytes);
        } catch (UnknownHostException e) {
            throw new AssertionError();
        }
    }

    public static int inet4AddressToIntHTH(Inet4Address inetAddr) {
        byte[] addr = inetAddr.getAddress();
        return ((addr[0] & 0xff) << 24) | ((addr[1] & 0xff) << 16)
                | ((addr[2] & 0xff) << 8) | (addr[3] & 0xff);
    }

    public static int prefixLengthToV4NetmaskIntHTH(int prefixLength) {
        if (prefixLength < 0 || prefixLength > 32) {
            throw new IllegalArgumentException("Invalid prefix length (0 <= prefix <= 32)");
        }
        return prefixLength == 0 ? 0 : 0xffffffff << (32 - prefixLength);
    }
}
