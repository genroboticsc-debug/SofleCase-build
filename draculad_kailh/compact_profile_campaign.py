from __future__ import annotations

"""Analysis-only compact single-spline campaign for the Kailh solder meniscus.

The independent reference is used only to identify a small set of engineering
fit points: two top endpoints, two valleys, one central crest, and optional
shoulder/approach points. Candidate production curves are newly interpolated
Build123d splines. No reference poles, knots, multiplicities, weights, pcurves,
faces, dense sections, or sampled contours are stored or replayed.
"""

import json
import math
from pathlib import Path

from build123d import Edge, Face, Vector, Vertex, Wire, export_step, import_step

from candidate_joint import X_START, _resolved
from reference_canal_probe import find_profile_contour, find_profile_face, isolate_right_solder

TARGET_AREA = 0.9075354150773971
TARGET_LENGTH_DIAGNOSTIC = 4.851046962108225

# Optional engineering datums already identified from the five rolling-surface
# families. They are used only to locate compact fit points on the source curve.
SHOULDER_YZ = (
    (6.055620170693765, 1.528914787055315),
    (4.120875765999405, 1.576891528610150),
)
APPROACH_YZ = (
    (6.166239902250160, 1.708932910993792),
    (3.905767147044970, 1.750000000000000),
    (4.024082158937437, 1.714648621669562),
)


def scalar(value) -> float:
    return float(_resolved(value))


def refine_extremum(edge: Edge, left: float, right: float, maximize: bool) -> float:
    for _ in range(90):
        t1 = left + (right - left) / 3.0
        t2 = right - (right - left) / 3.0
        z1 = edge.position_at(t1).Z
        z2 = edge.position_at(t2).Z
        if maximize:
            if z1 < z2:
                left = t1
            else:
                right = t2
        else:
            if z1 > z2:
                left = t1
            else:
                right = t2
    return (left + right) / 2.0


def interior_extrema(edge: Edge) -> list[tuple[str, float]]:
    sample_count = 6000
    ts = [i / sample_count for i in range(sample_count + 1)]
    zs = [edge.position_at(t).Z for t in ts]
    found: list[tuple[str, float]] = []
    for i in range(1, sample_count):
        is_min = zs[i] <= zs[i - 1] and zs[i] <= zs[i + 1]
        is_max = zs[i] >= zs[i - 1] and zs[i] >= zs[i + 1]
        if not (is_min or is_max):
            continue
        t = refine_extremum(edge, ts[i - 1], ts[i + 1], maximize=is_max)
        if t <= 1.0e-5 or t >= 1.0 - 1.0e-5:
            continue
        if not found or abs(t - found[-1][1]) > 1.0e-4:
            found.append(("max" if is_max else "min", t))
    return found


def nearest_parameter(edge: Edge, yz: tuple[float, float]) -> float:
    target_y, target_z = yz
    sample_count = 10000
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


def local_point(point: Vector) -> Vector:
    return Vector(X_START, point.Y, point.Z)


def local_tangent(vector: Vector) -> Vector:
    return Vector(0, vector.Y, vector.Z).normalized()


def point_curve_distance(curve: Edge, point: Vector) -> float:
    return curve.distance_to(Vertex(point))


def bidirectional_distance(reference: Edge, generated: Edge, samples: int = 80) -> dict:
    values: list[float] = []
    for i in range(samples + 1):
        t = i / samples
        values.append(point_curve_distance(generated, local_point(reference.position_at(t))))
        values.append(reference.distance_to(Vertex(generated.position_at(t))))
    return {
        "samples_each_direction": samples + 1,
        "rms": math.sqrt(sum(value * value for value in values) / len(values)),
        "max": max(values),
    }


def candidate_curve(
    reference: Edge,
    parameters: list[float],
    tangent_mode: str,
    scale: bool,
) -> Edge:
    points = [local_point(reference.position_at(t)) for t in parameters]
    tangents = None
    if tangent_mode == "ends":
        tangents = [
            local_tangent(Vector(reference.tangent_at(parameters[0]))),
            local_tangent(Vector(reference.tangent_at(parameters[-1]))),
        ]
    return Edge.make_spline(
        points,
        tangents=tangents,
        scale=scale,
        tol=1.0e-9,
    )


def evaluate_case(
    out: Path,
    reference: Edge,
    name: str,
    parameters: list[float],
    tangent_mode: str,
    scale: bool,
) -> dict:
    report = {
        "name": name,
        "point_count": len(parameters),
        "tangent_mode": tangent_mode,
        "scale_tangents": scale,
        "analysis_parameters": parameters,
        "points_yz": [
            [reference.position_at(t).Y, reference.position_at(t).Z]
            for t in parameters
        ],
    }
    try:
        curve = candidate_curve(reference, parameters, tangent_mode, scale)
        face = Face(Wire([curve, Edge.make_line(curve.end_point(), curve.start_point())]))
        report.update(
            {
                "curve_valid": bool(_resolved(curve.is_valid)),
                "face_valid": bool(_resolved(face.is_valid)),
                "curve_length": scalar(curve.length),
                "length_error_diagnostic": scalar(curve.length) - TARGET_LENGTH_DIAGNOSTIC,
                "face_area": scalar(face.area),
                "area_error": scalar(face.area) - TARGET_AREA,
                "area_error_percent": 100.0
                * (scalar(face.area) - TARGET_AREA)
                / TARGET_AREA,
                "distance": bidirectional_distance(reference, curve),
                "success": True,
            }
        )
        export_step(face, out / f"{name}.step")
    except Exception as exc:
        report.update({"success": False, "error": f"{type(exc).__name__}: {exc}"})
    return report


def main() -> None:
    out = Path("artifacts/compact_profile")
    out.mkdir(parents=True, exist_ok=True)
    reference = import_step("reference.step")
    _, solder = isolate_right_solder(reference)
    profile = find_profile_face(solder)
    contour = find_profile_contour(profile)

    extrema = interior_extrema(contour)
    if len(extrema) != 3:
        raise RuntimeError(f"expected two valleys and one crest, got {extrema}")
    extrema_parameters = [parameter for _, parameter in extrema]
    shoulder_parameters = [nearest_parameter(contour, yz) for yz in SHOULDER_YZ]
    approach_parameters = [nearest_parameter(contour, yz) for yz in APPROACH_YZ]

    families = {
        "five": sorted([0.0, *extrema_parameters, 1.0]),
        "seven": sorted([0.0, *extrema_parameters, *shoulder_parameters, 1.0]),
        "nine": sorted(
            [
                0.0,
                *extrema_parameters,
                *shoulder_parameters,
                approach_parameters[0],
                approach_parameters[2],
                1.0,
            ]
        ),
    }
    # Keep only distinct parameters after numerical location.
    families = {
        name: [
            parameter
            for i, parameter in enumerate(parameters)
            if i == 0 or abs(parameter - parameters[i - 1]) > 1.0e-7
        ]
        for name, parameters in families.items()
    }

    base_report = {
        "analysis_only": True,
        "reference_profile_area": scalar(profile.area),
        "reference_contour_length_imported": scalar(contour.length),
        "target_area": TARGET_AREA,
        "extrema": [
            {
                "kind": kind,
                "parameter": parameter,
                "point": list(contour.position_at(parameter).to_tuple()),
                "tangent": list(Vector(contour.tangent_at(parameter)).normalized().to_tuple()),
            }
            for kind, parameter in extrema
        ],
        "shoulder_parameters": shoulder_parameters,
        "approach_parameters": approach_parameters,
        "families": families,
        "cases": [],
    }
    (out / "base_datums.json").write_text(json.dumps(base_report, indent=2))

    cases = []
    for family_name, parameters in families.items():
        for tangent_mode in ("none", "ends"):
            for scale in (True, False):
                name = f"{family_name}_{tangent_mode}_{'scaled' if scale else 'unit'}"
                cases.append(
                    evaluate_case(
                        out,
                        contour,
                        name,
                        parameters,
                        tangent_mode,
                        scale,
                    )
                )
    base_report["cases"] = cases
    successful = [case for case in cases if case.get("success") and case.get("face_valid")]
    successful.sort(
        key=lambda case: (
            abs(case["area_error_percent"]),
            case["distance"]["max"],
        )
    )
    base_report["ranking"] = [case["name"] for case in successful]
    (out / "compact_profile_campaign.json").write_text(json.dumps(base_report, indent=2))
    print(json.dumps(base_report, indent=2))


if __name__ == "__main__":
    main()
