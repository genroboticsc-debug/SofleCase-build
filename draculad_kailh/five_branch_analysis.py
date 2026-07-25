from __future__ import annotations

"""Analysis-only five-branch reconstruction of the Kailh solder meniscus.

The reference is used only to extract a compact engineering description:
six rolling-branch boundary points, one interior design point per branch, and
six endpoint tangent directions.  No poles, knots, pcurves, faces, or sampled
sections are stored in production geometry.
"""

import json
import math
from pathlib import Path

from build123d import (
    Edge,
    Face,
    GeomType,
    Transition,
    Vector,
    Wire,
    export_step,
    extrude,
    import_step,
    sweep,
)

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    PAD_Z_MAX,
    TOP_Z,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    closed_wire,
    pad_face,
)
from reference_canal_probe import find_profile_contour, find_profile_face, isolate_right_solder
from swept_cutter_candidate import corner_cutter_face

# Exact feature datums identified from the five R0.375 rolling surface families.
BOUNDARIES_YZ = (
    (3.90576480246421, 1.75000000000000),
    (4.12087378923583, 1.57689067591220),
    (4.70235196349251, 1.43492679304686),
    (5.46862670809520, 1.38160563822046),
    (6.05561815841550, 1.52891560478045),
    (6.26449204350269, 1.75000000000000),
)
INTERIORS_YZ = (
    (4.023984011820813, 1.714516755368501),
    (4.248311078629781, 0.712055311788421),
    (5.069210154715189, 1.561664633732182),
    (5.911019073670400, 0.740430800709123),
    (6.166310258452469, 1.708854666930473),
)
TARGET_AREA = 0.9075354150773971
TARGET_CONTOUR_LENGTH = 4.851046962108225


def scalar(value) -> float:
    return float(_resolved(value))


def nearest_parameter(edge: Edge, yz: tuple[float, float]) -> float:
    target_y, target_z = yz
    sample_count = 12000
    best_i = min(
        range(sample_count + 1),
        key=lambda i: (
            (edge.position_at(i / sample_count).Y - target_y) ** 2
            + (edge.position_at(i / sample_count).Z - target_z) ** 2
        ),
    )
    left = max(0.0, (best_i - 2) / sample_count)
    right = min(1.0, (best_i + 2) / sample_count)
    phi = (5.0**0.5 - 1.0) / 2.0

    def score(t: float) -> float:
        p = edge.position_at(t)
        return (p.Y - target_y) ** 2 + (p.Z - target_z) ** 2

    c = right - phi * (right - left)
    d = left + phi * (right - left)
    fc, fd = score(c), score(d)
    for _ in range(100):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - phi * (right - left)
            fc = score(c)
        else:
            left, c, fc = c, d, fd
            d = left + phi * (right - left)
            fd = score(d)
    return (left + right) / 2.0


def local_vector(vector: Vector) -> Vector:
    v = Vector(0.0, vector.Y, vector.Z)
    return v.normalized()


def branch_curve(
    start: tuple[float, float],
    interior: tuple[float, float],
    end: tuple[float, float],
    start_tangent: Vector,
    end_tangent: Vector,
    x: float,
) -> Edge:
    return Edge.make_spline(
        [
            Vector(x, start[0], start[1]),
            Vector(x, interior[0], interior[1]),
            Vector(x, end[0], end[1]),
        ],
        tangents=[local_vector(start_tangent), local_vector(end_tangent)],
        scale=True,
        tol=1.0e-9,
    )


def candidate_profile(
    boundary_tangents: list[Vector], x: float
) -> tuple[list[Edge], Face]:
    branches = [
        branch_curve(
            BOUNDARIES_YZ[i],
            INTERIORS_YZ[i],
            BOUNDARIES_YZ[i + 1],
            boundary_tangents[i],
            boundary_tangents[i + 1],
            x,
        )
        for i in range(5)
    ]
    top = Edge.make_line(branches[-1].end_point(), branches[0].start_point())
    return branches, Face(closed_wire([*branches, top]))


def shape_metrics(shape) -> dict:
    bb = shape.bounding_box()
    return {
        "valid": bool(_resolved(shape.is_valid)),
        "volume": scalar(shape.volume),
        "area": scalar(shape.area),
        "solids": len(shape.solids()),
        "shells": len(shape.shells()),
        "faces": len(shape.faces()),
        "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z],
    }


def sample_bidirectional_distance(reference: Edge, generated: Wire) -> dict:
    # Parameter-correspondence is deliberately not assumed.  Each sampled point
    # is compared by exact point-to-curve distance in both directions.
    samples = 400
    forward = []
    reverse = []
    for i in range(samples + 1):
        t = i / samples
        point = reference.position_at(t)
        forward.append(generated.distance_to(point))
        point = generated.position_at(t)
        reverse.append(reference.distance_to(point))
    values = forward + reverse
    return {
        "sample_count_each_direction": samples + 1,
        "max_distance": max(values),
        "rms_distance": math.sqrt(sum(v * v for v in values) / len(values)),
    }


def attempt_native_fillet(raw, terminal_edges):
    try:
        result = raw.fillet(MAIN_ROLL_RADIUS, terminal_edges)
        return result, {"success": True, **shape_metrics(result)}
    except Exception as exc:
        return None, {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def attempt_wire_sweep(raw, branches, transition: Transition):
    try:
        path = Wire(branches)
        section = corner_cutter_face(branches[0], MAIN_ROLL_RADIUS)
        cutter = sweep(
            sections=section,
            path=path,
            is_frenet=True,
            transition=transition,
            clean=True,
        )
        result = raw.cut(cutter).clean()
        return result, {
            "success": True,
            "cutter": shape_metrics(cutter),
            "rolled": shape_metrics(result),
        }
    except Exception as exc:
        return None, {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def attempt_union_sweep(raw, branches):
    rows = []
    cutters = []
    try:
        for index, branch in enumerate(branches):
            section = corner_cutter_face(branch, MAIN_ROLL_RADIUS)
            cutter = sweep(
                sections=section,
                path=branch,
                is_frenet=True,
                clean=True,
            )
            rows.append({"index": index, **shape_metrics(cutter)})
            cutters.append(cutter)
        union = cutters[0].fuse(*cutters[1:]).clean()
        result = raw.cut(union).clean()
        return result, {
            "success": True,
            "individual": rows,
            "union": shape_metrics(union),
            "rolled": shape_metrics(result),
        }
    except Exception as exc:
        return None, {
            "success": False,
            "individual": rows,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    out = Path("artifacts/five_branch")
    out.mkdir(parents=True, exist_ok=True)
    reference = import_step("reference.step")
    _, solder = isolate_right_solder(reference)
    reference_face = find_profile_face(solder)
    contour = find_profile_contour(reference_face)

    boundary_parameters = [nearest_parameter(contour, p) for p in BOUNDARIES_YZ]
    interior_parameters = [nearest_parameter(contour, p) for p in INTERIORS_YZ]
    boundary_tangents = [
        local_vector(Vector(contour.tangent_at(t))) for t in boundary_parameters
    ]

    branches_start, profile = candidate_profile(boundary_tangents, X_START)
    branches_end, _ = candidate_profile(boundary_tangents, UNFILLETED_END_X)
    generated_wire = Wire(branches_start)
    raw = extrude(profile, UNFILLETED_END_X - X_START, dir=(1, 0, 0), clean=True)

    report: dict = {
        "analysis_only_reference_extraction": True,
        "boundary_parameters": boundary_parameters,
        "interior_parameters": interior_parameters,
        "boundaries_yz": BOUNDARIES_YZ,
        "interiors_yz": INTERIORS_YZ,
        "boundary_tangents_yz": [[v.Y, v.Z] for v in boundary_tangents],
        "reference_imported_contour_length": scalar(contour.length),
        "target_contour_length": TARGET_CONTOUR_LENGTH,
        "generated_branch_lengths": [scalar(edge.length) for edge in branches_start],
        "generated_contour_length": sum(scalar(edge.length) for edge in branches_start),
        "target_profile_area": TARGET_AREA,
        "generated_profile_area": scalar(profile.area),
        "profile_area_error_percent": 100.0 * (scalar(profile.area) - TARGET_AREA) / TARGET_AREA,
        "distance": sample_bidirectional_distance(contour, generated_wire),
        "raw": shape_metrics(raw),
        "strategies": {},
    }
    export_step(profile, out / "five_branch_profile.step")
    export_step(raw, out / "five_branch_raw.step")

    result, evidence = attempt_native_fillet(raw, branches_end)
    report["strategies"]["native_fillet"] = evidence
    if result is not None:
        export_step(result, out / "rolled_native_fillet.step")

    for name, transition in (
        ("wire_transformed", Transition.TRANSFORMED),
        ("wire_round", Transition.ROUND),
        ("wire_right", Transition.RIGHT),
    ):
        result, evidence = attempt_wire_sweep(raw, branches_end, transition)
        report["strategies"][name] = evidence
        if result is not None:
            export_step(result, out / f"rolled_{name}.step")

    result, evidence = attempt_union_sweep(raw, branches_end)
    report["strategies"]["individual_union"] = evidence
    if result is not None:
        export_step(result, out / "rolled_individual_union.step")

    # Exact skew pad is kept separate in this campaign so main-roll topology is
    # not obscured by a coincident planar fusion.
    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1), clean=True)
    report["pad"] = shape_metrics(pad)
    export_step(pad, out / "exact_skew_pad.step")

    (out / "five_branch_analysis.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
