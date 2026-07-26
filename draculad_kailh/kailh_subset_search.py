from __future__ import annotations
import json, traceback, itertools
from pathlib import Path
from build123d import CenterOf, Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step
ROOT=Path(__file__).resolve().parent; REF=ROOT/'kailh_reference.step'; OUT=ROOT/'results_subset'; OUT.mkdir(exist_ok=True)
X0=5.010191487800; X1=X0+2.0; R1=.375; R2=.07; TOP=1.75; PAD_TOP=1.80
SPANS=(
((6.26449438808344,1.75),(6.037652643286782,1.7464977207059593),(5.948216212731957,1.1627540082312793),(5.931167511145697,.9908398685910332)),
((5.931167511145697,.9908398685910332),(5.927754127720061,.9564203046194658),(5.922888677847069,.7445394664677538),(5.9056168509451865,.7353586477870302)),
((5.9056168509451865,.7353586477870302),(5.880620638817342,.7220719414904516),(5.853618519895407,.842675012490237),(5.847148297690575,.8600319632961385)),
((5.847148297690575,.8600319632961385),(5.816949601881485,.9410426706516545),(5.774807438674499,1.0176881094435422),(5.727176591347377,1.0896800429967701)),
((5.727176591347377,1.0896800429967701),(5.581540119368333,1.3098031733210076),(5.34929696093493,1.5421574803805749),(5.070910946871318,1.561888982007823)),
((5.070910946871318,1.561888982007823),(4.750995222704022,1.5845640350388521),(4.5310337517931325,1.291336161578472),(4.409299950016339,1.0327790431952582)),
((4.409299950016339,1.0327790431952582),(4.390241682529478,.9923001404512655),(4.2790421668386305,.6963848252000207),(4.268512060541968,.6942119954420493)),
((4.268512060541968,.6942119954420493),(4.2637523122493635,.6932298474523463),(4.259899087895539,.6960508690099316),(4.256802438167436,.6992378869858319)),
((4.256802438167436,.6992378869858319),(4.235761897724996,.7208924448146236),(4.239333497876836,.9743776290012744),(4.234772130300953,1.0251152351594182)),
((4.234772130300953,1.0251152351594182),(4.216801197009745,1.2250118934432974),(4.175010164179821,1.7476386118392202),(3.90576714704497,1.75)),)
def wire(es):
 w=Wire.combine(es,tol=1e-7)
 if len(w)!=1: raise RuntimeError(f'wire={len(w)}')
 return w[0]
def one(s,n):
 ss=s.solids()
 if len(ss)!=1 or not ss[0].is_valid: raise RuntimeError(f'{n}: solids={len(ss)} valid={ss[0].is_valid if ss else None}')
 return ss[0]
def met(s):
 b=s.bounding_box(); c=s.center(CenterOf.MASS)
 return {'v':float(s.volume),'a':float(s.area),'bb':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],'com':[c.X,c.Y,c.Z],'f':len(s.faces()),'e':len(s.edges())}
def er(i,e):
 b=e.bounding_box()
 try:g=str(e.geom_type)
 except:g='?'
 return {'i':i,'g':g,'L':e.length,'bb':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],'s':list(e.position_at(0)),'m':list(e.position_at(.5)),'t':list(e.position_at(1))}
def prof():
 def p(yz):return (X0,yz[0],yz[1])
 es=[Edge.make_bezier(*(p(q) for q in sp)) for sp in SPANS]
 es.append(Edge.make_line(p(SPANS[-1][-1]),p(SPANS[0][0])))
 return Face(wire(es))
def pad():
 ps=[(4.54488778941404,3.76578476453536,TOP),(7.210189558447279,3.7479184533604792,TOP),(7.21019340060459,6.41087029507891,TOP),(4.54488778941404,6.41087029507891,TOP)]
 return one(extrude(Face(wire([Edge.make_line(ps[i],ps[(i+1)%4]) for i in range(4)])),PAD_TOP-TOP,dir=(0,0,1)),'pad')
def xor(a,b):
 am=a.cut(b);bm=b.cut(a);av=float(am.volume);bv=float(bm.volume);return {'ab':av,'ba':bv,'v':av+bv,'pct':100*(av+bv)/float(a.volume)}
def terminal(raw):
 out=[]
 for i,e in enumerate(raw.edges()):
  b=e.bounding_box()
  if abs(b.min.X-X1)<1e-5 and abs(b.max.X-X1)<1e-5 and abs(e.length-2.358727341038)>1e-3:out.append((i,e))
 out.sort(key=lambda ie:ie[1].center().Y,reverse=True)
 return out
def junction_edges(joined):
 out=[]
 for i,e in enumerate(joined.edges()):
  b=e.bounding_box()
  if b.max.X>6.60 and b.min.X>6.55 and b.max.Z<=TOP+5e-4 and b.max.Z>=TOP-5e-4 and e.length<2.2:
   out.append((i,e))
 return out
def main():
 ar=import_step(REF);refs=[s for s in ar.solids() if 1.7<s.volume<1.9 and s.center(CenterOf.MASS).X>0]
 if len(refs)!=1:raise RuntimeError(f'refs={len(refs)}')
 ref=refs[0]; raw=one(extrude(prof(),2,dir=(1,0,0)),'raw'); ts=terminal(raw); pd=pad()
 rep={'ref':met(ref),'raw':met(raw),'terminal':[er(i,e) for i,e in ts],'roll_attempts':[],'successes':[]}
 for start in range(len(ts)):
  for stop in range(start+1,len(ts)+1):
   row={'start':start,'stop':stop,'selected_indices':[i for i,_ in ts[start:stop]]}
   try:
    roll=one(fillet([e for _,e in ts[start:stop]],R1),f'roll {start}:{stop}')
    row['roll']=met(roll); joined=one(roll.fuse(pd).clean(),'joined'); row['joined']=met(joined)
    js=junction_edges(joined);row['junction_candidates']=[er(i,e) for i,e in js]
    variants=[('none',[])]+[(f'e{i}',[(i,e)]) for i,e in js]
    if len(js)<=8:
     variants += [(f'p{a}_{b}',[js[a],js[b]]) for a in range(len(js)) for b in range(a+1,len(js))]
     variants += [(f't{a}_{b}_{c}',[js[a],js[b],js[c]]) for a in range(len(js)) for b in range(a+1,len(js)) for c in range(b+1,len(js))]
    if len(js)>1:variants.append(('all',js))
    best=None
    for vn,sel in variants:
     vr={'name':vn,'sel':[i for i,_ in sel]}
     try:
      final=joined if not sel else one(fillet([e for _,e in sel],R2),'junction')
      xx=xor(ref,final);vr['final']=met(final);vr['xor']=xx
      if best is None or xx['pct']<best['xor']['pct']:
       best={**vr,'solid':final}
     except Exception as e:vr['error']=f'{type(e).__name__}: {e}'
     row.setdefault('variants',[]).append(vr)
    if best:
     solid=best.pop('solid');row['best']=best
     rep['successes'].append({'start':start,'stop':stop,'best':best})
     stem=f's{start}_{stop}_{best["name"]}';export_step(solid,OUT/f'{stem}.step');export_stl(solid,OUT/f'{stem}.stl',tolerance=.01,angular_tolerance=.05,ascii_format=True)
   except Exception as e:row['error']=f'{type(e).__name__}: {e}'
   rep['roll_attempts'].append(row);(OUT/'subset_report.json').write_text(json.dumps(rep,indent=2),encoding='utf-8')
 rep['successes'].sort(key=lambda r:r['best']['xor']['pct'])
 (OUT/'subset_report.json').write_text(json.dumps(rep,indent=2),encoding='utf-8')
 print(json.dumps({'success_count':len(rep['successes']),'top':rep['successes'][:20]},indent=2))
if __name__=='__main__':main()
