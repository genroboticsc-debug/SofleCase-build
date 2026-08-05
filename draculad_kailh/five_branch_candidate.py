from __future__ import annotations

"""Reference-independent five-branch Kailh solder-joint builder.

The meniscus is expressed as five intentional rolling branches. Each branch is
controlled by its two engineering boundary datums, one interior shape datum,
and tangent directions at the shared boundaries. No STEP/STL import, B-Rep
replay, spline poles/knots, sampled sections, or correction bodies are used.
"""

import json
import os
from pathlib import Path

from build123d import (
    Edge,
    Face,
    Part,
    Transition,
    Vector,
    Wire,
    export_step,
    export_stl,
    extrude,
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
from swept_cutter_candidate import corner_cutter_face

# Exact compact design datums at the straight meniscus profile.
BOUNDARIES_YZ = (
    (3.905767147044970, 1.750000000000000),
    (4.120875765999405, 1.576891528610150),
    (4.702352901139571, 1.434925644480377),
    (5.468627665077156, 1.381606790580138),
    (6.055620170693765, 1.528914787055315),
    (6.264492043502691, 1.749999999979117),
)
INTERIORS_YZ = (
    (4.024082158937437, 1.714648621669562),
    (4.248331919821945, 0.712065277147395),
    (5.069233123298219, 1.562005051850265),
    (5.910925589337947, 0.740493655988842),
    (6.166239902250160, 1.708932910993792),
)

# Tangents are oriented from the left top boundary toward the right top
# boundary. The independent reference edge is parameterized in the opposite
# direction, so these are the exact reversed YZ directions.
BOUNDARY_TANGENTS_YZ = (
    (1.000000000000000, -1.420961144349527e-15),
    (0.396079668264180, -0.918216149056276),
    (0.774647135523515, 0.632393718679442),
    (0.769303894447745, -0.638883023712114),
    (0.376475523713166, 0.926426564841972),
    (0.999999999841332, 1.781394519034174e-05),
)
TARGET_PROFILE_AREA = 0.9075354150773971
TARGET_CONTOUR_LENGTH = 4.851046962108225


def metric(value):
    return _resolved(value)


def shape_metrics(shape) -> dict:
    bb = shape.bounding_box()
    return {
        "valid": bool(metric(shape.is_valid)),
        "volume": float(metric(shape.volume)),
        "area": float(metric(shape.area)),
        "solids": len(shape.solids()),
        "shells": len(shape.shells()),
        "faces": len(shape.faces()),
        "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z],
    }


def branch_edge(index: int, x: float) -> Edge:
    start = BOUNDARIES_YZ[index]
    interior = INTERIORS_YZ[index]
    end = BOUNDARIES_YZ[index + 1]
    tangent_start = BOUNDARY_TANGENTS_YZ[index]
    tangent_end = BOUNDARY_TANGENTS_YZ[index + 1]
    return Edge.make_spline(
        [
            Vector(x, start[0], start[1]),
            Vector(x, interior[0], interior[1]),
            Vector(x, end[0], end[1]),
        ],
        tangents=[
            Vector(0, tangent_start[0], tangent_start[1]),
            Vector(0, tangent_end[0], tangent_end[1]),
        ],
        scale=True,
        tol=1.0e-9,
    )


def profile_branches(x: float) -> list[Edge]:
    return [branch_edge(index, x) for index in range(5)]


def profile_face(x: float) -> Face:
    branches = profile_branches(x)
    top = Edge.make_line(branches[-1].end_point(), branches[0].start_point())
    return Face(closed_wire([*branches, top]))


def build_main_roll(strategy: str) -> tuple[Part, dict]:
    profile = profile_face(X_START)
    raw = extrude(
        profile,
        UNFILLETED_END_X - X_START,
        dir=(1, 0, 0),
        clean=True,
    )
    terminal = profile_branches(UNFILLETED_END_X)
    branch_lengths = [float(metric(edge.length)) for edge in profile_branches(X_START)]
    evidence = {
        "strategy": strategy,
        "profile_area": float(metric(profile.area)),
        "profile_area_error_percent": 100.0
        * (float(metric(profile.area)) - TARGET_PROFILE_AREA)
        / TARGET_PROFILE_AREA,
        "branch_lengths": branch_lengths,
        "contour_length": sum(branch_lengths),
        "contour_length_error": sum(branch_lengths) - TARGET_CONTOUR_LENGTH,
        "raw": shape_metrics(raw),
    }

    if strategy == "native_fillet":
        rolled = raw.fillet(MAIN_ROLL_RADIUS, terminal)
    elif strategy in {"wire_frenet", "wire_round", "wire_right"}:
        transition = {
            "wire_frenet": Transition.TRANSFORMED,
            "wire_round": Transition.ROUND,
            "wire_right": Transition.RIGHT,
        }[strategy]
        path = Wire(terminal)
        section = corner_cutter_face(terminal[0], MAIN_ROLL_RADIUS)
        cutter = sweep(
            sections=section,
            path=path,
            is_frenet=True,
            transition=transition,
            clean=True,
        )
        evidence["cutter"] = shape_metrics(cutter)
        rolled = raw.cut(cutter).clean()
    elif strategy == "individual_union":
        cutters = []
        cutter_rows = []
        for index, branch in enumerate(terminal):
            cutter = sweep(
                sections=corner_cutter_face(branch, MAIN_ROLL_RADIUS),
                path=branch,
                is_frenet=True,
                clean=True,
            )
            cutters.append(cutter)
            cutter_rows.append({"index": index, **shape_metrics(cutter)})
        union = cutters[0].fuse(*cutters[1:]).clean()
        evidence["individual_cutters"] = cutter_rows
        evidence["cutter_union"] = shape_metrics(union)
        rolled = raw.cut(union).clean()
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    evidence["rolled"] = shape_metrics(rolled)
    if not bool(metric(rolled.is_valid)) or len(rolled.solids()) != 1:
        raise RuntimeError(f"{strategy}: invalid main roll")
    return rolled, evidence


def build_joint(strategy: str) -> tuple[Part, dict]:
    rolled, evidence = build_main_roll(strategy)
    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1), clean=True)
    joint = rolled.fuse(pad).clean()
    evidence["pad"] = shape_metrics(pad)
    evidence["joint"] = shape_metrics(joint)
    if not bool(metric(joint.is_valid)) or len(joint.solids()) != 1:
        raise RuntimeError(f"{strategy}: invalid pad fusion")
    return joint, evidence


def main() -> None:
    strategy = os.environ.get("FIVE_BRANCH_STRATEGY", "native_fillet")
    out = Path("artifacts/five_branch_candidate")
    out.mkdir(parents=True, exist_ok=True)
    try:
        joint, evidence = build_joint(strategy)
        export_step(joint, out / "candidate_joint.step")
        export_stl(joint, out / "candidate_joint.stl", tolerance=0.005, angular_tolerance=0.02)
        evidence["success"] = True
    except Exception as exc:
        evidence = {
            "strategy": strategy,
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        (out / "candidate_build.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
        raise
    (out / "candidate_build.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
