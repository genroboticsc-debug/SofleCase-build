#!/usr/bin/env bash
set -euxo pipefail

SOURCE="CareerPilotAI_Pro_2.0.0_source.tar.xz"
LOG="$GITHUB_WORKSPACE/careerpilot-pro-21-build.log"
cat careerpilot_build/pro_v2/chunks/part{00..23} > "$SOURCE"
echo "8801d9153864d3da6d90075fbda17c49b84d2a427d2349baf32551370e767b24  $SOURCE" | sha256sum -c - | tee "$LOG"
mkdir -p build-src
tar -xJf "$SOURCE" -C build-src
python careerpilot_build/pro_v2/apply_compiler_fixes.py | tee -a "$LOG"
python careerpilot_build/pro_v2/apply_compiler_fixes_2.py | tee -a "$LOG"

cat > expected-patch-chunks.sha256 <<'HASHES'
4d5b785a89f373dfa85b635c5c9766c88ea105629b12d752ce214516ea1ad93d  careerpilot_build/pro_v21_patch/part00.b64
f9b1579b6018e87224405ab105f819d76966677eb2be7dee0ac483667e9cc2dd  careerpilot_build/pro_v21_patch/part01.b64
bdd5dbc56d012f0bdbdaabf2166f1a70d23be8361d0113cc2826addba358f58f  careerpilot_build/pro_v21_patch/part02.b64
HASHES
sha256sum -c expected-patch-chunks.sha256 | tee -a "$LOG"
cat careerpilot_build/pro_v21_patch/part{00..02}.b64 > careerpilot-21.patch.xz.b64
echo "b66b1aa34e2e2901b3d982baf9667d26b0743e60a4f3fafb36f2d5eea2b4916f  careerpilot-21.patch.xz.b64" | sha256sum -c - | tee -a "$LOG"
base64 -d careerpilot-21.patch.xz.b64 > careerpilot-21.patch.xz
echo "7244de3b9f49937d4a67f42f0ba9c784c34c54f59468c3f749f2ddf5ffbad275  careerpilot-21.patch.xz" | sha256sum -c - | tee -a "$LOG"
cd build-src/CareerPilotAI
xz -dc "$GITHUB_WORKSPACE/careerpilot-21.patch.xz" | patch -p1 --forward --batch | tee -a "$LOG"
grep -q 'versionName = "2.1.0-beta"' app/build.gradle.kts
grep -q 'RemotiveSearchConnector' app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt
grep -q 'openGoogleJobs' app/src/main/java/com/careerpilot/ai/ui/screens/JobsScreen.kt

set +e
gradle --no-daemon --stacktrace clean testDebugUnitTest assembleDebug 2>&1 | tee -a "$LOG"
status=${PIPESTATUS[0]}
set -e
exit "$status"
