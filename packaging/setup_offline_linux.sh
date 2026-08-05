#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
VENV_DIR="${VENV_DIR:-$ROOT/venv-linux}"
WHEELHOUSE="$ROOT/wheelhouse/linux_cp313_x86_64"
REQUIREMENTS="$ROOT/requirements-exact-linux-cp313.txt"

command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  echo "Required interpreter not found: $PYTHON_BIN" >&2
  exit 1
}
[[ -d "$WHEELHOUSE" ]] || { echo "Wheelhouse missing: $WHEELHOUSE" >&2; exit 1; }

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" -r "$REQUIREMENTS"
"$VENV_DIR/bin/python" -m pip check
"$VENV_DIR/bin/python" - <<'PY'
import build123d
import OCP
print("build123d", build123d.__version__)
print("OCP/OpenCascade import OK")
PY

echo "Offline Linux CAD environment ready at $VENV_DIR"
