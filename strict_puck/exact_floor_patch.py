from __future__ import annotations

from math import sqrt

from build123d import Compound, Location, Solid, Vector

import production as p


def lower_wall_support_solids(z0: float, z1: float) -> tuple[Solid, ...]:
    """Extrude the seven identified moulded supports with Boolean overtravel."""
    overtravel = 0.01
    return tuple(
        Solid.extrude(
            face,
            Vector(0.0, 0.0, z1 - z0 + 2.0 * overtravel),
        ).moved(Location((0.0, 0.0, z0 - overtravel)))
        for face in p.lower_wall_support_faces()
    )


def _solid_pieces(result) -> list[Solid]:
    if result is None:
        return []
    if isinstance(result, (list, tuple)):
        candidates = result
    elif hasattr(result, "solids"):
        candidates = list(result.solids())
    else:
        candidates = [result]
    return [piece for piece in candidates if piece is not None and piece.volume > 1.0e-8]


def build_case_base_exact(
    parameters: p.HexCaseParameters = p.HexCaseParameters(),
    *,
    cut_puck_opening: bool,
) -> Solid:
    """Build the shared case with the exact identified floor-domain feature order."""
    z0 = parameters.z_bottom
    z_floor = z0 + parameters.honeycomb_height
    z_top = z0 + parameters.total_height
    cavity_overlap = 0.01

    body = p.extrude_wire(
        p.raw_offset_wire(parameters.perimeter_clearance), z0, z_top
    )
    bottom_face = next(
        face
        for face in body.faces()
        if face.normal_at(face.center()).Z < -0.999999
        and abs(face.center().Z - z0) < 1.0e-6
    )
    body = body.chamfer(
        parameters.bottom_chamfer_height,
        None,
        bottom_face.edges(),
        bottom_face,
    ).clean()
    top_face = next(
        face
        for face in body.faces()
        if face.normal_at(face.center()).Z > 0.999999
        and abs(face.center().Z - z_top) < 1.0e-6
    )
    body = p._single_solid(
        body.chamfer(
            parameters.top_chamfer_height,
            None,
            top_face.edges(),
            top_face,
        ).clean(),
        "outer moulding",
    )

    lower_cavity_tools = tuple(
        Solid.extrude(
            profile,
            Vector(0.0, 0.0, parameters.tower_top_z - z_floor),
        ).moved(Location((0.0, 0.0, z_floor)))
        for profile in p.lower_cavity_profiles(parameters)
    )
    for index, tool in enumerate(lower_cavity_tools, start=1):
        body = p._single_solid(body.cut(tool), f"lower cavity feature {index}")

    upper_cavity = p.extrude_wire(
        p.raw_offset_wire(
            parameters.perimeter_clearance - parameters.upper_wall_thickness
        ),
        parameters.tower_top_z - cavity_overlap,
        z_top + 0.10,
    )
    body = p._single_solid(body.cut(upper_cavity), "upper cavity")
    body = p._single_solid(body.cut(p.controller_wall_opening()), "controller opening")

    # Exact vent cutters are clipped by the authored board profile, then every
    # material keepout is subtracted before the aggregate cut. This is the
    # identified production feature order and prevents detached floor islands.
    board_prism = p.extrude_wire(
        p.board_wire(), z0 - 0.05, z_floor + cavity_overlap
    )
    body_box = body.bounding_box()
    hex_radius = 2.0 * parameters.hex_apothem / sqrt(3.0)
    keepouts = (
        *((x, y, parameters.foot_pad_radius) for x, y in p.FOOT_RECESS_CENTERS),
        *((x, y, parameters.boss_outer_radius) for x, y in p.MOUNTING_BOSS_CENTERS),
        (
            parameters.puck_center_x,
            parameters.puck_center_y,
            parameters.puck_outer_radius,
        ),
        (*p.AUXILIARY_PAD_CENTER, p.AUXILIARY_PAD_RADIUS),
    )
    support_solids = lower_wall_support_solids(z0 - 0.05, z_floor + 0.05)
    grid_cutters: list[Solid] = []

    for center_x, center_y in p.grid_centers(parameters):
        if center_x + hex_radius < body_box.min.X or center_x - hex_radius > body_box.max.X:
            continue
        if center_y + parameters.hex_apothem < body_box.min.Y or center_y - parameters.hex_apothem > body_box.max.Y:
            continue

        cell = p.extrude_wire(
            p.rounded_hex_wire(center_x, center_y, parameters),
            z0 - 0.05,
            z_floor + cavity_overlap,
        )
        pieces = _solid_pieces(cell.intersect(board_prism))
        if not pieces:
            continue

        for keepout_x, keepout_y, keepout_radius in keepouts:
            if (
                (center_x - keepout_x) ** 2 + (center_y - keepout_y) ** 2
                > (hex_radius + keepout_radius) ** 2
            ):
                continue
            keepout = p.cylinder(
                keepout_radius,
                z0 - 0.10,
                z_floor + 0.10,
                keepout_x,
                keepout_y,
            )
            next_pieces: list[Solid] = []
            for piece in pieces:
                next_pieces.extend(_solid_pieces(piece.cut(keepout)))
            pieces = next_pieces
            if not pieces:
                break

        for support in support_solids:
            next_pieces = []
            for piece in pieces:
                next_pieces.extend(_solid_pieces(piece.cut(support)))
            pieces = next_pieces
            if not pieces:
                break

        grid_cutters.extend(pieces)

    if grid_cutters:
        body = p._single_solid(
            body.cut(Compound(grid_cutters)).fix().clean(),
            "honeycomb floor",
        )

    if cut_puck_opening:
        body = p._single_solid(
            body.cut(
                p.cylinder(
                    parameters.puck_opening_radius,
                    z0 - 0.05,
                    z_floor + cavity_overlap,
                    parameters.puck_center_x,
                    parameters.puck_center_y,
                )
            ),
            "puck opening",
        )

    body = p._single_solid(
        body.cut(
            p.cylinder(
                p.AUXILIARY_OPENING_RADIUS,
                z0 - 0.05,
                z_floor + cavity_overlap,
                *p.AUXILIARY_PAD_CENTER,
            )
        ),
        "auxiliary opening",
    )
    for x, y in p.FOOT_RECESS_CENTERS:
        body = p._single_solid(
            body.cut(
                p.cylinder(
                    parameters.foot_recess_radius,
                    z0 - 0.05,
                    z0 + parameters.foot_recess_depth,
                    x,
                    y,
                )
            ),
            "foot recess",
        )
    for x, y in p.MOUNTING_BOSS_CENTERS:
        body = p._single_solid(
            body.cut(p.staged_mounting_bore(x, y, z0, z_top, parameters)),
            "mounting bore",
        )

    return p._single_solid(body.fix().clean(), "case base")


def install() -> None:
    p.build_case_base = build_case_base_exact
