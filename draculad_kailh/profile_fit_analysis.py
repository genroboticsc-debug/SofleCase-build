from __future__ import annotations

"""Analysis-only compact fit-point reconstruction study for the Kailh meniscus."""

import json
from pathlib import Path

from build123d import Edge, Face, Vector, Wire, export_step, import_step

from candidate_joint import X_START, _resolved
from reference_canal_probe import find_profile_contour, find_profile_face, isolate_right_solder

TARGET_AREA = 0.9075354150773971
TARGET_LENGTH = 4.851046962108225


def refine_extremum(edge: Edge, left: float, right: float, maximize: bool) -> float:
    for _ in range(80):
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
    count = 4000
    ts = [i / count for i in range(count + 1)]
    zs = [edge.position_at(t).Z for t in ts]
    found = []
    for i in range(1, count):
        is_min = zs[i] <= zs[i - 1] and zs[i] <= zs[i + 1]
        is_max = zs[i] >= zs[i - 1] and zs[i] >= zs[i + 1]
        if is_min or is_max:
            t = refine_extremum(edge, ts[i - 1], ts[i + 1], maximize=is_max)
            if not found or abs(t - found[-1][1]) > 1.0e-4:
                found.append(("max" if is_max else "min", t))
    return found


def nearest_parameter(edge: Edge, yz: tuple[float, float]) -> float:
    target_y, target_z = yz
    # Golden-section minimization over normalized edge parameter.
    left, right = 0.0, 1.0
    phi = (5.0**0.5 - 1.0) / 2.0
    c = right - phi * (right - left)
    d = left + phi * (right - left)

    def score(t):
        p = edge.position_at(t)
        return (p.Y - target_y) ** 2 + (p.Z - target_z) ** 2

    fc, fd = score(c), score(d)
    for _ in range(100):
        if fc < fd:
            right, d, fd = d, c, fc
            c = right - phi * (right - left)
            fc = score(c)
        else:
            left, c, fc = c, d, fd
            d = left + phi * (right - left)
            fd = score(d)
    return (left + right) / 2.0


def make_candidate(name: str, ref: Edge, parameters: list[float], tangent_mode: str):
    points = [ref.position_at(t) for t in parameters]
    fixed_points = [Vector(X_START, p.Y, p.Z) for p in points]
    tangents = None
    if tangent_mode == "ends":
        tangents = []
        for t in (parameters[0], parameters[-1]):
            v = Vector(ref.tangent_at(t)).normalized()
            tangents.append(Vector(0, v.Y, v.Z))
    elif tangent_mode == "all":
        tangents = []
        for t in parameters:
            v = Vector(ref.tangent_at(t)).normalized()
            tangents.append(Vector(0, v.Y, v.Z))

    curve = Edge.make_spline(
        fixed_points,
        tangents=tangents,
        scale=True,
        tol=1.0e-9,
    )
    face = Face(Wire([curve, Edge.make_line(curve.end_point(), curve.start_point())]))

    samples = 1000
    errors = []
    for i in range(samples + 1):
        t = i / samples
        a = ref.position_at(t)
        b = curve.position_at(t)
        errors.append(((a.Y - b.Y) ** 2 + (a.Z - b.Z) ** 2) ** 0.5)

    return curve, face, {
        "name": name,
        "point_count": len(parameters),
        "tangent_mode": tangent_mode,
        "parameters": parameters,
        "points_yz": [[p.Y, p.Z] for p in points],
        "tangents_yz": (
            None
            if tangents is None
            else [[v.Y, v.Z] for v in tangents]
        ),
        "length": float(_resolved(curve.length)),
        "length_error": float(_resolved(curve.length)) - TARGET_LENGTH,
        "area": float(_resolved(face.area)),
        "area_error": float(_resolved(face.area)) - TARGET_AREA,
        "area_error_percent": 100.0 * (float(_resolved(face.area)) - TARGET_AREA) / TARGET_AREA,
        "sample_rms_distance": (sum(e * e for e in errors) / len(errors)) ** 0.5,
        "sample_max_distance": max(errors),
    }


def main():
    out = Path("artifacts/profile_fit")
    out.mkdir(parents=True, exist_ok=True)
    reference = import_step("reference.step")
    _, solder = isolate_right_solder(reference)
    profile = find_profile_face(solder)
    contour = find_profile_contour(profile)

    extrema = interior_extrema(contour)
    if len(extrema) != 3:
        raise RuntimeError(f"expected two valleys and one crest, got {extrema}")
    extrema_parameters = [t for _, t in extrema]

    # Two exact shoulder datums are boundaries between the reference rolling
    # surface families and therefore meaningful engineering stations.
    shoulders = [
        nearest_parameter(contour, (6.05561815841550, 1.52891560478045)),
        nearest_parameter(contour, (4.12087378923583, 1.57689067591220)),
    ]

    five = [0.0, *extrema_parameters, 1.0]
    seven = sorted([0.0, *extrema_parameters, *shoulders, 1.0])
    cases = []
    for label, params in [("five", five), ("seven", seven)]:
        for tangent_mode in ["none", "ends", "all"]:
            curve, face, report = make_candidate(
                f"{label}_{tangent_mode}", contour, params, tangent_mode
            )
            cases.append(report)
            export_step(face, out / f"{label}_{tangent_mode}.step")

    exact = {
        "target_area": TARGET_AREA,
        "target_length_nominal": TARGET_LENGTH,
        "imported_contour_length": float(_resolved(contour.length)),
        "extrema": [
            {
                "kind": kind,
                "parameter": t,
                "point": list(contour.position_at(t).to_tuple()),
                "tangent": list(Vector(contour.tangent_at(t)).normalized().to_tuple()),
            }
            for kind, t in extrema
        ],
        "shoulder_parameters": shoulders,
        "cases": cases,
    }
    (out / "profile_fit_analysis.json").write_text(json.dumps(exact, indent=2))
    print(json.dumps(exact, indent=2))


if __name__ == "__main__":
    main()
