from pathlib import Path

path = Path("build-src/CareerPilotAI/app/src/main/java/com/careerpilot/ai/discovery/JobDiscovery.kt")
text = path.read_text(encoding="utf-8")

for connector_type in ("ADZUNA", "JOOBLE", "BRAVE"):
    old = f'    override val type = "{connector_type}"'
    new = f'    val type = "{connector_type}"'
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one {connector_type} override, found {count}")
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("CareerPilot Pro 2 connector override fixes applied successfully")
