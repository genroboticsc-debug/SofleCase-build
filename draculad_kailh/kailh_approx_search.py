from __future__ import annotations

import inspect
import json
import traceback
from pathlib import Path

from build123d import CenterOf, Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step

ROOT=Path(__file__).resolve().parent
REFERENCE=ROOT/'kailh_reference.step'
OUT=ROOT/'results_approx'; OUT.mkdir(exist_ok=True)
X0=5.010191487800; X1=X0+2.0
ROLL=0.375; JUNCTION=0.07; TOP=1.75; PAD_TOP=1.80
REF_PROFILE_AREA=0.9075354150773971
REF_PROFILE_LENGTH=4.851046962108225
SPANS=(
((6.26449438808344,1.75),(6.037652643286782,1.7464977207059593),(5.948216212731957,1.1627540082312793),(5.931167511145697,0.9908398685910332)),
((5.931167511145697,0.9908398685910332),(5.927754127720061,0.9564203046194658),(5.922888677847069,0.7445394664677538),(5.9056168509451865,0.7353586477870302)),
((5.9056168509451865,0.7353586477870302),(5.880620638817342,0.7220719414904516),(5.853618519895407,0.842675012490237),(5.847148297690575,0.8600319632961385)),
((5.847148297690575,0.8600319632961385),(5.816949601881485,0.9410426706516545),(5.774807438674499,1.0176881094435422),(5.727176591347377,1.0896800429967701)),
((5.727176591347377,1.0896800429967701),(5.581540119368333,1.3098031733210076),(5.34929696093493,1.5421574803805749),(5.070910946871318,1.561888982007823)),
((5.070910946871318,1.561888982007823),(4.750995222704022,1.5845640350388521),(4.5310337517931325,1.291336161578472),(4.409299950016339,1.0327790431952582)),
((4.409299950016339,1.0327790431952582),(4.390241682529478,0.9923001404512655),(4.2790421668386305,0.6963848252000207),(4.268512060541968,0.6942119954420493)),
((4.268512060541968,0.6942119954420493),(4.2637523122493635,0.6932298474523463),(4.259899087895539,0.6960508690099316),(4.256802438167436,0.6992378869858319)),
((4.256802438167436,0.6992378869858319),(4.235761897724996,0.7208924448146236),(4.239333497876836,0.9743776290012744),(4.234772130300953,1.0251152351594182)),
((4.234772130300953,1.0251152351594182),(4.216801197009745,1.2250118934432974),(4.175010164179821,1.7476386118392202),(3.90576714704497,1.75)),
)

def bezier(s,t):
 u=1-t
 return tuple(u**3*s[0][i]+3*u*u*t*s[1][i]+3*u*t*t*s[2][i]+t**3*s[3][i] for i in range(2))

def points(mode):
 if mode=='landmarks15': mids={0,4,5,9}; samples={i:(0.5,) if i in mids else () for i in range(10)}
 elif mode=='adaptive19': mids={0,1,2,3,4,5,6,9}; samples={i:(0.5,) if i in mids else () for i in range(10)}
 elif mode=='analysis31': samples={i:(1/3,2/3) for i in range(10)}
 else: raise ValueError(mode)
 out=[SPANS[0][0]]
 for i,s in enumerate(SPANS):
  out.extend(bezier(s,t) for t in samples[i]); out.append(s[3])
 return out

def wire(edges):
 w=Wire.combine(edges,tol=1e-7)
 if len(w)!=1: raise RuntimeError(f'wire count={len(w)}')
 return w[0]

def one(shape,label):
 ss=shape.solids()
 if len(ss)!=1 or not ss[0].is_valid: raise RuntimeError(f'{label}: solids={len(ss)} valid={ss[0].is_valid if ss else None}')
 return ss[0]

def metrics(s):
 b=s.bounding_box(); c=s.center(CenterOf.MASS)
 return {'volume':float(s.volume),'area':float(s.area),'bbox':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],
         'com':[c.X,c.Y,c.Z],'faces':len(s.faces()),'edges':len(s.edges()),'valid':bool(s.is_valid)}

def erec(i,e):
 b=e.bounding_box()
 try:g=str(e.geom_type)
 except Exception:g='?'
 return {'i':i,'g':g,'L':e.length,'bbox':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z]}

def make_approx(ps,tol):
 attempts=[{'tolerance':tol},{'tol':tol},{'tolerance':tol,'min_degree':3,'max_degree':8},{'tol':tol,'min_degree':3,'max_degree':8}]
 errors=[]
 for kw in attempts:
  try:return Edge.make_spline_approx(ps,**kw),kw
  except TypeError as e: errors.append(str(e))
 raise TypeError(' | '.join(errors))

def profile(mode,tol,x):
 ps=[(x,y,z) for y,z in points(mode)]
 curve,kwargs=make_approx(ps,tol)
 top=Edge.make_line((x,ps[-1][1],ps[-1][2]),(x,ps[0][1],ps[0][2]))
 f=Face(wire([curve,top]))
 return f,curve,kwargs

def pad():
 ps=[(4.54488778941404,3.76578476453536,TOP),(7.210189558447279,3.7479184533604792,TOP),
     (7.21019340060459,6.41087029507891,TOP),(4.54488778941404,6.41087029507891,TOP)]
 return one(extrude(Face(wire([Edge.make_line(ps[i],ps[(i+1)%4]) for i in range(4)])),PAD_TOP-TOP,dir=(0,0,1)),'pad')

def xor(a,b):
 am=a.cut(b); bm=b.cut(a); av=float(am.volume); bv=float(bm.volume)
 return {'A_B':av,'B_A':bv,'xor_v':av+bv,'xor_pct':100*(av+bv)/float(a.volume)}

def build(mode,tol):
 f,c,kwargs=profile(mode,tol,X0)
 raw=one(extrude(f,2.0,dir=(1,0,0)),'raw')
 ends=[]; raw_edges=[]
 for i,e in enumerate(raw.edges()):
  raw_edges.append(erec(i,e)); b=e.bounding_box()
  if abs(b.min.X-X1)<1e-5 and abs(b.max.X-X1)<1e-5 and e.length>4: ends.append((i,e))
 if len(ends)!=1: raise RuntimeError(f'end curves={len(ends)}')
 rolled=one(fillet([ends[0][1]],ROLL),'roll')
 rolled_edges=[erec(i,e) for i,e in enumerate(rolled.edges())]
 j=[]
 for i,e in enumerate(rolled.edges()):
  b=e.bounding_box()
  if abs(b.min.Z-TOP)<3e-4 and abs(b.max.Z-TOP)<3e-4 and b.max.X>X1-0.03 and b.min.X>X1-ROLL-0.03:j.append((i,e))
 variants=[('none',[])]+[(f'e{i}',[(i,e)]) for i,e in j]
 if len(j)>1:variants.append(('all',j))
 rows=[]
 for name,sel in variants:
  r={'variant':name,'selected':[i for i,_ in sel]}
  try:
   formed=rolled if not sel else one(fillet([e for _,e in sel],JUNCTION),'junction')
   final=one(formed.fuse(pad()).clean(),'final')
   r.update({'formed':metrics(formed),'final':metrics(final),'solid':final})
  except Exception as e:r.update({'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()})
  rows.append(r)
 return {'mode':mode,'tol':tol,'point_count':len(points(mode)),'approx_kwargs':kwargs,
         'profile_area':f.area,'profile_area_delta':f.area-REF_PROFILE_AREA,
         'curve_length':c.length,'curve_length_delta':c.length-REF_PROFILE_LENGTH,
         'raw':metrics(raw),'raw_edges':raw_edges,'terminal_edge':ends[0][0],
         'rolled':metrics(rolled),'rolled_edges':rolled_edges,'junction_candidates':[i for i,_ in j],'variants':rows}

def main():
 allref=import_step(REFERENCE); refs=[s for s in allref.solids() if 1.7<s.volume<1.9 and s.center(CenterOf.MASS).X>0]
 if len(refs)!=1:raise RuntimeError(f'refs={len(refs)}')
 ref=refs[0]
 report={'signature':str(inspect.signature(Edge.make_spline_approx)),'reference':metrics(ref),'cases':[]}
 cases=[(m,t) for m in ('landmarks15','adaptive19','analysis31') for t in (1e-5,5e-5,1e-4,5e-4,1e-3,2e-3,5e-3,1e-2,2e-2)]
 for mode,tol in cases:
  row={'mode':mode,'tol':tol}
  try:
   data=build(mode,tol)
   for v in data['variants']:
    if 'solid' in v:
     s=v.pop('solid'); v['exact_xor']=xor(ref,s)
     stem=f'{mode}_{tol:g}_{v["variant"]}'.replace('.','p')
     export_step(s,OUT/f'{stem}.step'); export_stl(s,OUT/f'{stem}.stl',tolerance=.01,angular_tolerance=.05,ascii_format=True)
   row=data
  except Exception as e:row.update({'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()})
  report['cases'].append(row)
  (OUT/'approx_search_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
