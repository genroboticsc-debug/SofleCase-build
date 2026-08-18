from __future__ import annotations

from pathlib import Path

import certify
import certify_v2

ROOT = Path(__file__).resolve().parent
certify_v2.SOURCE_FILES = certify_v2.SOURCE_FILES + (
    ROOT / "exact_mount_patch.py",
    ROOT / "exact_domain_patch.py",
)
certify.static_srot = certify_v2.strict_source_closure_audit

if __name__ == "__main__":
    raise SystemExit(certify.main())
