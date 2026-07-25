from __future__ import annotations

"""Reference-independent cubic five-branch Kailh solder-joint builder.

Each rolling branch is a cubic Bézier determined by:
- exact branch endpoints;
- exact tangent directions at both endpoints;
- one exact interior design datum;
- the interior datum's exact normalized branch parameter.

The resulting profile contains five intentional engineering branches. It does
not contain reference spline poles/knots, dense sampled contours, section
stacks, imported CAD, mesh geometry, or residual correction bodies.
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

# Cubic Bézier points in the YZ design plane, ordered left-to-right.
BRANCH_BEZIER_YZ = (
    (
        (3.905767147044970, 1.750000000000000),
        (4.007978121795953, 1.750000000000000),
        (4.069318081734577, 1.696415710468264),
        (4.120875765999405, 1.576891528610150),
    ),
    (
        (4.120875765999405, 1.576891528610150),
        (4.681186461443986, 0.277944952278916),
        (3.702577205685040, 0.618745165782120),
        (4.702352901139571, 1.434925644480377),
    ),
    (
        (4.702352901139571, 1.434925644480377),
        (4.956197853564133, 1.642155421846412),
        (5.230906670317478, 1.579026703605459),
        (5.468627665077156, 1.381606790580138),
    ),
    (
        (5.468627665077156, 1.381606790580138),
        (6.344343475135149, 0.654351971411461),
        (5.576524301296046, 0.349961275978532),
        (6.055620170693765, 1.528914787055315),
    ),
    (
        (6.055620170693765, 1.528914787055315),
        (6.087425549966595, 1.607181092318955),
        (6.152263921173661, 1.749998000753497),
        (6.264492043502691, 1.749999999979117),
    ),
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
    return Edge.make_bezier(
        *(Vector(x, y, z) for y, z in BRANCH_BEZIER_YZ[index])
    )


def profile_branches(x: float) -> list[Edge]:
    return [branch_edge(index, x) for index in range(5)]


def profile_face(x: float) -> Face:
    branches = profile_branches(x)
    top = Edge.make_line(branches[-1].end_point(), branches[0].start_point())
    return Face(closed_wire([*branches, top]))


def preflight() -> tuple[Face, Part, list[Edge], dict]:
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
        "profile": {
            "valid": bool(metric(profile.is_valid)),
            "area": float(metric(profile.area)),
            "area_error_percent": 100.0
            * (float(metric(profile.area)) - TARGET_PROFILE_AREA)
            / TARGET_PROFILE_AREA,
            "branch_lengths": branch_lengths,
            "contour_length": sum(branch_lengths),
            "contour_length_error": sum(branch_lengths) - TARGET_CONTOUR_LENGTH,
        },
        "raw": shape_metrics(raw),
    }
    return profile, raw, terminal, evidence


def build_main_roll(strategy: str) -> tuple[Part, dict]:
    _, raw, terminal, evidence = preflight()
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
        rows = []
        for index, branch in enumerate(terminal):
            cutter = sweep(
                sections=corner_cutter_face(branch, MAIN_ROLL_RADIUS),
                path=branch,
                is_frenet=True,
                clean=True,
            )
            cutters.append(cutter)
            rows.append({"index": index, **shape_metrics(cutter)})
        union = cutters[0].fuse(*cutters[1:]).clean()
        evidence["individual_cutters"] = rows
        evidence["cutter_union"] = shape_metrics(union)
        rolled = raw.cut(union).clean()
    else:
        raise ValueError(strategy)
    evidence["rolled"] = shape_metrics(rolled)
    return rolled, evidence


def build_joint(strategy: str) -> tuple[Part, dict]:
    rolled, evidence = build_main_roll(strategy)
    if not bool(metric(rolled.is_valid)) or len(rolled.solids()) != 1:
        raise RuntimeError(f"{strategy}: invalid main roll; {evidence}")
    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1), clean=True)
    joint = rolled.fuse(pad).clean()
    evidence["pad"] = shape_metrics(pad)
    evidence["joint"] = shape_metrics(joint)
    if not bool(metric(joint.is_valid)) or len(joint.solids()) != 1:
        raise RuntimeError(f"{strategy}: invalid pad fusion; {evidence}")
    return joint, evidence


def main() -> None:
    strategy = os.environ.get("BEZIER_STRATEGY", "native_fillet")
    out = Path("artifacts/five_branch_bezier")
    out.mkdir(parents=True, exist_ok=True)
    _, _, _, preflight_evidence = preflight()
    evidence = {"strategy": strategy, **preflight_evidence}
    try:
        joint, result_evidence = build_joint(strategy)
        evidence.update(result_evidence)
        export_step(joint, out / "candidate_joint.step")
        export_stl(
            joint,
            out / "candidate_joint.stl",
            tolerance=0.005,
            angular_tolerance=0.02,
        )
        evidence["success"] = True
    except Exception as exc:
        evidence["success"] = False
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        (out / "candidate_build.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
        raise
    (out / "candidate_build.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
