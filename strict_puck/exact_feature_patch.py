from __future__ import annotations

from build123d import Edge, Face, Kind, Side, Vector, Wire
import production as p

FACET_COUNTS_BY_INDEX: dict[int, int] = {
    0: 8, 2: 26, 4: 14, 6: 10, 8: 6,
    13: 5, 14: 6, 15: 6, 16: 7, 18: 8,
    20: 3, 22: 8, 24: 5, 25: 6, 27: 14,
    29: 14, 31: 22, 33: 8,
}


def pt(x: float, y: float) -> Vector:
    return Vector(float(x), float(y), 0.0)


def cubic_point(points: tuple[tuple[float, float], ...], t: float) -> Vector:
    u = 1.0 - t
    return Vector(
        u**3*points[0][0] + 3.0*u*u*t*points[1][0] + 3.0*u*t*t*points[2][0] + t**3*points[3][0],
        u**3*points[0][1] + 3.0*u*u*t*points[1][1] + 3.0*u*t*t*points[2][1] + t**3*points[3][1],
        0.0,
    )


def feature_facets(feature_index: int) -> list[Edge]:
    feature = p.CASE_PERIMETER_FEATURES[feature_index]
    points = feature.points
    if feature.kind == "line":
        return [Edge.make_line(Vector(*points[0]), Vector(*points[-1]))]
    if feature.kind == "bezier":
        count = FACET_COUNTS_BY_INDEX[feature_index]
        vertices = [cubic_point(points, index / count) for index in range(count + 1)]
        return [Edge.make_line(a, b) for a, b in zip(vertices, vertices[1:])]
    if feature.kind == "arc":
        arc = Edge.make_three_point_arc(*(Vector(*point) for point in points))
        if feature_index == 10:
            return [arc]
        count = FACET_COUNTS_BY_INDEX[feature_index]
        vertices = [arc.position_at(index / count) for index in range(count + 1)]
        return [Edge.make_line(a, b) for a, b in zip(vertices, vertices[1:])]
    raise ValueError(feature.kind)


def board_wire() -> Wire:
    wire = Wire([
        edge
        for feature_index in range(len(p.CASE_PERIMETER_FEATURES))
        for edge in feature_facets(feature_index)
    ])
    if not wire.is_closed or not p.shape_is_valid(wire):
        raise RuntimeError("Compact faceted perimeter is not one valid closed wire")
    return wire


def raw_offset_wire(distance: float) -> Wire:
    kind = Kind.INTERSECTION if distance >= 0.0 else Kind.TANGENT
    result = board_wire().offset_2d(distance, kind=kind)
    if isinstance(result, list):
        if not result:
            raise RuntimeError(f"Offset {distance} produced no wire")
        result = max(result, key=lambda item: Face(item).area)
    if not isinstance(result, Wire):
        wires = list(result.wires())
        if not wires:
            raise RuntimeError(f"Offset {distance} produced no wire")
        result = max(wires, key=lambda item: Face(item).area)
    if abs(distance - 3.25) < 1.0e-9:
        face = Face(result)
        corner = min(
            face.vertices(),
            key=lambda vertex: (vertex.X - 34.632959) ** 2 + (vertex.Y + 41.654483) ** 2,
        )
        result = face.fillet_2d(2.0, [corner]).outer_wire()
    if not result.is_closed or not p.shape_is_valid(result):
        raise RuntimeError(f"Offset {distance} is invalid")
    return result


def feature_offset_edges(feature_index: int, distance: float) -> list[Edge]:
    source_wire = Wire(feature_facets(feature_index))
    if not p.shape_is_valid(source_wire):
        raise RuntimeError(f"Perimeter feature {feature_index} is invalid before offset")
    offset = source_wire.offset_2d(distance, side=Side.RIGHT, closed=False)
    if isinstance(offset, list):
        if len(offset) != 1:
            raise RuntimeError(f"Perimeter feature {feature_index} offset split into {len(offset)} wires")
        offset = offset[0]
    return list(offset.order_edges())


def support_face(edges: list[Edge], name: str) -> Face:
    wire = Wire(edges)
    if not wire.is_closed or not p.shape_is_valid(wire):
        raise RuntimeError(f"{name} support wire is invalid")
    face = Face(wire)
    if not p.shape_is_valid(face) or face.area <= 0.0:
        raise RuntimeError(f"{name} support face is invalid")
    return face


def lower_wall_support_faces() -> tuple[Face, ...]:
    supports: list[Face] = []

    default = feature_offset_edges(4, 0.75)
    reinforced = feature_offset_edges(4, 1.75)
    left_default = pt(-56.947618560, 20.115506596)
    left_reinforced = pt(-55.215567753, 19.115506596)
    right_default = pt(-34.308520921, 15.540458596)
    right_reinforced = pt(-36.040571729, 14.540458596)
    supports.append(support_face([
        Edge.make_line(left_default, default[0].vertices()[0]), *default,
        Edge.make_line(default[-1].vertices()[-1], right_default),
        Edge.make_three_point_arc(right_default, pt(-35.040571729, 14.808407789), right_reinforced),
        Edge.make_line(right_reinforced, reinforced[-1].vertices()[-1]),
        *[edge.reversed() for edge in reinforced[::-1]],
        Edge.make_line(reinforced[0].vertices()[0], left_reinforced),
        Edge.make_three_point_arc(left_reinforced, pt(-56.215567753, 19.383455789), left_default),
    ], "upper column transition"))

    left_default = pt(-23.776042271, 13.015444596)
    left_reinforced = pt(-22.043991464, 12.015444596)
    right_reinforced = pt(-12.242330586, 12.015444596)
    right_controller = pt(-10.242330586, 14.015444596)
    controller_zone_x = -10.510253
    supports.append(support_face([
        Edge.make_line(left_default, pt(controller_zone_x, 13.015500000)),
        Edge.make_line(pt(controller_zone_x, 13.015500000), pt(controller_zone_x, 14.015500000)),
        Edge.make_line(pt(controller_zone_x, 14.015500000), right_controller),
        Edge.make_three_point_arc(right_controller, pt(-10.828117023, 12.601231034), right_reinforced),
        Edge.make_line(right_reinforced, left_reinforced),
        Edge.make_three_point_arc(left_reinforced, pt(-23.043991464, 12.283393789), left_default),
    ], "upper second-column terrace"))

    default = feature_offset_edges(27, 0.75)
    reinforced = feature_offset_edges(27, 1.75)
    left_default = pt(-56.970925981, -35.334351404)
    left_reinforced = pt(-55.238875173, -34.334351404)
    right_default = pt(-38.646381151, -39.909399404)
    right_reinforced = pt(-40.378431959, -38.909399404)
    supports.append(support_face([
        Edge.make_line(left_default, default[-1].vertices()[-1]),
        *[edge.reversed() for edge in default[::-1]],
        Edge.make_line(default[0].vertices()[0], right_default),
        Edge.make_three_point_arc(right_default, pt(-39.378431959, -39.177348596), right_reinforced),
        Edge.make_line(right_reinforced, reinforced[0].vertices()[0]), *reinforced,
        Edge.make_line(reinforced[-1].vertices()[-1], left_reinforced),
        Edge.make_three_point_arc(left_reinforced, pt(-56.238875173, -34.602300596), left_default),
    ], "lower column transition"))

    default = feature_offset_edges(0, 0.75)
    reinforced = feature_offset_edges(0, 1.75)
    vertical_default = pt(-101.877041463, -5.716584211)
    vertical_reinforced = pt(-100.877041463, -3.984533404)
    terrace_reinforced = pt(-95.877041463, 1.015466596)
    terrace_default = pt(-94.144990655, 2.015466596)
    supports.append(support_face([
        Edge.make_line(vertical_default, default[0].vertices()[0]), *default,
        Edge.make_line(default[-1].vertices()[-1], terrace_default),
        Edge.make_three_point_arc(terrace_default, pt(-94.877041463, 1.283415789), terrace_reinforced),
        Edge.make_line(terrace_reinforced, reinforced[-1].vertices()[-1]),
        *[edge.reversed() for edge in reinforced[::-1]],
        Edge.make_line(reinforced[0].vertices()[0], vertical_reinforced),
        Edge.make_three_point_arc(vertical_reinforced, pt(-101.144990655, -4.984533404), vertical_default),
    ], "upper-left corner return"))

    default = feature_offset_edges(33, 0.75)
    reinforced = feature_offset_edges(33, 1.75)
    terrace_default = pt(-94.144990655, -53.434391404)
    terrace_reinforced = pt(-95.877041463, -52.434391404)
    vertical_reinforced = pt(-100.877041463, -47.434391404)
    vertical_default = pt(-101.877041463, -45.702340596)
    supports.append(support_face([
        Edge.make_line(terrace_default, default[0].vertices()[0]), *default,
        Edge.make_line(default[-1].vertices()[-1], vertical_default),
        Edge.make_three_point_arc(vertical_default, pt(-101.144990655, -46.434391404), vertical_reinforced),
        Edge.make_line(vertical_reinforced, reinforced[-1].vertices()[-1]),
        *[edge.reversed() for edge in reinforced[::-1]],
        Edge.make_line(reinforced[0].vertices()[0], terrace_reinforced),
        Edge.make_three_point_arc(terrace_reinforced, pt(-94.877041463, -52.702340596), terrace_default),
    ], "lower-left corner return"))

    default = feature_offset_edges(18, 0.75)
    reinforced = feature_offset_edges(18, 1.75)
    first_default = pt(-0.117509333, -67.481758872)
    first_reinforced = pt(-1.849577555, -68.481728709)
    second_reinforced = pt(-8.679867995, -70.311864065)
    second_default = pt(-10.679867995, -70.311879522)
    supports.append(support_face([
        Edge.make_line(first_default, default[0].vertices()[0]), *default,
        Edge.make_line(default[-1].vertices()[-1], second_default),
        Edge.make_three_point_arc(second_default, pt(-9.679870066, -70.043922601), second_reinforced),
        Edge.make_line(second_reinforced, reinforced[-1].vertices()[-1]),
        *[edge.reversed() for edge in reinforced[::-1]],
        Edge.make_line(reinforced[0].vertices()[0], first_reinforced),
        Edge.make_three_point_arc(first_reinforced, pt(-1.117513999, -67.749690650), first_default),
    ], "lower thumb V"))

    default = feature_offset_edges(22, 0.75)
    reinforced = feature_offset_edges(22, 1.75)
    first_default = pt(-30.055814288, -61.985268422)
    first_reinforced = pt(-31.470027205, -60.571054215)
    second_reinforced = pt(-35.005528493, -54.447346128)
    second_default = pt(-35.523156474, -52.515491767)
    supports.append(support_face([
        Edge.make_line(first_default, default[0].vertices()[0]), *default,
        Edge.make_line(default[-1].vertices()[-1], second_default),
        Edge.make_three_point_arc(second_default, pt(-35.005523076, -53.412069948), second_reinforced),
        Edge.make_line(second_reinforced, reinforced[-1].vertices()[-1]),
        *[edge.reversed() for edge in reinforced[::-1]],
        Edge.make_line(reinforced[0].vertices()[0], first_reinforced),
        Edge.make_three_point_arc(first_reinforced, pt(-30.573451969, -61.088692714), first_default),
    ], "thumb return"))

    return tuple(supports)


def install() -> None:
    p.board_wire = board_wire
    p.raw_offset_wire = raw_offset_wire
    p.lower_wall_support_faces = lower_wall_support_faces
