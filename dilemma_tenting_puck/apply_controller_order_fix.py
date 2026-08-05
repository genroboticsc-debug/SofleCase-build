#!/usr/bin/env python3
"""Make the exact controller replacement independent of wire start-edge ordering."""
from pathlib import Path
path=Path(__file__).with_name('dilemma_tenting_puck_family.py')
s=path.read_text()
a=s.index('def native_controller_cavity_face_exact(cavity_face):\n')
b=s.index('\n\ndef controller_wall_opening():',a)
new='''def native_controller_cavity_face_exact(cavity_face):
    edges=list(cavity_face.outer_wire().order_edges())
    candidates=[i for i,e in enumerate(edges)
        if e.geom_type.name=="LINE" and e.bounding_box().min.X < -24.7
        and e.bounding_box().max.X > -24.2
        and 13.0 < e.bounding_box().min.Y < 13.2]
    if len(candidates)!=1: raise RuntimeError(f"controller join candidates {candidates}")
    li=candidates[0]
    terraces=[i for i,e in enumerate(edges) if e.geom_type.name=="LINE"
        and e.length>30 and abs(e.bounding_box().min.Y-12.6555)<.01]
    if len(terraces)!=1: raise RuntimeError(f"controller terrace candidates {terraces}")
    ti=terraces[0]
    if ti < li:
        edges=edges[li:]+edges[:li]
        ti=(ti-li)%len(edges)
        li=0
    ls=edges[li].vertices()[0]; re=edges[ti].vertices()[-1]
    p0=_point(-24.077079461468443,13.015444596428026)
    p1=_point(-23.776042271076335,13.015444596428026)
    p2=_point(-22.043991463507460,12.015444596428027)
    p3=_point(-12.242330585806730,12.015444596428027)
    p4=_point(-10.242330585806730,14.015444596428027)
    p5=_point(-9.540174793573136,13.959978596162381)
    p6=_point(-8.853120822958800,13.802639149346222)
    p7=_point(-6.321693815707628,12.848273141887887)
    p8=_point(-5.703402751805730,12.706680592863014)
    p9=_point(-5.057428599478593,12.655652597508022)
    rep=[
        Edge.make_line(ls,p0),Edge.make_line(p0,p1),
        Edge.make_three_point_arc(p1,_point(-23.043991463507460,12.283393788858905),p2),
        Edge.make_line(p2,p3),
        Edge.make_three_point_arc(p3,_point(-10.828117023433921,12.601231034054932),p4),
        Edge.make_line(p4,p5),Edge.make_line(p5,p6),Edge.make_line(p6,p7),
        Edge.make_line(p7,p8),Edge.make_line(p8,p9),Edge.make_line(p9,re)]
    w=Wire(edges[:li]+rep+edges[ti+1:])
    if not w.is_closed or not valid(w):
        raise RuntimeError("native controller cavity replacement produced invalid wire")
    return Face(w)
'''
s=s[:a]+new+s[b:]
path.write_text(s)
print('applied controller order fix')
