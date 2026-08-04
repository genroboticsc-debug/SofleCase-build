#!/usr/bin/env python3
"""Apply the robust piecewise cavity/floor construction to the materialized source."""
from pathlib import Path

path = Path(__file__).with_name("dilemma_tenting_puck_family.py")
source = path.read_text(encoding="utf-8")
start = source.index(
    "    lower=Face(raw_offset_wire(p.perimeter_clearance-p.wall_thickness))\n",
    source.index("def build_opening_case"),
)
end = source.index(
    "    body=one(body.cut(extrude_wire(raw_offset_wire(p.perimeter_clearance-p.upper_wall_thickness),",
    start,
)
lower = '''    lower_face=native_controller_cavity_face_exact(
        Face(raw_offset_wire(p.perimeter_clearance-p.wall_thickness))
    )
    lower_solid=Solid.extrude(
        lower_face,Vector(0,0,p.tower_top_z-zf)
    ).moved(Location((0,0,zf)))
    wide_solid=extrude_wire(
        raw_offset_wire(p.perimeter_clearance-p.upper_wall_thickness),
        zf,p.tower_top_z,
    )
    cavity_pieces=[lower_solid]
    for zone in (
        zone_face(-10.510253,40,.131665,30),
        zone_face(8.501314,40,-90,-5.601676),
    ):
        zone_solid=Solid.extrude(
            zone,Vector(0,0,p.tower_top_z-zf)
        ).moved(Location((0,0,zf)))
        cavity_pieces.extend(pieces(wide_solid.intersect(zone_solid)))
    for support in support_solids(zf,p.tower_top_z):
        next_pieces=[]
        for cavity_piece in cavity_pieces:
            next_pieces.extend(pieces(cavity_piece.cut(support)))
        cavity_pieces=next_pieces
    for x,y in MOUNTING_BOSS_CENTERS:
        keepout=cylinder(p.boss_outer_radius,zf,p.tower_top_z,x,y)
        next_pieces=[]
        for cavity_piece in cavity_pieces:
            next_pieces.extend(pieces(cavity_piece.cut(keepout)))
        cavity_pieces=next_pieces
    for index,cavity_piece in enumerate(cavity_pieces,1):
        body=one(body.cut(cavity_piece),f"lower cavity piece {index}")
'''
source = source[:start] + lower + source[end:]

start = source.index(
    "    region=floor_vent_region_face_exact(p)\n",
    source.index("def build_opening_case"),
)
end = source.index("    if cut_puck_opening:\n", start)
floor = '''    floor_core=extrude_wire(
        raw_offset_wire(p.perimeter_clearance-p.wall_thickness),z0-.05,zf
    )
    board_prism=extrude_wire(board_wire(),z0-.05,zf)
    floor_relief_pieces=[]
    for zone in (
        zone_face(-10.510253,40,.131665,30),
        zone_face(8.501314,40,-90,.131665),
    ):
        zone_solid=Solid.extrude(
            zone,Vector(0,0,zf-(z0-.05))
        ).moved(Location((0,0,z0-.05)))
        for relief in pieces(board_prism.intersect(zone_solid)):
            floor_relief_pieces.extend(pieces(relief.cut(floor_core)))
    keepouts=(
        *((x,y,p.foot_keepout_radius) for x,y in FOOT_RECESS_CENTERS),
        *((x,y,p.boss_outer_radius) for x,y in MOUNTING_BOSS_CENTERS),
        (p.puck_center_x,p.puck_center_y,p.puck_outer_radius),
        (*AUXILIARY_PAD_CENTER,AUXILIARY_PAD_RADIUS),
    )
    floor_supports=support_solids(z0-.05,zf+.05)
    cutters=[]
    hr=2*p.hex_apothem/sqrt(3)
    bb=body.bounding_box()
    for cx,cy in grid_centers(p):
        if cx+hr<bb.min.X or cx-hr>bb.max.X or cy+p.hex_apothem<bb.min.Y or cy-p.hex_apothem>bb.max.Y:
            continue
        cell=extrude_wire(rounded_hex_wire(cx,cy,p),z0-.05,zf)
        ps=pieces(cell.intersect(floor_core))
        for relief in floor_relief_pieces:
            ps.extend(pieces(cell.intersect(relief)))
        for kx,ky,kr in keepouts:
            if (cx-kx)**2+(cy-ky)**2>(hr+kr)**2: continue
            next_ps=[]
            for q in ps:
                next_ps.extend(pieces(q.cut(cylinder(kr,z0-.1,zf+.1,kx,ky))))
            ps=next_ps
        for support in floor_supports:
            next_ps=[]
            for q in ps:
                next_ps.extend(pieces(q.cut(support)))
            ps=next_ps
        cutters.extend(ps)
    for cutter in cutters:
        cut_pieces=pieces(body.cut(cutter))
        if len(cut_pieces)==1:
            body=cut_pieces[0]
    if cutters:
        body=one(body.clean(),"honeycomb floor")

'''
source = source[:start] + floor + source[end:]
path.write_text(source, encoding="utf-8")
print(f"applied piecewise baseline refinement: {path.stat().st_size} bytes")
