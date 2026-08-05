from __future__ import annotations

import json
import traceback
from pathlib import Path

from build123d import CenterOf, Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "kailh_reference.step"
OUT = ROOT / "results_spline"
OUT.mkdir(exist_ok=True)

X0 = 5.010191487800
X1 = X0 + 2.0
ROLL_RADIUS = 0.375
JUNCTION_RADIUS = 0.07
TOP_Z = 1.75
PAD_Z1 = 1.80
SPANS = (
    ((6.26449438808344, 1.75), (6.037652643286782, 1.7464977207059593), (5.948216212731957, 1.1627540082312793), (5.931167511145697, 0.9908398685910332)),
    ((5.931167511145697, 0.9908398685910332), (5.927754127720061, 0.9564203046194658), (5.922888677847069, 0.7445394664677538), (5.9056168509451865, 0.7353586477870302)),
    ((5.9056168509451865, 0.7353586477870302), (5.880620638817342, 0.7220719414904516), (5.853618519895407, 0.842675012490237), (5.847148297690575, 0.8600319632961385)),
    ((5.847148297690575, 0.8600319632961385), (5.816949601881485, 0.9410426706516545), (5.774807438674499, 1.0176881094435422), (5.727176591347377, 1.0896800429967701)),
    ((5.727176591347377, 1.0896800429967701), (5.581540119368333, 1.3098031733210076), (5.34929696093493, 1.5421574803805749), (5.070910946871318, 1.561888982007823)),
    ((5.070910946871318, 1.561888982007823), (4.750995222704022, 1.5845640350388521), (4.5310337517931325, 1.291336161578472), (4.409299950016339, 1.0327790431952582)),
    ((4.409299950016339, 1.0327790431952582), (4.390241682529478, 0.9923001404512655), (4.2790421668386305, 0.6963848252000207), (4.268512060541968, 0.6942119954420493)),
    ((4.268512060541968, 0.6942119954420493), (4.2637523122493635, 0.6932298474523463), (4.259899087895539, 0.6960508690099316), (4.256802438167436, 0.6992378869858319)),
    ((4.256802438167436, 0.6992378869858319), (4.235761897724996, 0.7208924448146236), (4.239333497876836, 0.9743776290012744), (4.234772130300953, 1.0251152351594182)),
    ((4.234772130300953, 1.0251152351594182), (4.216801197009745, 1.2250118934432974), (4.175010164179821, 1.7476386118392202), (3.90576714704497, 1.75)),
)


def bezier(span, t):
    u = 1.0 - t
    return tuple(
        u**3 * span[0][i] + 3*u*u*t * span[1][i] + 3*u*t*t * span[2][i] + t**3 * span[3][i]
        for i in range(2)
    )


def landmark_points(mode):
    mids = {
        "endpoints11": set(),
        "landmarks15": {0, 4, 5, 9},
        "adaptive19": {0, 1, 2, 3, 4, 5, 6, 9},
    }[mode]
    pts = [SPANS[0][0]]
    for i, span in enumerate(SPANS):
        if i in mids:
            pts.append(bezier(span, 0.5))
        pts.append(span[3])
    return pts


def closed_wire(edges):
    wires = Wire.combine(edges, tol=1e-7)
    if len(wires) != 1:
        raise RuntimeError(f"expected one wire, got {len(wires)}")
    return wires[0]


def profile_face(mode, x):
    yz = landmark_points(mode)
    curve = Edge.make_spline([(x, y, z) for y, z in yz])
    top = Edge.make_line((x, yz[-1][0], yz[-1][1]), (x, yz[0][0], yz[0][1]))
    return Face(closed_wire([curve, top])), curve


def shape_single(shape, label):
    solids = shape.solids()
    if len(solids) != 1:
        raise RuntimeError(f"{label}: expected one solid, got {len(solids)}")
    solid = solids[0]
    if not solid.is_valid:
        raise RuntimeError(f"{label}: invalid solid")
    return solid


def metrics(shape):
    b = shape.bounding_box()
    c = shape.center(CenterOf.MASS)
    return {
        "valid": bool(shape.is_valid), "volume": float(shape.volume), "area": float(shape.area),
        "bbox": [b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],
        "com": [c.X,c.Y,c.Z], "faces": len(shape.faces()), "edges": len(shape.edges()),
    }


def edge_record(i, e):
    b=e.bounding_box()
    try: gt=str(e.geom_type)
    except Exception: gt="unknown"
    return {"index":i,"geom_type":gt,"length":e.length,
            "bbox":[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],
            "start":list(e.position_at(0)),"end":list(e.position_at(1))}


def exact_xor(a,b):
    am=a.cut(b); bm=b.cut(a)
    av=float(am.volume); bv=float(bm.volume)
    return {"a_minus_b":av,"b_minus_a":bv,"xor_volume":av+bv,
            "xor_pct":100.0*(av+bv)/float(a.volume)}


def pad():
    pts=[
        (4.54488778941404,3.76578476453536,TOP_Z),
        (7.210189558447279,3.7479184533604792,TOP_Z),
        (7.21019340060459,6.41087029507891,TOP_Z),
        (4.54488778941404,6.41087029507891,TOP_Z),
    ]
    w=closed_wire([Edge.make_line(pts[i],pts[(i+1)%4]) for i in range(4)])
    return shape_single(extrude(Face(w),PAD_Z1-TOP_Z,dir=(0,0,1)),"pad")


def terminal_curve(raw):
    candidates=[]
    records=[]
    for i,e in enumerate(raw.edges()):
        records.append(edge_record(i,e))
        b=e.bounding_box()
        if abs(b.min.X-X1)<1e-5 and abs(b.max.X-X1)<1e-5 and e.length>4.0:
            candidates.append((i,e))
    if len(candidates)!=1:
        raise RuntimeError(f"terminal spline candidates={len(candidates)}")
    return records,candidates[0]


def junction_candidates(rolled):
    records=[]; candidates=[]
    for i,e in enumerate(rolled.edges()):
        rec=edge_record(i,e); records.append(rec)
        b=e.bounding_box()
        if abs(b.min.Z-TOP_Z)<2e-4 and abs(b.max.Z-TOP_Z)<2e-4 and b.max.X>X1-0.02 and b.min.X>X1-ROLL_RADIUS-0.02:
            candidates.append((i,e))
    return records,candidates


def build_mode(mode):
    face,curve=profile_face(mode,X0)
    raw=shape_single(extrude(face,2.0,dir=(1,0,0)),"raw")
    raw_records,(term_i,term)=terminal_curve(raw)
    rolled=shape_single(fillet([term],ROLL_RADIUS),"R0.375 terminal blend")
    rolled_records,jedges=junction_candidates(rolled)
    variants=[("no_junction",[])]
    variants += [(f"junction_{i}",[(i,e)]) for i,e in jedges]
    if len(jedges)>1:
        variants.append(("junction_all",jedges))
    rows=[]
    for vname,selected in variants:
        row={"variant":vname,"selected":[i for i,_ in selected]}
        try:
            formed=rolled if not selected else shape_single(fillet([e for _,e in selected],JUNCTION_RADIUS),"R0.07 junction")
            final=shape_single(formed.fuse(pad()).clean(),"final")
            row.update({"formed":metrics(formed),"final":metrics(final),"solid":final})
        except Exception as exc:
            row["error"]=f"{type(exc).__name__}: {exc}"
            row["traceback"]=traceback.format_exc()
        rows.append(row)
    return {
        "mode":mode,"point_count":len(landmark_points(mode)),
        "profile_area":face.area,"profile_curve_length":curve.length,
        "raw":metrics(raw),"raw_edges":raw_records,"terminal_edge":term_i,
        "rolled":metrics(rolled),"rolled_edges":rolled_records,
        "junction_candidates":[i for i,_ in jedges],"variants":rows,
    }


def main():
    all_ref=import_step(REFERENCE)
    refs=[s for s in all_ref.solids() if 1.7<s.volume<1.9 and s.center(CenterOf.MASS).X>0]
    if len(refs)!=1: raise RuntimeError(f"reference solder count={len(refs)}")
    ref=refs[0]
    report={"reference":metrics(ref),"modes":[]}
    for mode in ("endpoints11","landmarks15","adaptive19"):
        entry={"mode":mode}
        try:
            data=build_mode(mode)
            for row in data["variants"]:
                if "solid" in row:
                    solid=row.pop("solid")
                    row["exact_xor"]=exact_xor(ref,solid)
                    stem=f"{mode}_{row['variant']}"
                    export_step(solid,OUT/f"{stem}.step")
                    export_stl(solid,OUT/f"{stem}.stl",tolerance=0.01,angular_tolerance=0.05,ascii_format=True)
            entry=data
        except Exception as exc:
            entry["error"]=f"{type(exc).__name__}: {exc}"
            entry["traceback"]=traceback.format_exc()
        report["modes"].append(entry)
        (OUT/"spline_search_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
