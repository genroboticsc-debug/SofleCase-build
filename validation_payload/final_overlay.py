from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("validation_run")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch target not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


for relative in (
    "scripts/midplate_reference.py",
    "scripts/midplate_model.py",
    "validation/validate.py",
):
    path = ROOT / relative
    path.write_text(path.read_text(encoding="utf-8").replace(".is_valid()", ".is_valid"), encoding="utf-8")

model = ROOT / "scripts/midplate_model.py"
model.write_text(
    model.read_text(encoding="utf-8").replace(
        'FEATURE_COUNTS["inner_wires"]',
        '(FEATURE_COUNTS["closed_wires"] - 1)',
    ),
    encoding="utf-8",
)
replace_once(
    model,
    '''    bbox = body.bounding_box()\n    if abs((bbox.max.Y - bbox.min.Y) - thickness_mm) > 1.0e-9:\n        raise RuntimeError("Generated thickness does not equal 3.000 mm")\n''',
    '''    vertex_y = [float(vertex.Y) for vertex in body.vertices()]\n    y_min = min(vertex_y)\n    y_max = max(vertex_y)\n    if abs(y_min - float(DESIGN["y_min_mm"])) > 1.0e-9 or abs(y_max - float(DESIGN["y_max_mm"])) > 1.0e-9:\n        raise RuntimeError(\n            f"Generated datum planes differ from exact design: y_min={y_min:.17g}, y_max={y_max:.17g}"\n        )\n''',
)

validator = ROOT / "validation/validate.py"
replace_once(
    validator,
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut\n",
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut\nfrom OCP.BRepGProp import BRepGProp\nfrom OCP.GProp import GProp_GProps\n",
)
replace_once(
    validator,
    "EXPECTED_VOLUME_MM3 = 29059.63965979482\nEXPECTED_AREA_MM2 = 21520.538770864157\n",
    "EXPECTED_VOLUME_MM3 = 29036.084275777324\nEXPECTED_AREA_MM2 = 21505.504694885698\n",
)
replace_once(
    validator,
    '''    bmin = vec(bb.min)\n    bmax = vec(bb.max)\n    return {\n''',
    '''    bmin = vec(bb.min)\n    bmax = vec(bb.max)\n    vertex_coordinates = np.array(\n        [[float(vertex.X), float(vertex.Y), float(vertex.Z)] for vertex in shape.vertices()],\n        dtype=float,\n    )\n    vertex_min = vertex_coordinates.min(axis=0)\n    vertex_max = vertex_coordinates.max(axis=0)\n    return {\n''',
)
replace_once(
    validator,
    '''        "bbox_size_mm": bmax - bmin,\n        "body_count": len(shape.solids()),\n''',
    '''        "bbox_size_mm": bmax - bmin,\n        "vertex_min_mm": vertex_min,\n        "vertex_max_mm": vertex_max,\n        "body_count": len(shape.solids()),\n''',
)
replace_once(
    validator,
    '''    result = operation.Shape()\n    if result.IsNull():\n        return 0.0\n    return float(Shape.cast(result).volume)\n''',
    '''    result = operation.Shape()\n    if result.IsNull():\n        return 0.0\n    properties = GProp_GProps()\n    BRepGProp.VolumeProperties_s(result, properties)\n    return float(properties.Mass())\n''',
)
replace_once(
    validator,
    '''        "reference_exact_y_datums": abs(rp["bbox_min_mm"][1] - EXPECTED_Y_MIN) < 1.0e-8 and abs(rp["bbox_max_mm"][1] - EXPECTED_Y_MAX) < 1.0e-8,\n        "generated_exact_y_datums": abs(gp["bbox_min_mm"][1] - EXPECTED_Y_MIN) < 1.0e-8 and abs(gp["bbox_max_mm"][1] - EXPECTED_Y_MAX) < 1.0e-8,\n''',
    '''        "reference_exact_y_datums": abs(rp["vertex_min_mm"][1] - EXPECTED_Y_MIN) < 1.0e-9 and abs(rp["vertex_max_mm"][1] - EXPECTED_Y_MAX) < 1.0e-9,\n        "generated_exact_y_datums": abs(gp["vertex_min_mm"][1] - EXPECTED_Y_MIN) < 1.0e-9 and abs(gp["vertex_max_mm"][1] - EXPECTED_Y_MAX) < 1.0e-9,\n''',
)
replace_once(
    validator,
    '''    }\n    metrics["checks"] = checks\n''',
    '''    }\n    checks = {name: bool(value) for name, value in checks.items()}\n    metrics["checks"] = checks\n''',
)

manifest_path = ROOT / "source/geometry_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["exact_unit_profile_metrics"] = {
    "area_mm2": 9678.694758592441,
    "perimeter_mm": 716.0383925669388,
    "centroid_xy_mm": [-5.570548104791537, -7.143261597964015],
    "bbox_min_xy_mm": manifest["exact_unit_profile_metrics"]["bbox_min_xy_mm"],
    "bbox_max_xy_mm": manifest["exact_unit_profile_metrics"]["bbox_max_xy_mm"],
    "provenance": "Pinned Build123d 0.11.1 / OCCT 7.9.3.1 direct import of byte-exact authoritative DXF",
}
manifest["exact_3mm_reference_metrics"] = {
    "volume_mm3": 29036.084275777324,
    "surface_area_mm2": 21505.504694885698,
    "center_of_mass_global_mm": [-5.570548104791537, -4.35, 7.143261597964015],
    "thickness_mm": 3.0,
    "y_min_mm": -5.85,
    "y_max_mm": -2.85,
}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print("FINAL_OVERLAY=APPLIED")
