from pathlib import Path

ROOT = Path("build-src/CareerPilotAI")


def remove_exact_line(relative_path: str, exact_line: str) -> None:
    path = ROOT / relative_path
    lines = path.read_text(encoding="utf-8").splitlines()
    count = lines.count(exact_line)
    if count != 1:
        raise SystemExit(
            f"Refusing approximate edit: expected exactly one {exact_line!r} in {relative_path}; found {count}"
        )
    lines.remove(exact_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


for screen in (
    "AutomationScreen.kt",
    "CopilotScreen.kt",
    "DashboardScreen.kt",
    "SettingsScreen.kt",
):
    remove_exact_line(
        f"app/src/main/java/com/careerpilot/ai/ui/screens/{screen}",
        "import androidx.compose.foundation.layout.weight",
    )

print("Applied exact source fixes: removed four obsolete explicit weight imports")
