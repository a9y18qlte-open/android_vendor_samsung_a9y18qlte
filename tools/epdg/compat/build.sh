#!/bin/bash
# Compile the EpdgService compat classes into a dex.
# Usage: build.sh <android source root with a built framework> <out dir>
set -e
TOP=$(realpath "$1"); OUT=$(realpath -m "$2"); HERE=$(dirname "$(realpath "$0")")
JDK=$TOP/prebuilts/jdk/jdk11/linux-x86/bin
IM=$TOP/out/soong/.intermediates
CP=$IM/frameworks/base/framework/android_common/turbine-combined/framework.jar
CP=$CP:$IM/frameworks/opt/telephony/telephony-common/android_common/turbine-combined/telephony-common.jar
for m in framework-wifi framework-connectivity; do
    CP=$CP:$(find $IM/packages/modules -path "*/$m/android_common*/turbine-combined/$m.jar" | head -1)
done
rm -rf "$OUT"; mkdir -p "$OUT/classes"
"$JDK/javac" --release 8 -nowarn -encoding UTF-8 -cp "$CP" \
    -d "$OUT/classes" $(find "$HERE/src" -name '*.java')
"$JDK/java" -cp "$TOP/prebuilts/r8/r8.jar" com.android.tools.r8.D8 --release --min-api 31 --lib "$TOP/prebuilts/sdk/31/system/android.jar" \
    --output "$OUT" $(find "$OUT/classes" -name '*.class')
ls -l "$OUT/classes.dex"
