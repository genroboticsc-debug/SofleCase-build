from __future__ import annotations
import json, math
from pathlib import Path
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

Z_LOCAL=30.805714882516945
T=(8.878417177497228,-12.630815719428673,-24.256343014615943)
Z0=Z_LOCAL+T[2]

def read(path):
 r=STEPControl_Reader(); s=int(r.ReadFile(str(path))); assert s==int(IFSelect_RetDone); r.TransferRoots(); return r.OneShape()
def exp(shape,typ):
 x=TopExp_Explorer(shape,typ); out=[]
 while x.More():
  q=x.Current()
  if typ==TopAbs_SOLID:q=TopoDS.Solid_s(q)
  elif typ==TopAbs_FACE:q=TopoDS.Face_s(q)
  elif typ==TopAbs_EDGE:q=TopoDS.Edge_s(q)
  out.append(q); x.Next()
 return out
def same(a,b):return bool(a.IsSame(b))
def length(e):
 g=GProp_GProps(); BRepGProp.LinearProperties_s(e,g); return float(g.Mass())
def sample(e,n=161):
 c=BRepAdaptor_Curve(e); a=float(c.FirstParameter()); b=float(c.LastParameter()); out=[]
 for i in range(n):
  p=c.Value(a+(b-a)*i/(n-1)); out.append((float(p.X()),float(p.Y()),float(p.Z())))
 return out
def stats(A,B):
 ds=[min(math.hypot(a[0]-b[0],a[1]-b[1]) for b in B) for a in A]
 m=sum(ds)/len(ds); return {'mean':m,'min':min(ds),'max':max(ds),'spread':max(ds)-min(ds),'rms':math.sqrt(sum((d-m)**2 for d in ds)/len(ds))}

root=read('reference/Mouse.STEP'); solids=exp(root,TopAbs_SOLID)
# RightButtons is the unique 183-face / ~2108.521 mm3 solid.
rows=[]
for si,s in enumerate(solids,1):
 g=GProp_GProps(); BRepGProp.VolumeProperties_s(s,g); rows.append((si,float(g.Mass()),len(exp(s,TopAbs_FACE))))
si=min(rows,key=lambda r:abs(r[1]-2108.5211808863587))[0]
rb=solids[si-1]; faces=exp(rb,TopAbs_FACE)
unique=[]
for e in exp(rb,TopAbs_EDGE):
 if not any(same(e,u) for u in unique):unique.append(e)
face_edges=[]
for f in faces:
 ids=[]
 for e in exp(f,TopAbs_EDGE):
  j=next(j for j,u in enumerate(unique) if same(e,u))
  if j not in ids:ids.append(j)
 face_edges.append(ids)
edge_faces=[[] for _ in unique]
for fi,ids in enumerate(face_edges,1):
 for j in ids:edge_faces[j].append(fi)
E=[]
for j,e in enumerate(unique):
 try:pts=sample(e)
 except:pts=[]
 E.append({'id':j+1,'length':length(e),'faces':edge_faces[j],'pts':pts,'flat':bool(pts and max(abs(p[2]-Z0) for p in pts)<2e-6)})
# Exact lower rails are the long base-datum edges owned by F111/F116.
target=[]
for fi in (111,116):
 for j in face_edges[fi-1]:
  if E[j]['flat'] and E[j]['length']>1.0 and j not in target:target.append(j)
# search every other edge for geometric parallel/offset relation to each lower rail
matches=[]
for ti in target:
 A=E[ti]['pts']
 for cj,r in enumerate(E):
  if cj==ti or len(r['pts'])<5 or r['length']<0.5:continue
  lr=r['length']/E[ti]['length']
  if not 0.3<lr<3.5:continue
  ab=stats(A,r['pts']); ba=stats(r['pts'],A)
  if min(ab['mean'],ba['mean'])<5:
   score=ab['rms']+ba['rms']+.25*(ab['spread']+ba['spread'])
   matches.append({'target':ti+1,'candidate':cj+1,'target_faces':E[ti]['faces'],'candidate_faces':r['faces'],'target_length':E[ti]['length'],'candidate_length':r['length'],'candidate_flat':r['flat'],'AtoB':ab,'BtoA':ba,'score':score})
matches.sort(key=lambda x:x['score'])
# explicit cross-section relation to F128/F129 shared edges
shared={}
for a,b in ((111,128),(116,129),(111,116),(128,129)):
 ids=sorted(set(face_edges[a-1]).intersection(face_edges[b-1])); shared[f'{a}-{b}']=[{'id':i+1,'length':E[i]['length'],'pts0':E[i]['pts'][0] if E[i]['pts'] else None,'pts1':E[i]['pts'][-1] if E[i]['pts'] else None} for i in ids]
out={'solid_inventory':rows,'rightbuttons_solid_index':si,'occurrence_translation':T,'base_global_z':Z0,'target_rails':[i+1 for i in target],'shared_edges':shared,'best_offset_candidates':matches[:80]}
Path('mouse_runtime/rightbuttons_offset_analysis.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'solid_inventory':rows,'rightbuttons_solid_index':si,'base_global_z':Z0,'target_rails':[i+1 for i in target],'shared_edges':shared,'best_offset_candidates':matches[:20]},indent=2))
