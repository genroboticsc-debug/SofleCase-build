"""Sweep exact segmented-circle topology for the bottom-left boss.

A full OpenCascade circle canonicalizes its seam. Two-arc and four-arc closed
profiles preserve the identical analytic circle while exposing explicit
parametric seam locations that can reproduce a different valid STL triangle
fan without changing any recovered dimension.
"""

from __future__ import annotations

import json
import math

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
PHASES = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 22.5, 30.0, 45.0)
TOPOLOGIES = (2, 4)
ROOT = validator.ROOT / "generated" / "bottom_left_segmented_circle_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_CLIPPED_BOSS = tp._clipped_boss_solid
BASE_NAME, BASE_X, BASE_Z, BASE_Y0, BASE_Y1 = tp.BOSSES[0]

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")


def point(angle_degrees: float) -> tuple[float, float]:
    angle = math.radians(angle_degrees)
    return (
        BASE_X + tp.BOSS_RADIUS * math.cos(angle),
        BASE_Z + tp.BOSS_RADIUS * math.sin(angle),
    )


def segmented_boss(arc_count: int, phase_degrees: float):
    with tp.BuildSketch(tp.xz_plane(BASE_Y0)) as profile:
        with tp.BuildLine():
            if arc_count == 2:
                p0 = point(phase_degrees)
                p1 = point(phase_degrees + 90.0)
                p2 = point(phase_degrees + 180.0)
                p3 = point(phase_degrees + 270.0)
                tp.ThreePointArc(p0, p1, p2)
                tp.ThreePointArc(p2, p3, p0)
            elif arc_count == 4:
                cardinal = [point(phase_degrees + 90.0 * index) for index in range(4)]
                midpoint = [point(phase_degrees + 45.0 + 90.0 * index) for index in range(4)]
                for index in range(4):
                    tp.ThreePointArc(
                        cardinal[index],
                        midpoint[index],
                        cardinal[(index + 1) % 4],
                    )
            else:
                raise ValueError(arc_count)
        tp.make_face()
    cylinder = tp.extrude(profile.sketch.face(), amount=-(BASE_Y1 - BASE_Y0))
    envelope = tp._solid_from_sketch(tp.outer_profile_sketch(), BASE_Y0, BASE_Y1)
    clipped = cylinder & envelope
    if len(clipped.solids()) != 1 or not clipped.is_valid:
        raise RuntimeError(
            f"Segmented bottom-left boss invalid: arcs={arc_count}, phase={phase_degrees}"
        )
    return clipped


def install_candidate(arc_count: int, phase_degrees: float) -> None:
    candidate = segmented_boss(arc_count, phase_degrees)

    def isolated_clipped_boss(x: float, z: float, y0: float, y1: float):
        if (
            abs(x - BASE_X) <= 1.0e-12
            and abs(z - BASE_Z) <= 1.0e-12
            and abs(y0 - BASE_Y0) <= 1.0e-12
            and abs(y1 - BASE_Y1) <= 1.0e-12
        ):
            return candidate
        return ORIGINAL_CLIPPED_BOSS(x, z, y0, y1)

    tp._clipped_boss_solid = isolated_clipped_boss


rows = []
for arc_count in TOPOLOGIES:
    for phase_degrees in PHASES:
        tag = f"arcs_{arc_count}_phase_{phase_degrees:.6f}".replace(".", "p")
        validator.OUTPUT = ROOT / tag
        print(
            f"=== segmented BL boss arcs={arc_count} phase={phase_degrees:.6f} deg ===",
            flush=True,
        )
        try:
            install_candidate(arc_count, phase_degrees)
            row = validator.validate_candidate(LINEAR, reference_raw, reference)
            row.update(
                {
                    "bottom_left_boss_arc_count": arc_count,
                    "bottom_left_boss_phase_degrees": phase_degrees,
                    "geometry_change": "none; exact analytic circle",
                }
            )
        except Exception as exc:
            row = {
                "bottom_left_boss_arc_count": arc_count,
                "bottom_left_boss_phase_degrees": phase_degrees,
                "strict_pass": False,
                "exception": repr(exc),
            }
        finally:
            tp._clipped_boss_solid = ORIGINAL_CLIPPED_BOSS
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "base_bottom_left_boss": list(tp.BOSSES[0]),
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== SEGMENTED BOTTOM-LEFT CIRCLE SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
