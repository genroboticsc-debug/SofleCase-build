"""Machine-enforced Strict SROT audit for the parametric generator.

The audit is intentionally independent of numerical validation.  It verifies
that top_parametric.py is a standalone analytic Build123d feature tree and
rejects reference-file imports, mesh/B-Rep replay, serialization payloads,
external geometry helpers, hidden file reads, dynamic code execution, and
large coordinate tables that could encode sampled reference geometry.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "top_parametric.py"
REPORT = ROOT / "generated" / "strict_srot_report.json"

ALLOWED_IMPORT_ROOTS = {"__future__", "math", "pathlib", "build123d"}
FORBIDDEN_IMPORT_ROOTS = {
    "OCP",
    "cadquery",
    "trimesh",
    "meshio",
    "numpy",
    "scipy",
    "shapely",
    "manifold3d",
    "stl",
    "pickle",
    "marshal",
    "base64",
    "binascii",
    "json",
}
FORBIDDEN_CALL_TOKENS = {
    "import_stl",
    "import_step",
    "import_brep",
    "load_mesh",
    "load_stl",
    "load_step",
    "read_brep",
    "deserialize",
    "from_brep",
    "from_mesh",
    "eval",
    "exec",
    "compile",
    "__import__",
}
FORBIDDEN_READ_METHODS = {
    "open",
    "read",
    "read_text",
    "read_bytes",
    "load",
    "loads",
    "fromfile",
    "from_file",
}
REQUIRED_FUNCTIONS = {
    "outer_profile_sketch",
    "_main_rolling_body",
    "_top_right_clipped_cap",
    "_clipped_boss_solid",
    "_subtract_cylindrical_bore",
    "build_top",
    "export_model",
}
REQUIRED_FEATURE_MARKERS = {f"F{i:03d}" for i in range(1, 13)}


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def numeric_leaf_count(node: ast.AST) -> int:
    count = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
            if not isinstance(child.value, bool):
                count += 1
    return count


def docstring_nodes(tree: ast.AST) -> set[int]:
    nodes: set[int] = set()
    candidates: list[ast.AST] = [tree]
    candidates.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    for candidate in candidates:
        body = getattr(candidate, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            nodes.add(id(first.value))
    return nodes


def check_source() -> dict[str, Any]:
    source_text = SOURCE.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    tree = ast.parse(source_text, filename=str(SOURCE))
    docstrings = docstring_nodes(tree)

    violations: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "source_sha256": source_hash,
        "source_bytes": len(source_text.encode("utf-8")),
        "imports": [],
        "top_level_functions": [],
        "max_numeric_literal_container": 0,
        "feature_markers_found": sorted(
            marker for marker in REQUIRED_FEATURE_MARKERS if marker in source_text
        ),
    }

    def fail(rule: str, detail: str, node: ast.AST | None = None) -> None:
        record: dict[str, Any] = {"rule": rule, "detail": detail}
        if node is not None and hasattr(node, "lineno"):
            record["line"] = getattr(node, "lineno")
        violations.append(record)

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                imported_roots.add(root)
                evidence["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0] if module else ""
            imported_roots.add(root)
            evidence["imports"].append(module)

    for root in sorted(imported_roots):
        if root in FORBIDDEN_IMPORT_ROOTS:
            fail("SROT-IMPORT-FORBIDDEN", f"Forbidden geometry/data module: {root}")
        elif root not in ALLOWED_IMPORT_ROOTS:
            fail("SROT-IMPORT-EXTERNAL", f"Unapproved dependency in generator: {root}")

    top_level_functions = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    evidence["top_level_functions"] = sorted(top_level_functions)
    missing_functions = REQUIRED_FUNCTIONS - top_level_functions
    if missing_functions:
        fail(
            "SROT-FEATURE-TREE-MISSING",
            f"Missing required analytic feature functions: {sorted(missing_functions)}",
        )

    missing_markers = REQUIRED_FEATURE_MARKERS - set(evidence["feature_markers_found"])
    if missing_markers:
        fail(
            "SROT-FEATURE-ORDER-MISSING",
            f"Missing explicit feature-tree markers: {sorted(missing_markers)}",
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = dotted_name(node.func)
            terminal = name.rsplit(".", 1)[-1].lower()
            lowered = name.lower()
            if any(token in lowered for token in FORBIDDEN_CALL_TOKENS):
                fail("SROT-REPLAY-CALL", f"Forbidden call: {name}", node)
            if terminal in FORBIDDEN_READ_METHODS:
                fail("SROT-HIDDEN-FILE-READ", f"Generator reads external data: {name}", node)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bytes):
                fail("SROT-ENCODED-PAYLOAD", "Bytes payload embedded in generator", node)
            if isinstance(node.value, str) and id(node) not in docstrings:
                value = node.value.lower().replace("\\", "/")
                if "reference/" in value or "reference\\" in value:
                    fail(
                        "SROT-REFERENCE-PATH",
                        f"Reference path embedded in executable source: {node.value}",
                        node,
                    )
                if any(
                    token in value
                    for token in (
                        ".brep",
                        ".brp",
                        ".pickle",
                        ".pkl",
                        ".npy",
                        ".npz",
                        ".json",
                        "base64",
                    )
                ):
                    fail(
                        "SROT-SERIALIZED-GEOMETRY",
                        f"Serialized data indicator: {node.value}",
                        node,
                    )

        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            count = numeric_leaf_count(node)
            evidence["max_numeric_literal_container"] = max(
                evidence["max_numeric_literal_container"], count
            )
            if count > 32:
                fail(
                    "SROT-SAMPLED-COORDINATE-TABLE",
                    f"Literal container encodes {count} numeric values",
                    node,
                )

    build_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_top"
    ]
    if len(build_defs) != 1 or build_defs[0].args.args:
        fail(
            "SROT-STANDALONE-BUILD",
            "build_top must exist exactly once and require no reference input",
        )

    exporter_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "export_model"
    ]
    if len(exporter_defs) != 1:
        fail("SROT-EXPORTER", "Exactly one export_model function is required")

    report = {
        "standard": "STRICT-SROT-ANALYTIC-FEATURE-TREE-V1",
        "pass": not violations,
        "violations": violations,
        "evidence": evidence,
        "rules": {
            "reference_import_or_read": "forbidden",
            "mesh_brep_face_wire_pcurve_replay": "forbidden",
            "cached_or_serialized_geometry": "forbidden",
            "sampled_coordinate_profile_tables": "forbidden",
            "external_generator_dependencies": "build123d-only",
            "standalone_zero-input_feature_tree": "required",
            "explicit_F001_to_F012_order": "required",
        },
    }
    return report


def run(report_path: Path = REPORT) -> dict[str, Any]:
    report = check_source()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
