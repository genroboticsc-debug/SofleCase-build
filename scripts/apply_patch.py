from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
src = root / "NekoSpeak"
overlay = root / "app"

for file in overlay.rglob("*"):
    if file.is_file():
        target = src / file.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)

# App identity: coexist with the upstream APK instead of replacing its signature.
gradle = src / "app/build.gradle.kts"
text = gradle.read_text()
text = text.replace('versionCode = 16', 'versionCode = 17')
text = text.replace('versionName = "1.4.2"', 'versionName = "1.5.0-studio"')
if 'applicationIdSuffix = ".studio"' not in text:
    text = text.replace(
        'buildTypes {\n        release {',
        'buildTypes {\n        debug {\n            applicationIdSuffix = ".studio"\n            versionNameSuffix = "-pixel9a"\n            isDebuggable = true\n        }\n        release {'
    )
if 'material-icons-extended' not in text:
    text = text.replace(
        'implementation("androidx.compose.material3:material3")',
        'implementation("androidx.compose.material3:material3")\n    implementation("androidx.compose.material:material-icons-extended")'
    )
gradle.write_text(text)

# Use the exact current Malayalam ONNX file rather than probing nonexistent quantized paths.
models = src / "app/src/main/java/com/nekospeak/tts/data/ModelRepository.kt"
text = models.read_text()
text = text.replace('Offline Malayalam neural voice. Quantized ONNX model optimized for local Android inference.',
                    'Offline Malayalam neural voice using a compact 114 MB ONNX model for local Android inference.')
text = text.replace(
'''                    "$MAL_BASE/onnx/model_quantized.onnx?download=true",
                    "Malayalam VITS quantized model",
                    mirrors = listOf(
                        "$MAL_BASE/onnx/model_int8.onnx?download=true",
                        "$MAL_BASE/onnx/model_uint8.onnx?download=true",
                        "$MAL_BASE/onnx/model.onnx?download=true",
                        "$MAL_BASE/model.onnx?download=true"
                    ),''',
'''                    "$MAL_BASE/model.onnx?download=true",
                    "Malayalam VITS ONNX model (114 MB)",
                    mirrors = emptyList(),'''
)
models.write_text(text)

# More useful model download errors.
manager = src / "app/src/main/java/com/nekospeak/tts/ui/screens/ModelManagerScreen.kt"
text = manager.read_text()
text = text.replace(
    'downloadError = "Download failed. Check connection."',
    'downloadError = ModelRepository.getLastError(modelInfo.id) ?: "Download failed"'
)
manager.write_text(text)

# Malayalam speed controls in the existing settings screen.
settings = src / "app/src/main/java/com/nekospeak/tts/ui/screens/SettingsScreen.kt"
text = settings.read_text()
text = text.replace(
    'if (currentModel == "kitten_nano" || currentModel.startsWith("piper")) {',
    'if (currentModel == "kitten_nano" || currentModel == "mms_malayalam" || currentModel.startsWith("piper")) {'
)
settings.write_text(text)

# Wake lock for long-form disk-streamed generation.
manifest = src / "app/src/main/AndroidManifest.xml"
text = manifest.read_text()
if 'android.permission.WAKE_LOCK' not in text:
    text = text.replace(
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.WAKE_LOCK" />'
    )
manifest.write_text(text)

# Distinct app name.
strings = src / "app/src/main/res/values/strings.xml"
if strings.exists():
    text = strings.read_text()
    text = text.replace('<string name="app_name">NekoSpeak</string>', '<string name="app_name">NekoSpeak Studio</string>')
    strings.write_text(text)

print("Applied NekoSpeak Studio overlay")
