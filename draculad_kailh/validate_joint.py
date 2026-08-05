from __future__ import annotations

"""Independent one-body Kailh solder-joint validation.

The reference is downloaded separately from the pinned source commit. This
script never participates in production geometry construction.
"""

import json
import math
from pathlib import Path
import traceback

from build123d import Plane, export_stl, import_step


def resolved(value):
    return value() if callable(value) else value


def scalar(value) -> float:
    return float(resolved(value))


def total_volume(shape) -> float:
    return sum(scalar(s.volume) for s in shape.solids())


def bbox_values(shape) -> list[float]:
    b = shape.bounding_box()
    return [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z]


def com_values(shape) -> list[float]:
    c = resolved(shape.center_of_mass)
    return [c.X, c.Y, c.Z]


def shape_metrics(shape) -> dict:
    return {
        "volume": total_volume(shape),
        "area": scalar(shape.area),
        "bbox": bbox_values(shape),
        "com": com_values(shape),
        "valid": bool(resolved(shape.is_valid)),
        "solid_count": len(shape.solids()),
        "face_count": len(shape.faces()),
    }


def select_right_solder(reference):
    candidates = []
    for i, solid in enumerate(reference.solids()):
        b = solid.bounding_box()
        volume = scalar(solid.volume)
        if 1.0 < volume < 3.0 and b.min.X > 4.0:
            candidates.append((i, solid))
    if len(candidates) != 1:
        rows = [(i, scalar(s.volume), bbox_values(s)) for i, s in candidates]
        raise RuntimeError(f"unable to isolate right solder: {rows}")
    return candidates[0]


def exact_cut_volume(a, b) -> tuple[float, dict]:
    info = {
        "success": False,
        "error": None,
        "valid": None,
        "solid_count": None,
        "signed_volume": None,
    }
    try:
        result = a.cut(b)
        info["valid"] = bool(resolved(result.is_valid))
        info["solid_count"] = len(result.solids())
        value = total_volume(result)
        info["signed_volume"] = value
        info["success"] = math.isfinite(value) and value >= -1.0e-10
        return max(0.0, value), info
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        return math.inf, info


def section_diagnostics(shape, xs: list[float]) -> list[dict]:
    rows = []
    for x in xs:
        row = {"x": x}
        try:
            sections = shape.section(Plane(origin=(x, 0, 0), z_dir=(1, 0, 0)))
            faces = list(sections.faces()) if hasattr(sections, "faces") else []
            edges = list(sections.edges()) if hasattr(sections, "edges") else []
            row.update(
                {
                    "success": True,
                    "faces": len(faces),
                    "edges": len(edges),
                    "face_area": sum(scalar(f.area) for f in faces),
                    "edge_length": sum(scalar(e.length) for e in edges),
                }
            )
        except Exception as exc:
            row.update({"success": False, "error": f"{type(exc).__name__}: {exc}"})
        rows.append(row)
    return rows


def mesh_boolean_diagnostic(ref_solid, gen_solid, out: Path) -> dict:
    data = {
        "success": False,
        "official": False,
        "method": "manifold mesh diagnostic only",
    }
    try:
        import trimesh

        export_stl(
            ref_solid,
            out / "reference_joint.stl",
            tolerance=0.005,
            angular_tolerance=0.02,
        )
        export_stl(
            gen_solid,
            out / "generated_joint.stl",
            tolerance=0.005,
            angular_tolerance=0.02,
        )
        r = trimesh.load_mesh(out / "reference_joint.stl", force="mesh", process=True)
        g = trimesh.load_mesh(out / "generated_joint.stl", force="mesh", process=True)
        r_minus_g = trimesh.boolean.difference([r, g], engine="manifold")
        g_minus_r = trimesh.boolean.difference([g, r], engine="manifold")
        av = abs(float(r_minus_g.volume)) if r_minus_g is not None else 0.0
        bv = abs(float(g_minus_r.volume)) if g_minus_r is not None else 0.0
        data.update(
            {
                "success": True,
                "reference_watertight": bool(r.is_watertight),
                "generated_watertight": bool(g.is_watertight),
                "reference_mesh_volume": abs(float(r.volume)),
                "generated_mesh_volume": abs(float(g.volume)),
                "a_minus_b": av,
                "b_minus_a": bv,
                "xor_volume": av + bv,
                "xor_percent_reference_mesh": 100.0
                * (av + bv)
                / abs(float(r.volume)),
            }
        )
    except Exception as exc:
        data["error"] = f"{type(exc).__name__}: {exc}"
        data["traceback"] = traceback.format_exc()
    return data


def main() -> None:
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    reference = import_step("reference.step")
    generated = import_step(out / "candidate_joint.step")
    ref_index, ref = select_right_solder(reference)
    gen_solids = generated.solids()
    if len(gen_solids) != 1:
        raise RuntimeError(f"candidate must contain one solid, got {len(gen_solids)}")
    gen = gen_solids[0]

    a_minus_b, a_info = exact_cut_volume(ref, gen)
    b_minus_a, b_info = exact_cut_volume(gen, ref)
    boolean_success = a_info["success"] and b_info["success"]
    xor_volume = a_minus_b + b_minus_a if boolean_success else math.inf
    ref_volume = scalar(ref.volume)
    xor_percent = 100.0 * xor_volume / ref_volume if boolean_success else math.inf

    rm = shape_metrics(ref)
    gm = shape_metrics(gen)
    report = {
        "reference_solid_index": ref_index,
        "reference": rm,
        "generated": gm,
        "volume_error_percent": 100.0
        * abs(gm["volume"] - rm["volume"])
        / abs(rm["volume"]),
        "area_error_percent": 100.0
        * abs(gm["area"] - rm["area"])
        / abs(rm["area"]),
        "bbox_abs_diff": [abs(a - b) for a, b in zip(rm["bbox"], gm["bbox"])],
        "com_shift": math.dist(rm["com"], gm["com"]),
        "a_minus_b": a_minus_b,
        "b_minus_a": b_minus_a,
        "xor_volume": xor_volume,
        "xor_percent": xor_percent,
        "boolean_success": boolean_success,
        "fallback_used": False,
        "a_minus_b_info": a_info,
        "b_minus_a_info": b_info,
        "reference_sections": section_diagnostics(
            ref, [6.60, 6.6351914878, 6.70, 6.80, 6.90, 7.00, 7.01, 7.05, 7.08]
        ),
        "generated_sections": section_diagnostics(
            gen, [6.60, 6.6351914878, 6.70, 6.80, 6.90, 7.00, 7.01, 7.05, 7.08]
        ),
        "mesh_diagnostic": mesh_boolean_diagnostic(ref, gen, out),
        "target_percent": 0.01,
        "pass": boolean_success and xor_percent < 0.01,
    }
    (out / "joint_validation.json").write_text(
        json.dumps(report, indent=2, allow_nan=True)
    )
    print(json.dumps(report, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()
