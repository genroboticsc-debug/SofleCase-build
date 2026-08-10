from __future__ import annotations

import json, math
from pathlib import Path

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

REF=Path('reference/Mouse.STEP')
OUT=Path('mouse_runtime/rightbuttons_authority_analysis.json')
Z0=30.805714882516945


def read_step(path):
    r=STEPControl_Reader()
    s=int(r.ReadFile(str(path)))
    if s != int(IFSelect_RetDone):
        raise RuntimeError((path,s))
    r.TransferRoots()
    return r.OneShape()


def explore(shape, typ):
    ex=TopExp_Explorer(shape,typ); out=[]
    while ex.More(): out.append(ex.Current()); ex.Next()
    return out


def edge_length(edge):
    g=GProp_GProps(); BRepGProp.LinearProperties_s(edge,g); return float(g.Mass())


def xyz(p): return [float(p.X()),float(p.Y()),float(p.Z())]

def sample_edge(edge,n=81):
    c=BRepAdaptor_Curve(edge); a=float(c.FirstParameter()); b=float(c.LastParameter())
    if not (math.isfinite(a) and math.isfinite(b)) or abs(b-a)>1e8:
        return []
    pts=[]
    for i in range(n):
        u=a+(b-a)*i/(n-1)
        try: pts.append(xyz(c.Value(u)))
        except Exception: pass
    return pts


def bbox_pts(pts):
    if not pts: return None
    return [[min(p[k] for p in pts) for k in range(3)],[max(p[k] for p in pts) for k in range(3)]]


def curve_type(edge):
    try: return int(BRepAdaptor_Curve(edge).GetType())
    except Exception: return None

def surf_type(face):
    try: return int(BRepAdaptor_Surface(face).GetType())
    except Exception: return None


def same(a,b): return bool(a.IsSame(b))

root=read_step(REF)
solids=explore(root,TopAbs_SOLID)
if len(solids)!=10: raise RuntimeError(f'expected 10 solids, got {len(solids)}')
rb=solids[-1]
faces=explore(rb,TopAbs_FACE)
edges=explore(rb,TopAbs_EDGE)

# de-duplicate global edges by topology identity
unique=[]
for e in edges:
    if not any(same(e,u) for u in unique): unique.append(e)

# face-edge ownership and adjacency
face_edges=[]
for f in faces:
    fes=[]
    for e in explore(f,TopAbs_EDGE):
        idx=next(i for i,u in enumerate(unique) if same(e,u))
        if idx not in fes: fes.append(idx)
    face_edges.append(fes)

edge_faces=[[] for _ in unique]
for fi,fes in enumerate(face_edges,1):
    for ei in fes: edge_faces[ei].append(fi)

edge_rows=[]
for ei,e in enumerate(unique):
    pts=sample_edge(e)
    edge_rows.append({
        'edge':ei+1,
        'type':curve_type(e),
        'length':edge_length(e),
        'faces':edge_faces[ei],
        'bbox':bbox_pts(pts),
        'z0_flat': bool(pts and max(abs(p[2]-Z0) for p in pts)<2e-6),
        'endpoints':[pts[0],pts[-1]] if pts else None,
        'samples':pts,
    })

focus={}
for fi in [111,116,128,129]:
    if 1 <= fi <= len(faces):
        focus[str(fi)]={
            'surface_type':surf_type(faces[fi-1]),
            'edges':[edge_rows[i] for i in face_edges[fi-1]],
            'neighbor_faces':sorted({n for i in face_edges[fi-1] for n in edge_faces[i] if n!=fi}),
        }

# Candidate target rails: any edge belonging to F111/F116 and lying completely on base-top datum.
target_ids=[]
for fi in [111,116]:
    if 1 <= fi <= len(face_edges):
        for ei in face_edges[fi-1]:
            if edge_rows[ei]['z0_flat'] and ei not in target_ids: target_ids.append(ei)

# Compare every other sufficiently curved/long edge to each target by sample-wise nearest distances in XY.
# Analysis only: this is hypothesis discovery, never production geometry.
def dist2(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def nearest_stats(A,B):
    if len(A)<5 or len(B)<5: return None
    ds=[]
    for a in A:
        ds.append(min(dist2(a,b) for b in B))
    mean=sum(ds)/len(ds); rms=math.sqrt(sum((d-mean)**2 for d in ds)/len(ds))
    return {'mean':mean,'min':min(ds),'max':max(ds),'spread':max(ds)-min(ds),'rms_about_mean':rms}

matches=[]
for ti in target_ids:
    A=edge_rows[ti]['samples']
    for cj,row in enumerate(edge_rows):
        if cj==ti or row['length']<0.2 or len(row['samples'])<5: continue
        s1=nearest_stats(A,row['samples']); s2=nearest_stats(row['samples'],A)
        if not s1 or not s2: continue
        # keep strongest candidates: near-constant distance under 5 mm and roughly comparable extent
        length_ratio=row['length']/edge_rows[ti]['length'] if edge_rows[ti]['length'] else 999
        score=s1['rms_about_mean']+s2['rms_about_mean']+0.25*(s1['spread']+s2['spread'])
        if min(s1['mean'],s2['mean']) < 5.0 and 0.3 < length_ratio < 3.5:
            matches.append({
                'target_edge':ti+1,'candidate_edge':cj+1,
                'target_faces':edge_rows[ti]['faces'],'candidate_faces':row['faces'],
                'target_length':edge_rows[ti]['length'],'candidate_length':row['length'],
                'candidate_type':row['type'],'candidate_z0_flat':row['z0_flat'],
                'A_to_B':s1,'B_to_A':s2,'score':score,
                'candidate_endpoints':row['endpoints'],
            })
matches.sort(key=lambda x:x['score'])

# Compact list of all non-line-like or focus-adjacent edges to make human review easier.
interesting=[]
focus_face_set={111,116,128,129}
for row in edge_rows:
    if row['type'] not in (0,None) or focus_face_set.intersection(row['faces']):
        rr={k:v for k,v in row.items() if k!='samples'}
        interesting.append(rr)

out={
    'reference_sha_expected':'fcd48ca5636fab4cb3f0ed3c69e3f7dbe00cca3c27cbb77c41fdd25bed5238cb',
    'solid_count':len(solids),'rightbuttons_face_count':len(faces),'unique_edge_count':len(unique),
    'focus':focus,'target_rail_edges':[i+1 for i in target_ids],
    'best_offset_candidates':matches[:100],
    'interesting_edges':interesting,
}
OUT.write_text(json.dumps(out,indent=2))
print(json.dumps({
    'face_count':len(faces),'unique_edges':len(unique),'target_rail_edges':[i+1 for i in target_ids],
    'focus':focus,'best_offset_candidates':matches[:20],
},indent=2))
