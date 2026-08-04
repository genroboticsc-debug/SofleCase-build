from __future__ import annotations

import json
import platform
import subprocess
import sys
import traceback
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference" / "top.stl"
GENERATED = ROOT / "generated"
GENERATED.mkdir(parents=True, exist_ok=True)


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def command_output(command: list[str]) -> str:
    try:
        return subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def write_environment() -> None:
    info = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            name: package_version(name)
            for name in (
                "build123d",
                "cadquery-ocp",
                "cadquery-ocp-novtk",
                "manifold3d",
                "trimesh",
                "numpy",
                "scipy",
                "shapely",
            )
        },
        "arial_font_matches": command_output(["fc-match", "Arial"]),
        "arial_font_files": command_output(
            ["bash", "-lc", "fc-list | grep -i '/Arial' | head -20"]
        ),
    }
    (GENERATED / "environment.json").write_text(
        json.dumps(info, indent=2),
        encoding="utf-8",
    )


def run() -> int:
    write_environment()
    status = {
        "strict_srot": False,
        "generation": False,
        "validation": False,
        "overall_pass": False,
    }
    try:
        from strict_srot_check import run as run_strict_srot

        srot_report = run_strict_srot()
        status["strict_srot"] = bool(srot_report.get("pass"))

        from top_parametric import export_model

        step_path, stl_path = export_model(GENERATED)
        status["generation"] = step_path.exists() and stl_path.exists()

        from validate_top import validate

        validation_report = validate(REFERENCE, GENERATED)
        status["validation"] = True
        status["validation_pass"] = bool(
            validation_report.get("overall_pass")
        )
        status["overall_pass"] = bool(
            status["strict_srot"]
            and status["generation"]
            and status["validation_pass"]
        )
    except Exception as exc:
        status["exception"] = f"{type(exc).__name__}: {exc}"
        status["traceback"] = traceback.format_exc()

    (GENERATED / "run_status.json").write_text(
        json.dumps(status, indent=2),
        encoding="utf-8",
    )

    archive = GENERATED / "top_exact_validation_outputs.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(GENERATED.iterdir()):
            if path == archive or not path.is_file():
                continue
            zf.write(path, path.name)
        for path in (
            ROOT / "top_parametric.py",
            ROOT / "validate_top.py",
            ROOT / "strict_srot_check.py",
            REFERENCE,
        ):
            if path.exists():
                zf.write(path, path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
