#!/bin/bash
# Compile the IMS bridge into a dex.
# Usage: build.sh <android source root with a built framework> <out dir>
set -e
TOP=$(realpath "$1"); OUT=$(realpath -m "$2"); HERE=$(dirname "$(realpath "$0")")
# Android 14's framework jars are Java 17 class files.
JDK=$TOP/prebuilts/jdk/jdk17/linux-x86/bin
[ -x "$JDK/javac" ] || JDK=$TOP/prebuilts/jdk/jdk11/linux-x86/bin
IM=$TOP/out/soong/.intermediates
# Android 14 puts the jars one directory deeper (android_common/<hash>/).
jar() { ls "$IM/$1"/android_common/turbine-combined/"$2" \
    "$IM/$1"/android_common/*/turbine-combined/"$2" 2>/dev/null | head -1; }
CP=$(jar frameworks/base/framework framework.jar)
CP=$CP:$(jar frameworks/opt/telephony/telephony-common telephony-common.jar)
CP=$CP:$(jar frameworks/opt/net/ims/ims-common ims-common.jar)
rm -rf "$OUT"; mkdir -p "$OUT/classes"
"$JDK/javac" --release 8 -nowarn -encoding UTF-8 -cp "$CP" \
    -d "$OUT/classes" $(find "$HERE/src" "$HERE/stubs" -name '*.java')
# Only the bridge goes into the dex; the stubs stand in for classes already in imsservice.apk.
rm -rf "$OUT/classes/com/google" "$OUT/classes/com/sec/ims" \
    "$OUT/classes/com/sec/internal/google/ImsMmtelFeature.class"
"$JDK/java" -cp "$TOP/prebuilts/r8/r8.jar" com.android.tools.r8.D8 --release --min-api 31 --lib "$TOP/prebuilts/sdk/31/system/android.jar" \
    --output "$OUT" $(find "$OUT/classes" -name '*.class')
ls -l "$OUT/classes.dex"
