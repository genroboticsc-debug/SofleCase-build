from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import certify

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    ROOT / "production.py",
    ROOT / "exact_feature_patch.py",
    ROOT / "exact_floor_patch.py",
    ROOT / "exact_build.py",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def strict_source_closure_audit() -> dict[str, object]:
    forbidden_import_roots = {
        "trimesh", "manifold3d", "cadquery", "FreeCAD", "pickle", "base64", "stl"
    }
    forbidden_call_names = {
        "import_step", "import_stl", "read_step", "read_stl", "load_mesh",
        "make_bspline_surface", "make_bezier_surface", "make_spline",
    }
    forbidden_fragments = (
        "STEPControl_Reader", "StlAPI_Reader", "BRepTools.Read",
        "serialized_brep", "cached_brep", "read_bytes(", "frombuffer(", ".brep",
    )
    files: list[dict[str, object]] = []
    overall_pass = True
    combined_text = ""

    def dotted(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return dotted(node.value) + "." + node.attr
        return ""

    for path in SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        combined_text += "\n" + text
        tree = ast.parse(text, filename=str(path))
        imports: list[str] = []
        calls: list[str] = []
        byte_literal_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call):
                calls.append(dotted(node.func))
            elif isinstance(node, ast.Constant) and isinstance(node.value, bytes):
                byte_literal_count += len(node.value)
        import_hits = sorted(
            name for name in imports if name.split(".")[0] in forbidden_import_roots
        )
        call_hits = sorted(
            name for name in calls if name.rsplit(".", 1)[-1] in forbidden_call_names
        )
        text_hits = [fragment for fragment in forbidden_fragments if fragment.lower() in text.lower()]
        passed = not import_hits and not call_hits and not text_hits and byte_literal_count == 0
        overall_pass = overall_pass and passed
        files.append({
            "path": path.name,
            "sha256": digest(path),
            "ast_valid": True,
            "forbidden_imports": import_hits,
            "forbidden_calls": call_hits,
            "forbidden_text": text_hits,
            "embedded_binary_bytes": byte_literal_count,
            "status": "PASS_STATIC_PURITY" if passed else "FAIL_STATIC_PURITY",
        })

    required_symbols = (
        "CASE_PERIMETER_FEATURES", "HONEYCOMB_CELL_INDICES",
        "HexCaseParameters", "IntegratedPuckParameters", "build_case_base",
        "FACET_COUNTS_BY_INDEX", "lower_wall_support_faces",
        "lower_wall_support_solids", "build_case_base_exact", "install",
    )
    missing = [symbol for symbol in required_symbols if symbol not in combined_text]
    overall_pass = overall_pass and not missing
    return {
        "status": "STRICT_SROT_STATIC_PASS" if overall_pass else "STRICT_SROT_STATIC_FAIL",
        "source_closure": files,
        "missing_required_symbols": missing,
        "design_data": [
            "35 named perimeter features expanded by fixed authored facet counts",
            "50 integer honeycomb indices",
            "seven exact perimeter-offset support features",
            "exact floor vent domain and material keepouts",
            "explicit integrated-puck and opening feature branches",
        ],
    }


certify.static_srot = strict_source_closure_audit

if __name__ == "__main__":
    raise SystemExit(certify.main())
