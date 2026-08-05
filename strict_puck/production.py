from __future__ import annotations

from dataclasses import dataclass
from math import sqrt, tan
from pathlib import Path
import argparse

from build123d import (
    Compound, Edge, Face, Kind, Location, Plane, Side, Solid, Vector, Wire,
    export_step, export_stl,
)


@dataclass(frozen=True)
class PerimeterFeature:
    name: str
    kind: str
    points: tuple[tuple[float, float], ...]


CASE_PERIMETER_FEATURES: tuple[PerimeterFeature, ...] = (
    PerimeterFeature('left_top_corner', 'arc', ((-102.627041, 0.1905), (-101.870041, 2.0085), (-100.052041, 2.7655))),
    PerimeterFeature('left_upper_terrace', 'line', ((-100.052041, 2.7655), (-86.252041, 2.7655))),
    PerimeterFeature('left_upper_matrix_transition', 'bezier', ((-86.252041, 2.7655), (-82.00435438, 2.76285279), (-84.78810235, 20.92951005), (-80.119041, 20.8655))),
    PerimeterFeature('upper_matrix_terrace', 'line', ((-80.119041, 20.8655), (-48.227041, 20.8655))),
    PerimeterFeature('upper_column_transition_1', 'bezier', ((-48.227041, 20.8655), (-45.349005926, 20.879833168), (-45.930886837, 16.275382562), (-43.052041, 16.2905))),
    PerimeterFeature('upper_column_terrace_1', 'line', ((-43.052041, 16.2905), (-29.252041, 16.2905))),
    PerimeterFeature('upper_column_transition_2', 'bezier', ((-29.252041, 16.2905), (-27.146651923, 16.32976191), (-26.157581726, 13.72605812), (-24.052041, 13.7655))),
    PerimeterFeature('upper_column_terrace_2', 'line', ((-24.052041, 13.7655), (-10.252041, 13.7655))),
    PerimeterFeature('upper_column_transition_3', 'bezier', ((-10.252041, 13.7655), (-8.412676752, 13.792710381), (-6.906474373, 12.378097632), (-5.067041, 12.4055))),
    PerimeterFeature('controller_top_terrace', 'line', ((-5.067041, 12.4055), (26.882959, 12.4055))),
    PerimeterFeature('controller_outer_corner', 'arc', ((26.882959, 12.4055), (29.998959, 11.1545), (31.382959, 8.0955))),
    PerimeterFeature('right_outer_vertical', 'line', ((31.382959, 8.0955), (31.382959, -38.4045))),
    PerimeterFeature('right_lower_terrace', 'line', ((31.382959, -38.4045), (13.183959, -38.4045))),
    PerimeterFeature('thumb_transition_1', 'bezier', ((13.183959, -38.4045), (11.624861095, -38.4045), (10.733756143, -39.411415818), (10.611959, -39.5375))),
    PerimeterFeature('thumb_transition_2', 'bezier', ((10.611959, -39.5375), (9.59318172, -40.626336115), (9.048576949, -42.053633524), (8.594959, -43.4485))),
    PerimeterFeature('thumb_transition_3', 'bezier', ((8.594959, -43.4485), (7.392983666, -47.421116629), (6.988287963, -51.570298664), (6.169959, -55.6275))),
    PerimeterFeature('thumb_transition_4', 'bezier', ((6.169959, -55.6275), (5.949095608, -56.717252655), (5.390229044, -59.442414963), (4.478959, -61.0215))),
    PerimeterFeature('thumb_outer_line_1', 'line', ((4.478959, -61.0215), (-2.422041, -72.9725))),
    PerimeterFeature('thumb_outer_corner', 'arc', ((-2.422041, -72.9725), (-3.986041, -74.1685), (-5.939041, -73.9145))),
    PerimeterFeature('thumb_outer_line_2', 'line', ((-5.939041, -73.9145), (-17.890041, -67.0155))),
    PerimeterFeature('thumb_transition_5', 'bezier', ((-17.890041, -67.0155), (-19.431632486, -66.152922152), (-20.971186244, -65.194111944), (-22.698041, -64.7335))),
    PerimeterFeature('thumb_inner_line_1', 'line', ((-22.698041, -64.7335), (-35.883041, -61.2005))),
    PerimeterFeature('thumb_transition_6', 'bezier', ((-35.883041, -61.2005), (-37.17303516, -60.898536686), (-38.221191972, -59.504970056), (-37.815041, -58.1715))),
    PerimeterFeature('thumb_inner_line_2', 'line', ((-37.815041, -58.1715), (-34.243041, -44.8425))),
    PerimeterFeature('thumb_transition_7', 'bezier', ((-34.243041, -44.8425), (-33.928774086, -43.667580669), (-34.382984398, -42.900412044), (-34.444041, -42.7855))),
    PerimeterFeature('thumb_transition_8', 'bezier', ((-34.444041, -42.7855), (-34.757090295, -42.203479806), (-36.117956551, -40.6595), (-38.367041, -40.6595))),
    PerimeterFeature('lower_column_terrace_1', 'line', ((-38.367041, -40.6595), (-43.052041, -40.6595))),
    PerimeterFeature('lower_column_transition_1', 'bezier', ((-43.052041, -40.6595), (-45.931028055, -40.674722442), (-45.34855248, -36.069538635), (-48.227041, -36.0845))),
    PerimeterFeature('lower_column_terrace_2', 'line', ((-48.227041, -36.0845), (-62.027041, -36.0845))),
    PerimeterFeature('lower_column_transition_2', 'bezier', ((-62.027041, -36.0845), (-65.66467176, -36.128510087), (-63.614656033, -42.165430433), (-67.252041, -42.2095))),
    PerimeterFeature('lower_column_terrace_3', 'line', ((-67.252041, -42.2095), (-81.052041, -42.2095))),
    PerimeterFeature('left_lower_matrix_transition', 'bezier', ((-81.052041, -42.2095), (-85.12407235, -42.19086191), (-81.71422405, -54.24370745), (-86.252041, -54.1845))),
    PerimeterFeature('left_lower_terrace', 'line', ((-86.252041, -54.1845), (-100.052041, -54.1845))),
    PerimeterFeature('left_bottom_corner', 'arc', ((-100.052041, -54.1845), (-101.870041, -53.4275), (-102.627041, -51.6095))),
    PerimeterFeature('left_outer_vertical', 'line', ((-102.627041, -51.6095), (-102.627041, 0.1905))),
)

LOWER_WALL_SUPPORT_DATA = (
    (((-56.94761856, 20.115506596), (-55.215567753, 19.115506596), (-34.308520921, 15.540458596), (-36.040571729, 14.540458596)), ((-35.040571729, 14.808407789), (-56.215567753, 19.383455789))),
    (((-23.776042271, 13.015444596), (-22.043991464, 12.015444596), (-12.242330586, 12.015444596), (-10.242330586, 14.015444596)), ((-10.828117023, 12.601231034), (-23.043991464, 12.283393789))),
    (((-56.970925981, -35.334351404), (-55.238875173, -34.334351404), (-38.646381151, -39.909399404), (-40.378431959, -38.909399404)), ((-39.378431959, -39.177348596), (-56.238875173, -34.602300596))),
    (((-101.877041463, -5.716584211), (-100.877041463, -3.984533404), (-95.877041463, 1.015466596), (-94.144990655, 2.015466596)), ((-94.877041463, 1.283415789), (-101.144990655, -4.984533404))),
    (((-94.144990655, -53.434391404), (-95.877041463, -52.434391404), (-100.877041463, -47.434391404), (-101.877041463, -45.702340596)), ((-101.144990655, -46.434391404), (-94.877041463, -52.702340596))),
    (((-0.117509333, -67.481758872), (-1.849577555, -68.481728709), (-8.679867995, -70.311864065), (-10.679867995, -70.311879522)), ((-9.679870066, -70.043922601), (-1.117513999, -67.74969065))),
    (((-30.055814288, -61.985268422), (-31.470027205, -60.571054215), (-35.005528493, -54.447346128), (-35.523156474, -52.515491767)), ((-35.005523076, -53.412069948), (-30.573451969, -61.088692714))),
)

FOOT_RECESS_CENTERS = (
    (-53.62204089861489, 15.306683314737421), (-94.73692346464968, -4.772690998617071),
    (-95.62204126369335, -46.69331567198362), (-30.622040606528852, -56.6933154484662),
    (-5.622041679504468, -66.69331690880183), (24.377958185979526, -31.693315464244442),
    (23.955785668379296, 5.62517909496699),
)
MOUNTING_BOSS_CENTERS = (
    (-77.54704146299772, 16.430500596428027), (-30.28704146299773, -41.96449940357197),
    (4.20295853700227, -43.13949940357197),
)
AUXILIARY_PAD_CENTER = (12.70294653700227, 3.8611815964280285)
AUXILIARY_PAD_RADIUS = 10.0
AUXILIARY_OPENING_RADIUS = 7.0
HONEYCOMB_CELL_INDICES = (
    (-7,3),(-7,4),(-7,5),(-7,6),(-6,2),(-6,3),(-6,4),(-6,5),(-6,6),
    (-5,3),(-5,4),(-5,5),(-5,6),(-4,2),(-4,3),(-4,4),(-4,5),(-4,6),
    (-3,2),(-3,5),(-2,0),(-2,1),(-2,4),(-2,5),(-1,-1),(-1,0),(-1,1),
    (-1,2),(-1,3),(-1,4),(0,-2),(0,-1),(0,0),(0,1),(0,2),(0,3),(0,4),
    (1,-2),(1,-1),(1,0),(1,1),(1,2),(1,3),(2,-1),(2,0),(2,1),(3,-1),(3,0),(3,1),(3,2),
)


def shape_is_valid(shape) -> bool:
    status = shape.is_valid
    return bool(status() if callable(status) else status)


def _point(xy):
    return Vector(xy[0], xy[1], 0.0)


def board_wire() -> Wire:
    edges = []
    for feature in CASE_PERIMETER_FEATURES:
        points = tuple(_point(p) for p in feature.points)
        if feature.kind == 'line': edges.append(Edge.make_line(points[0], points[-1]))
        elif feature.kind == 'bezier': edges.append(Edge.make_bezier(*points))
        elif feature.kind == 'arc': edges.append(Edge.make_three_point_arc(points[0], points[1], points[2]))
        else: raise ValueError(feature.kind)
    wire = Wire(edges)
    if not wire.is_closed or not shape_is_valid(wire): raise RuntimeError('invalid analytic perimeter')
    return wire


def raw_offset_wire(distance: float) -> Wire:
    wire = board_wire().offset_2d(distance, kind=Kind.ARC, side=Side.BOTH, closed=True)
    if not isinstance(wire, Wire):
        wires = list(wire.wires())
        if len(wires) != 1: raise RuntimeError(f'offset {distance} wires={len(wires)}')
        wire = wires[0]
    if not wire.is_closed or not shape_is_valid(wire): raise RuntimeError(f'invalid offset {distance}')
    return wire


def cylinder(radius,z0,z1,x,y):
    return Solid.make_cylinder(radius,z1-z0).moved(Location((x,y,z0)))


def extrude_wire(wire,z0,z1):
    return Solid.extrude(Face(wire),Vector(0,0,z1-z0)).moved(Location((0,0,z0)))


def zone_face(xmin,xmax,ymin,ymax):
    return Face(Wire.make_polygon([Vector(xmin,ymin,0),Vector(xmax,ymin,0),Vector(xmax,ymax,0),Vector(xmin,ymax,0)],close=True))


def _single_solid(result,name):
    solids=list(result.solids())
    if len(solids)!=1 or not shape_is_valid(solids[0]): raise RuntimeError(f'{name}: solids={len(solids)}')
    return solids[0].clean()


def _face_pieces(result,name,allow_empty=False):
    candidates=[result] if isinstance(result,Face) else list(result.faces())
    pieces=[face.clean() for face in candidates if face.area>1e-8]
    if not pieces and not allow_empty: raise RuntimeError(f'{name}: no face')
    if any(not shape_is_valid(face) for face in pieces): raise RuntimeError(f'{name}: invalid face')
    return pieces


def support_face(data):
    (a,b,c,d),(m_cd,m_ba)=data
    wire=Wire([Edge.make_line(_point(a),_point(c)),Edge.make_three_point_arc(_point(c),_point(m_cd),_point(d)),Edge.make_line(_point(d),_point(b)),Edge.make_three_point_arc(_point(b),_point(m_ba),_point(a))])
    face=Face(wire)
    if not wire.is_closed or not shape_is_valid(face): raise RuntimeError('invalid support')
    return face


def lower_wall_support_faces():
    return tuple(support_face(data) for data in LOWER_WALL_SUPPORT_DATA)


def rounded_hex_wire(cx,cy,p):
    r=2*p.hex_apothem/sqrt(3)
    pts=((cx-r/2,cy+p.hex_apothem),(cx+r/2,cy+p.hex_apothem),(cx+r,cy),(cx+r/2,cy-p.hex_apothem),(cx-r/2,cy-p.hex_apothem),(cx-r,cy))
    sharp=Wire.make_polygon([_point(q) for q in pts],close=True)
    return sharp.fillet_2d(p.hex_corner_radius,sharp.vertices())


def grid_centers(p):
    pitch_x=p.grid_pitch*sqrt(3)/2
    return tuple((p.grid_seed_x+c*pitch_x,p.grid_seed_y+r*p.grid_pitch+c*p.grid_pitch/2) for c,r in HONEYCOMB_CELL_INDICES)


@dataclass(frozen=True)
class HexCaseParameters:
    z_bottom: float=-8.6
    honeycomb_height: float=3.0
    total_height: float=8.2
    perimeter_clearance: float=3.25
    wall_thickness: float=4.0
    upper_wall_thickness: float=3.0
    tower_top_z: float=-1.6
    bottom_chamfer_height: float=.75
    top_chamfer_height: float=.75
    hex_apothem: float=6.0
    hex_corner_radius: float=1.0
    grid_pitch: float=15.0
    grid_seed_x: float=-11.944374
    grid_seed_y: float=-40.484533
    puck_center_x: float=-46.25704146299772
    puck_center_y: float=-12.099500403571973
    puck_outer_radius: float=23.75
    puck_opening_radius: float=20.75
    foot_pad_radius: float=7.25
    foot_recess_radius: float=5.25
    foot_recess_depth: float=1.25
    boss_outer_radius: float=4.85
    boss_counterbore_radius: float=3.15
    boss_through_radius: float=1.75
    boss_counterbore_height: float=4.2


def lower_cavity_profiles(p):
    cavity=Face(raw_offset_wire(p.perimeter_clearance-p.wall_thickness))
    wide=Face(raw_offset_wire(p.perimeter_clearance-p.upper_wall_thickness))
    profiles=[cavity]
    for name,zone in (("upper controller rail",zone_face(-10.510253,40,.131665,30)),("lower controller rail",zone_face(8.501314,40,-90,-5.601676))):
        profiles.extend(_face_pieces(wide.intersect(zone),name))
    exclusions=(*lower_wall_support_faces(),*(Face(Wire.make_circle(p.boss_outer_radius,Plane(origin=(x,y,0)))) for x,y in MOUNTING_BOSS_CENTERS))
    for i,exclusion in enumerate(exclusions,1):
        next_profiles=[]
        for profile in profiles: next_profiles.extend(_face_pieces(profile.cut(exclusion),f'cavity exclusion {i}',True))
        if not next_profiles: raise RuntimeError(f'cavity exclusion {i} removed cavity')
        profiles=next_profiles
    return tuple(profiles)


def controller_wall_opening():
    cx=12.408097537002; zb,zl,zu,zt=-4.4,-3.4,-1.4,-.4; bh,th,toph=5.,6.,7.; q=sqrt(.5)
    def xz(x,z): return Vector(x,0,z)
    e=[Edge.make_line(xz(cx-bh,zb),xz(cx+bh,zb)),Edge.make_three_point_arc(xz(cx+bh,zb),xz(cx+bh+q,zl-q),xz(cx+th,zl)),Edge.make_line(xz(cx+th,zl),xz(cx+th,zu)),Edge.make_three_point_arc(xz(cx+th,zu),xz(cx+toph-q,zu+q),xz(cx+toph,zt)),Edge.make_line(xz(cx+toph,zt),xz(cx-toph,zt)),Edge.make_three_point_arc(xz(cx-toph,zt),xz(cx-toph+q,zu+q),xz(cx-th,zu)),Edge.make_line(xz(cx-th,zu),xz(cx-th,zl)),Edge.make_three_point_arc(xz(cx-th,zl),xz(cx-bh-q,zl-q),xz(cx-bh,zb))]
    return _single_solid(Solid.extrude(Face(Wire(e)),Vector(0,4,0)).moved(Location((0,12,0))).fix().clean(),'controller opening')


def staged_mounting_bore(x,y,z0,zt,p):
    return _single_solid(cylinder(p.boss_through_radius,z0-.1,zt+.1,x,y).fuse(cylinder(p.boss_counterbore_radius,z0-.1,z0+p.boss_counterbore_height,x,y)).clean(),'mount bore tool')


def build_case_base(p=HexCaseParameters(),*,cut_puck_opening):
    z0=p.z_bottom; zf=z0+p.honeycomb_height; zt=z0+p.total_height; overlap=.01
    body=extrude_wire(raw_offset_wire(p.perimeter_clearance),z0,zt)
    bottom=next(f for f in body.faces() if f.normal_at(f.center()).Z<-.999999 and abs(f.center().Z-z0)<1e-6)
    body=body.chamfer(p.bottom_chamfer_height,None,bottom.edges(),bottom).clean()
    top=next(f for f in body.faces() if f.normal_at(f.center()).Z>.999999 and abs(f.center().Z-zt)<1e-6)
    body=_single_solid(body.chamfer(p.top_chamfer_height,None,top.edges(),top).clean(),'outer moulding')
    for i,profile in enumerate(lower_cavity_profiles(p),1):
        tool=Solid.extrude(profile,Vector(0,0,p.tower_top_z-zf)).moved(Location((0,0,zf)))
        body=_single_solid(body.cut(tool),f'lower cavity {i}')
    body=_single_solid(body.cut(extrude_wire(raw_offset_wire(p.perimeter_clearance-p.upper_wall_thickness),p.tower_top_z-overlap,zt+.1)),'upper cavity')
    body=_single_solid(body.cut(controller_wall_opening()),'controller opening')
    floor_profiles=[Face(raw_offset_wire(p.perimeter_clearance-p.wall_thickness))]
    wide=Face(raw_offset_wire(p.perimeter_clearance-p.upper_wall_thickness))
    for name,zone in (("upper floor rail",zone_face(-10.510253,40,.131665,30)),("lower floor rail",zone_face(8.501314,40,-90,-5.601676))):
        floor_profiles.extend(_face_pieces(wide.intersect(zone).cut(floor_profiles[0]),name,True))
    exclusions=(*lower_wall_support_faces(),*(Face(Wire.make_circle(p.boss_outer_radius,Plane(origin=(x,y,0)))) for x,y in MOUNTING_BOSS_CENTERS))
    for exclusion in exclusions:
        nxt=[]
        for profile in floor_profiles: nxt.extend(_face_pieces(profile.cut(exclusion),'floor exclusion',True))
        floor_profiles=nxt
    prisms=tuple(Solid.extrude(face,Vector(0,0,zf-(z0-.05))).moved(Location((0,0,z0-.05))) for face in floor_profiles)
    hr=2*p.hex_apothem/sqrt(3); keepouts=(*((x,y,p.foot_pad_radius) for x,y in FOOT_RECESS_CENTERS),(p.puck_center_x,p.puck_center_y,p.puck_outer_radius),(*AUXILIARY_PAD_CENTER,AUXILIARY_PAD_RADIUS))
    cutters=[]; bb=body.bounding_box()
    for cx,cy in grid_centers(p):
        if cx+hr<bb.min.X or cx-hr>bb.max.X or cy+p.hex_apothem<bb.min.Y or cy-p.hex_apothem>bb.max.Y: continue
        cell=extrude_wire(rounded_hex_wire(cx,cy,p),z0-.05,zf+overlap); pieces=[]
        for prism in prisms: pieces.extend(s for s in cell.intersect(prism).solids() if s.volume>1e-8)
        for kx,ky,kr in keepouts:
            if (cx-kx)**2+(cy-ky)**2>(hr+kr)**2: continue
            tool=cylinder(kr,z0-.1,zf+.1,kx,ky); nxt=[]
            for piece in pieces: nxt.extend(s for s in piece.cut(tool).solids() if s.volume>1e-8)
            pieces=nxt
        cutters.extend(pieces)
    if cutters: body=_single_solid(body.cut(Compound(cutters)).fix().clean(),'honeycomb')
    if cut_puck_opening: body=_single_solid(body.cut(cylinder(p.puck_opening_radius,z0-.05,zf+overlap,p.puck_center_x,p.puck_center_y)),'puck opening')
    body=_single_solid(body.cut(cylinder(AUXILIARY_OPENING_RADIUS,z0-.05,zf+overlap,*AUXILIARY_PAD_CENTER)),'aux opening')
    for x,y in FOOT_RECESS_CENTERS: body=_single_solid(body.cut(cylinder(p.foot_recess_radius,z0-.05,z0+p.foot_recess_depth,x,y)),'foot recess')
    for x,y in MOUNTING_BOSS_CENTERS: body=_single_solid(body.cut(staged_mounting_bore(x,y,z0,zt,p)),'mount bore')
    return _single_solid(body.fix().clean(),'case base')


@dataclass(frozen=True)
class IntegratedPuckParameters:
    center_x: float=-46.25704146299772
    center_y: float=-12.099500403571973
    outer_radius: float=22.05
    window_inner_radius: float=6.35
    window_outer_radius: float=19.2334344306992
    spoke_half_width: float=2.65
    window_corner_radius: float=2.0
    central_bore_radius: float=2.5527
    fastener_pitch_radius: float=19.05
    fastener_bore_radius: float=1.65
    fastener_boss_radius: float=2.65
    fastener_cone_semi_angle_rad: float=1.029744258677
    tab_radius: float=1.5
    tab_half_span: float=1.15
    tab_radial_offset: float=20.517797152716
    bottom_z: float=-8.6
    web_bottom_z: float=-6.6
    fastener_throat_z: float=-5.6
    web_top_z: float=-4.1
    boss_top_z: float=-1.6


def fastener_centers(p):
    return ((p.center_x-p.fastener_pitch_radius,p.center_y),(p.center_x+p.fastener_pitch_radius,p.center_y),(p.center_x,p.center_y+p.fastener_pitch_radius),(p.center_x,p.center_y-p.fastener_pitch_radius))


def integrated_quadrant_aperture_faces(p):
    annulus=Face(Wire.make_circle(p.window_outer_radius,Plane(origin=(p.center_x,p.center_y,0))),[Wire.make_circle(p.window_inner_radius,Plane(origin=(p.center_x,p.center_y,0)))])
    span=p.window_outer_radius+2
    cross=_face_pieces(zone_face(p.center_x-p.spoke_half_width,p.center_x+p.spoke_half_width,p.center_y-span,p.center_y+span).fuse(zone_face(p.center_x-span,p.center_x+span,p.center_y-p.spoke_half_width,p.center_y+p.spoke_half_width)),'spoke cross')[0]
    quadrants=_face_pieces(annulus.cut(cross),'quadrant windows')
    if len(quadrants)!=4: raise RuntimeError(f'quadrants={len(quadrants)}')
    return tuple(face.fillet_2d(p.window_corner_radius,face.vertices()).clean() for face in quadrants)


def capsule_solid(first,second,radius,z0,z1):
    wire=Edge.make_line(_point(first),_point(second)).offset_2d(radius,kind=Kind.ARC,side=Side.BOTH,closed=True)
    if not isinstance(wire,Wire): wire=list(wire.wires())[0]
    return extrude_wire(wire,z0,z1)


def build_opening_case():
    return build_case_base(HexCaseParameters(),cut_puck_opening=True)


def build_integrated_case():
    case=build_case_base(HexCaseParameters(),cut_puck_opening=False); p=IntegratedPuckParameters()
    body=_single_solid(case.fuse(cylinder(p.outer_radius,p.bottom_z,p.web_top_z,p.center_x,p.center_y)).clean(),'puck plate')
    fasteners=fastener_centers(p)
    tabs=(((p.center_x+p.tab_radial_offset,p.center_y-p.tab_half_span),(p.center_x+p.tab_radial_offset,p.center_y+p.tab_half_span)),((p.center_x-p.tab_radial_offset,p.center_y-p.tab_half_span),(p.center_x-p.tab_radial_offset,p.center_y+p.tab_half_span)),((p.center_x-p.tab_half_span,p.center_y+p.tab_radial_offset),(p.center_x+p.tab_half_span,p.center_y+p.tab_radial_offset)),((p.center_x-p.tab_half_span,p.center_y-p.tab_radial_offset),(p.center_x+p.tab_half_span,p.center_y-p.tab_radial_offset)))
    for (x,y),(first,second) in zip(fasteners,tabs):
        body=_single_solid(body.fuse(cylinder(p.fastener_boss_radius,p.web_top_z,p.boss_top_z,x,y)).fuse(capsule_solid(first,second,p.tab_radius,p.web_top_z,p.boss_top_z)).clean(),'boss tab')
    windows=tuple(Solid.extrude(face,Vector(0,0,p.web_top_z-p.web_bottom_z)).moved(Location((0,0,p.web_bottom_z))) for face in integrated_quadrant_aperture_faces(p))
    central=cylinder(p.central_bore_radius,p.bottom_z-.05,p.web_top_z+.05,p.center_x,p.center_y)
    h=p.fastener_bore_radius/tan(p.fastener_cone_semi_angle_rad); apex=p.fastener_throat_z-h; bores=[]
    for x,y in fasteners:
        taper=Solid.make_cone(0,p.fastener_bore_radius,h,Plane(origin=(x,y,apex)))
        straight=cylinder(p.fastener_bore_radius,p.fastener_throat_z,p.boss_top_z+.05,x,y)
        bores.append(_single_solid(taper.fuse(straight).clean(),'fastener tool'))
    return _single_solid(body.cut(Compound((*windows,central,*bores))).fix().clean(),'integrated case')


def export_both(output_dir=Path('generated')):
    output_dir.mkdir(parents=True,exist_ok=True)
    for name,builder in (('dilemma_case_integrated_tenting_puck',build_integrated_case),('dilemma_case_tenting_puck_opening',build_opening_case)):
        part=builder(); export_step(part,output_dir/f'{name}.step'); export_stl(part,output_dir/f'{name}.stl',tolerance=.001,angular_tolerance=.02)
        print(f'BUILT {name} solids={len(part.solids())} volume={part.volume:.12f} area={part.area:.12f}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',type=Path,default=Path('generated')); args=parser.parse_args(); export_both(args.output_dir)
