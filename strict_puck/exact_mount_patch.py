from __future__ import annotations

from math import sqrt

from build123d import Vector, Wire

import production as p


def regular_hex_bore_wire(center_x: float, center_y: float) -> Wire:
    """Regular hexagonal nut pocket, 6.0 mm across flats."""
    apothem = 3.0
    radius = 2.0 * apothem / sqrt(3.0)
    return Wire.make_polygon(
        [
            Vector(center_x + radius, center_y),
            Vector(center_x + radius / 2.0, center_y + apothem),
            Vector(center_x - radius / 2.0, center_y + apothem),
            Vector(center_x - radius, center_y),
            Vector(center_x - radius / 2.0, center_y - apothem),
            Vector(center_x + radius / 2.0, center_y - apothem),
        ],
        close=True,
    )


def flat_hex_bore_wire(center_x: float, center_y: float) -> Wire:
    """Exact hex section clipped by the 3.5 mm horizontal band."""
    half_height = 1.75
    outer_x = 6.0 / sqrt(3.0)
    shoulder_x = outer_x - half_height / sqrt(3.0)
    return Wire.make_polygon(
        [
            Vector(center_x - outer_x, center_y),
            Vector(center_x - shoulder_x, center_y + half_height),
            Vector(center_x + shoulder_x, center_y + half_height),
            Vector(center_x + outer_x, center_y),
            Vector(center_x + shoulder_x, center_y - half_height),
            Vector(center_x - shoulder_x, center_y - half_height),
        ],
        close=True,
    )


def square_bore_wire(center_x: float, center_y: float) -> Wire:
    half_width = 1.75
    return Wire.make_polygon(
        [
            Vector(center_x - half_width, center_y - half_width),
            Vector(center_x + half_width, center_y - half_width),
            Vector(center_x + half_width, center_y + half_width),
            Vector(center_x - half_width, center_y + half_width),
        ],
        close=True,
    )


def staged_mounting_bore(
    center_x: float,
    center_y: float,
    z_bottom: float,
    z_top: float,
    _parameters=None,
):
    """Hex -> flat-hex -> square -> circular mounting-cavity stack."""
    overlap = 0.01
    stages = (
        p.extrude_wire(
            regular_hex_bore_wire(center_x, center_y), z_bottom - 0.02, -4.6
        ),
        p.extrude_wire(
            flat_hex_bore_wire(center_x, center_y), -4.6 - overlap, -4.4
        ),
        p.extrude_wire(
            square_bore_wire(center_x, center_y), -4.4 - overlap, -4.2
        ),
        p.cylinder(1.75, -4.2 - overlap, z_top + 0.05, center_x, center_y),
    )
    result = stages[0]
    for stage in stages[1:]:
        result = p._single_solid(result.fuse(stage).clean(), "mounting-cavity stage")
    return p._single_solid(result.fix().clean(), "mounting-cavity tool")


def install() -> None:
    p.staged_mounting_bore = staged_mounting_bore
