from pathlib import Path

path = Path("build-src/CareerPilotAI/app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt")
text = path.read_text(encoding="utf-8")
old = '.joinToString(", ") { it.safeText() }.trim(", ")'
new = '.joinToString(", ") { it.safeText() }.trim(\',\', \' \')'
count = text.count(old)
if count != 2:
    raise SystemExit(f"Expected exactly 2 invalid trim calls, found {count}")
text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
if text.count(new) != 2 or old in text:
    raise SystemExit("CareerPilot 2.3 compile fix verification failed")
print("CareerPilot 2.3 Kotlin trim fixes applied successfully")
