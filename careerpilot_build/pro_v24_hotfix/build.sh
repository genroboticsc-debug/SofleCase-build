#!/usr/bin/env bash
set -euo pipefail

ROOT="$PWD"
LOG="$ROOT/careerpilot-pro-24-build.log"
SOURCE="$ROOT/source.tar.xz"
BUILD_DIR="$ROOT/build-src"
APP_DIR="$BUILD_DIR/CareerPilotAI"

exec > >(tee "$LOG") 2>&1

rm -rf "$BUILD_DIR" "$SOURCE" "$ROOT"/v22.* "$ROOT"/v23.* "$ROOT"/v24.*

cat careerpilot_build/pro_v2/chunks/part{00..23} > "$SOURCE"
echo "8801d9153864d3da6d90075fbda17c49b84d2a427d2349baf32551370e767b24  $SOURCE" | sha256sum -c -
mkdir -p "$BUILD_DIR"
tar -xJf "$SOURCE" -C "$BUILD_DIR"

python careerpilot_build/pro_v2/apply_compiler_fixes.py
python careerpilot_build/pro_v2/apply_compiler_fixes_2.py

cat careerpilot_build/pro_v22_patch/part{00..04}.b64 > v22.xz.b64
echo "a96b940b66a7bfb30a1447eb8d60acf149d2978d1f92dac086f4ecc0655c2811  v22.xz.b64" | sha256sum -c -
base64 -d v22.xz.b64 > v22.xz
echo "0eac18187e9688ad8979c0db32f5e09382332214f87f186b0d404400a1c58320  v22.xz" | sha256sum -c -
xz -dc v22.xz > v22.patch
echo "f3e4a974ce1731ab7f9227bcf7c1f0a37cb0c678ad88f25f3d0783b5a04f13f4  v22.patch" | sha256sum -c -
(cd "$APP_DIR" && patch -p4 --forward --batch < "$ROOT/v22.patch")

cat careerpilot_build/pro_v23_patch/part{00..04}.b64 > v23.xz.b64
echo "27d032546b249e190e7c6dbfb6d4e9f53c3d000c763198f91de9349dedb8cd92  v23.xz.b64" | sha256sum -c -
base64 -d v23.xz.b64 > v23.xz
echo "6a76da41686e4ec56b91e30179e71220f19cafd7e7db6e5f5a1580edf74ed575  v23.xz" | sha256sum -c -
xz -dc v23.xz > v23.patch
echo "ad600e430e4c0785e01e00215494eecbf8732f5e80a4371de4b5f1f5cd185589  v23.patch" | sha256sum -c -
(cd "$APP_DIR" && patch -p1 --forward --batch < "$ROOT/v23.patch")
python careerpilot_build/pro_v23_patch/apply_compile_fixes.py

cat > v24-chunks.sha256 <<'HASHES'
cacf48c41e095f782c251e02a6f9173a950eacefcbd593bb044a8d5dfc644f41  careerpilot_build/pro_v24_hotfix/part00.b64
0193b76bff9e25c9eb155c3fa1f68d3724af7bc51c72293c5795568606d4f3c9  careerpilot_build/pro_v24_hotfix/part01.b64
003f1c507d23123d56595e1c992105944d0a1dea70ceea59ec13c74045e153af  careerpilot_build/pro_v24_hotfix/part02.b64
HASHES
sha256sum -c v24-chunks.sha256
cat careerpilot_build/pro_v24_hotfix/part{00..02}.b64 > v24.xz.b64
echo "981303b868edbff3c11d6612840ecc32b0c43f73fac70db29b1a70542b7c544c  v24.xz.b64" | sha256sum -c -
base64 -d v24.xz.b64 > v24.xz
echo "fa6f43f5cc27d8e8f69bd927eb4f9459260c5a6c4b6015ff482cbf8f7eb0df64  v24.xz" | sha256sum -c -
xz -dc v24.xz > v24.patch
echo "93dedfa995800ede2dab98a5cad1ea934b2ea6925a9bbdbbde6ff1e2ef301ea3  v24.patch" | sha256sum -c -
(cd "$APP_DIR" && patch -p1 --forward --batch < "$ROOT/v24.patch")

# FileProvider resource omitted by the original patch. Keep exposure limited to app files/cache.
mkdir -p "$APP_DIR/app/src/main/res/xml"
cat > "$APP_DIR/app/src/main/res/xml/file_paths.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <files-path name="careerpilot_files" path="." />
    <cache-path name="careerpilot_cache" path="." />
</paths>
XML

grep -q 'versionName = "2.4.0-beta"' "$APP_DIR/app/build.gradle.kts"
grep -q 'ACTION_PROCESS_QUEUE' "$APP_DIR/app/src/main/java/com/careerpilot/ai/automation/AutomationForegroundService.kt"
grep -q 'copyBaseResume' "$APP_DIR/app/src/main/java/com/careerpilot/ai/data/ArtifactRepository.kt"
grep -q 'createShareableZip' "$APP_DIR/app/src/main/java/com/careerpilot/ai/data/ArtifactRepository.kt"
grep -q 'shareApplicationPack' "$APP_DIR/app/src/main/java/com/careerpilot/ai/ui/AppViewModel.kt"
grep -q 'repairLegacySearchState' "$APP_DIR/app/src/main/java/com/careerpilot/ai/workflow/WorkflowRepository.kt"
! grep -q 'markAutopilotSearch()' <(sed -n '/fun searchJobsNow/,/fun syncJobs/p' "$APP_DIR/app/src/main/java/com/careerpilot/ai/ui/AppViewModel.kt")

ok=0
for url in \
  'https://remotive.com/api/remote-jobs?search=mechanical&limit=1' \
  'https://jobicy.com/api/v2/remote-jobs?count=1&tag=engineering' \
  'https://remoteok.com/api' \
  'https://www.arbeitnow.com/api/job-board-api'; do
  code=$(curl -L --max-time 20 -A 'CareerPilotAI/2.4' -o /tmp/feed.out -s -w '%{http_code}' "$url" || true)
  bytes=$(wc -c < /tmp/feed.out 2>/dev/null || echo 0)
  echo "SEARCH_ROUTE http=$code bytes=$bytes url=$url"
  [[ "$code" == "200" && "$bytes" -gt 50 ]] && ok=$((ok+1))
done
echo "SEARCH_ROUTES_AVAILABLE=$ok/4"
test "$ok" -ge 3

(
  cd "$APP_DIR"
  gradle --no-daemon --stacktrace clean testDebugUnitTest assembleDebug
)

cp "$APP_DIR/app/build/outputs/apk/debug/app-debug.apk" "$ROOT/CareerPilotAI-Pro-2.4.apk"
APKSIGNER="$ANDROID_HOME/build-tools/36.0.0/apksigner"
AAPT="$ANDROID_HOME/build-tools/36.0.0/aapt"
{
  echo '=== APK SIGNATURE ==='
  "$APKSIGNER" verify --verbose --print-certs "$ROOT/CareerPilotAI-Pro-2.4.apk"
  echo '=== APK PACKAGE METADATA ==='
  "$AAPT" dump badging "$ROOT/CareerPilotAI-Pro-2.4.apk"
  echo '=== APK SHA256 ==='
  sha256sum "$ROOT/CareerPilotAI-Pro-2.4.apk"
  echo '=== APK ZIP INTEGRITY ==='
  unzip -t "$ROOT/CareerPilotAI-Pro-2.4.apk" | tail -n 2
} | tee "$ROOT/CareerPilotAI-Pro-2.4.validation.txt"
sha256sum "$ROOT/CareerPilotAI-Pro-2.4.apk" > "$ROOT/CareerPilotAI-Pro-2.4.apk.sha256"
tar --exclude='.gradle' --exclude='**/build' -cJf "$ROOT/CareerPilotAI-Pro-2.4-source.tar.xz" -C "$BUILD_DIR" CareerPilotAI
sha256sum "$ROOT/CareerPilotAI-Pro-2.4-source.tar.xz" > "$ROOT/CareerPilotAI-Pro-2.4-source.tar.xz.sha256"
