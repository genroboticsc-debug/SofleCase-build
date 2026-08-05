from __future__ import annotations

from build123d import Edge, Face, Plane, Wire

import production as p


def face_pieces(result) -> list[Face]:
    if result is None:
        return []
    if isinstance(result, Face):
        candidates = [result]
    elif isinstance(result, (list, tuple)):
        candidates = list(result)
    elif hasattr(result, "faces"):
        candidates = list(result.faces())
    else:
        candidates = [result]
    return [face for face in candidates if face is not None and face.area > 1.0e-8]


def fuse_region(region: Face, addition: Face, name: str) -> Face:
    pieces = face_pieces(region.fuse(addition))
    if len(pieces) != 1:
        raise RuntimeError(f"{name} produced {len(pieces)} planar regions")
    boundary = pieces[0].outer_wire()
    if not boundary.is_closed or not p.shape_is_valid(boundary):
        raise RuntimeError(f"{name} produced an invalid boundary")
    result = Face(boundary)
    if not p.shape_is_valid(result):
        raise RuntimeError(f"{name} produced an invalid face")
    return result


def native_controller_cavity_face(cavity_face: Face) -> Face:
    """Replace the obsolete offset segment by the exact native edge chain."""
    edges = list(cavity_face.outer_wire().order_edges())
    candidates = [
        index
        for index, edge in enumerate(edges)
        if edge.geom_type.name == "LINE"
        and edge.bounding_box().min.X < -24.7
        and edge.bounding_box().max.X > -24.2
        and 13.0 < edge.bounding_box().min.Y < 13.2
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"controller left-join candidates={candidates}")
    left_index = candidates[0]
    terrace_index = next(
        index
        for index, edge in enumerate(edges)
        if index > left_index
        and edge.geom_type.name == "LINE"
        and edge.length > 30.0
        and abs(edge.bounding_box().min.Y - 12.6555) < 0.01
    )
    left_start = edges[left_index].vertices()[0]
    right_end = edges[terrace_index].vertices()[-1]
    point = lambda x, y: p._point((x, y))

    p0 = point(-24.077079461468443, 13.015444596428026)
    p1 = point(-23.776042271076335, 13.015444596428026)
    p2 = point(-22.043991463507460, 12.015444596428027)
    p3 = point(-12.242330585806730, 12.015444596428027)
    p4 = point(-10.242330585806730, 14.015444596428027)
    p5 = point(-9.540174793573136, 13.959978596162381)
    p6 = point(-8.853120822958800, 13.802639149346222)
    p7 = point(-6.321693815707628, 12.848273141887887)
    p8 = point(-5.703402751805730, 12.706680592863014)
    p9 = point(-5.057428599478593, 12.655652597508022)

    replacement = [
        Edge.make_line(left_start, p0),
        Edge.make_line(p0, p1),
        Edge.make_three_point_arc(
            p1,
            point(-23.043991463507460, 12.283393788858905),
            p2,
        ),
        Edge.make_line(p2, p3),
        Edge.make_three_point_arc(
            p3,
            point(-10.828117023433921, 12.601231034054932),
            p4,
        ),
        Edge.make_line(p4, p5),
        Edge.make_line(p5, p6),
        Edge.make_line(p6, p7),
        Edge.make_line(p7, p8),
        Edge.make_line(p8, p9),
        Edge.make_line(p9, right_end),
    ]
    wire = Wire(edges[:left_index] + replacement + edges[terrace_index + 1 :])
    if not wire.is_closed or not p.shape_is_valid(wire):
        raise RuntimeError("native controller cavity wire is invalid")
    result = Face(wire)
    if not p.shape_is_valid(result):
        raise RuntimeError("native controller cavity face is invalid")
    return result


def exact_lower_cavity_profiles(parameters: p.HexCaseParameters) -> tuple[Face, ...]:
    region = Face(
        p.raw_offset_wire(
            parameters.perimeter_clearance - parameters.wall_thickness
        )
    )
    wide = Face(
        p.raw_offset_wire(
            parameters.perimeter_clearance - parameters.upper_wall_thickness
        )
    )
    zones = (
        ("upper controller rail", p.zone_face(-10.510253, 40.0, 0.131665, 30.0)),
        ("lower controller rail", p.zone_face(8.501314, 40.0, -90.0, -5.601676)),
    )
    for name, zone in zones:
        reliefs = face_pieces(wide.intersect(zone))
        if not reliefs:
            raise RuntimeError(f"{name} produced no relief")
        for relief in reliefs:
            region = fuse_region(region, relief, name)
    region = native_controller_cavity_face(region)

    exclusions = (
        *p.lower_wall_support_faces(),
        *(
            Face(
                Wire.make_circle(
                    parameters.boss_outer_radius,
                    Plane(origin=(x, y, 0.0)),
                )
            )
            for x, y in p.MOUNTING_BOSS_CENTERS
        ),
    )
    profiles = [region]
    for index, exclusion in enumerate(exclusions, start=1):
        next_profiles: list[Face] = []
        for profile in profiles:
            next_profiles.extend(face_pieces(profile.cut(exclusion)))
        if not next_profiles:
            raise RuntimeError(f"lower-cavity exclusion {index} removed the region")
        profiles = next_profiles
    return tuple(profiles)


def exact_floor_vent_face(parameters: p.HexCaseParameters) -> Face:
    region = Face(
        p.raw_offset_wire(
            parameters.perimeter_clearance - parameters.wall_thickness
        )
    )
    wide = Face(
        p.raw_offset_wire(
            parameters.perimeter_clearance - parameters.upper_wall_thickness
        )
    )
    zones = (
        p.zone_face(-10.510253, 40.0, 0.131665, 30.0),
        p.zone_face(8.501314, 40.0, -90.0, 0.131665),
        p.zone_face(30.0, 40.0, -5.601676, 0.131665),
    )
    for index, zone in enumerate(zones, start=1):
        reliefs = face_pieces(wide.intersect(zone))
        if not reliefs:
            raise RuntimeError(f"floor controller relief {index} is empty")
        for relief in reliefs:
            region = fuse_region(region, relief, f"floor controller relief {index}")
    region = native_controller_cavity_face(region)
    for index, support in enumerate(p.lower_wall_support_faces(), start=1):
        pieces = face_pieces(region.cut(support))
        if len(pieces) != 1:
            raise RuntimeError(f"floor support {index} produced {len(pieces)} regions")
        region = Face(pieces[0].outer_wire())
    if not p.shape_is_valid(region):
        raise RuntimeError("exact floor vent face is invalid")
    return region


def install() -> None:
    original_build = p.build_case_base
    original_board_wire = p.board_wire
    p.lower_cavity_profiles = exact_lower_cavity_profiles

    def exact_domain_build(
        parameters: p.HexCaseParameters = p.HexCaseParameters(),
        *,
        cut_puck_opening: bool,
    ):
        floor_wire = exact_floor_vent_face(parameters).outer_wire()
        call_count = 0

        def routed_board_wire() -> Wire:
            nonlocal call_count
            call_count += 1
            if call_count == 5:
                return floor_wire
            return original_board_wire()

        p.board_wire = routed_board_wire
        try:
            return original_build(
                parameters,
                cut_puck_opening=cut_puck_opening,
            )
        finally:
            p.board_wire = original_board_wire

    p.build_case_base = exact_domain_build
