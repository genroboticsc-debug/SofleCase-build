"""Construct the exact R2 top roll as a clipped 3-D solid offset.

The identified top contour is the exact two-millimetre inward offset of the
reference spring contour after suppression of the 0.076052190114 mm feature
that cannot survive an R2 roll.  Offsetting a prism of this contour outward by
2 mm creates the exact planar/cylindrical/toroidal/spherical cap.  The result
is intersected with the identified outer-profile envelope and united with the
unfilleted lower prism.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from build123d import (
    BuildPart,
    BuildSketch,
    Kind,
    Mode,
    add,
    export_step,
    export_stl,
    extrude,
    offset,
)

from top_parametric import (
    TOP_FILLET_RADIUS,
    Y_BODY_LOW,
    Y_FILLET_LOW,
    Y_TOP,
    outer_profile_sketch,
    xz_plane,
)

OUT = Path(__file__).resolve().parent / "generated"
OUT.mkdir(parents=True, exist_ok=True)


def _face_at(sketch, y: float):
    with BuildSketch(xz_plane(y)) as placed:
        add(sketch)
    return placed.sketch.faces()[0]


def _solid_from(sketch, y0: float, y1: float):
    face = _face_at(sketch, y0)
    return extrude(face, amount=-(y1 - y0))


def _top_planar_area(part) -> float:
    return sum(
        face.area
        for face in part.faces()
        if face.vertices()
        and all(abs(vertex.Y - Y_TOP) <= 1.0e-6 for vertex in face.vertices())
    )


def _metrics(name: str, part):
    bbox = part.bounding_box()
    record = {
        "name": name,
        "valid": bool(part.is_valid),
        "solid_count": len(part.solids()),
        "volume": part.volume,
        "area": part.area,
        "top_planar_area": _top_planar_area(part),
        "bounds": {
            "x_min": bbox.min.X,
            "x_max": bbox.max.X,
            "y_min": bbox.min.Y,
            "y_max": bbox.max.Y,
            "z_min": bbox.min.Z,
            "z_max": bbox.max.Z,
        },
        "face_types": sorted(face.geom_type.name for face in part.faces()),
    }
    export_step(part, OUT / f"{name}.step")
    export_stl(
        part,
        OUT / f"{name}.stl",
        tolerance=0.001,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    return record


def _build(offset_amount: float, use_opening: bool):
    outer = outer_profile_sketch()
    top_profile = offset(
        outer,
        amount=-TOP_FILLET_RADIUS,
        kind=Kind.ARC,
        min_edge_length=1.0e-7,
    )

    # A tall seed prevents the lower offset from influencing the retained cap.
    seed = _solid_from(top_profile, Y_BODY_LOW - 4.0, Y_FILLET_LOW)
    openings = []
    if use_opening:
        bottom_faces = [
            face
            for face in seed.faces()
            if face.vertices()
            and all(
                abs(vertex.Y - (Y_BODY_LOW - 4.0)) <= 1.0e-6
                for vertex in face.vertices()
            )
        ]
        openings = bottom_faces

    expanded = offset(
        seed,
        amount=offset_amount,
        openings=openings if use_opening else None,
        kind=Kind.ARC,
    )
    envelope = _solid_from(outer, Y_BODY_LOW, Y_TOP)
    lower = _solid_from(outer, Y_BODY_LOW, Y_FILLET_LOW)

    clipped = expanded & envelope
    final = lower.fuse(clipped)
    return top_profile, seed, expanded, clipped, final


def main() -> int:
    attempts = []
    for amount in (TOP_FILLET_RADIUS, -TOP_FILLET_RADIUS):
        for use_opening in (False, True):
            stem = f"offset_cap_a{'p' if amount > 0 else 'm'}2_o{int(use_opening)}"
            try:
                top_profile, seed, expanded, clipped, final = _build(
                    amount, use_opening
                )
                attempts.append(
                    {
                        "ok": True,
                        "amount": amount,
                        "use_opening": use_opening,
                        "top_profile_area": top_profile.faces()[0].area,
                        "seed": _metrics(f"{stem}_seed", seed),
                        "expanded": _metrics(f"{stem}_expanded", expanded),
                        "clipped": _metrics(f"{stem}_clipped", clipped),
                        "final": _metrics(f"{stem}_final", final),
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "ok": False,
                        "amount": amount,
                        "use_opening": use_opening,
                        "exception": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                )

    report = {"attempts": attempts}
    (OUT / "offset_cap_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
