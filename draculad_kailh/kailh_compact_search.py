from __future__ import annotations
import json, traceback
from pathlib import Path
from build123d import CenterOf, Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step
ROOT=Path(__file__).resolve().parent; REF=ROOT/'kailh_reference.step'; OUT=ROOT/'results_compact'; OUT.mkdir(exist_ok=True)
X0=5.010191487800; X1=X0+2.0; R1=.375; R2=.07; TOP=1.75; PAD_TOP=1.80
REF_AREA=.9075354150773971; REF_LEN=4.851046962108225
P={
'EH':(6.26449438808344,1.75),
'RO':(5.931167511145697,.9908398685910332),
'RV':(5.9056168509451865,.7353586477870302),
'RI':(5.727176591347377,1.0896800429967701),
'C':(5.070910946871318,1.561888982007823),
'LI':(4.409299950016339,1.0327790431952582),
'LV':(4.268512060541968,.6942119954420493),
'LO':(4.234772130300953,1.0251152351594182),
'EL':(3.90576714704497,1.75),
}
SETS={
'design5':['EH','RV','C','LV','EL'],
'design7':['EH','RV','RI','C','LI','LV','EL'],
'design9':['EH','RO','RV','RI','C','LI','LV','LO','EL'],
'design8_no_ro':['EH','RV','RI','C','LI','LV','LO','EL'],
'design8_no_lo':['EH','RO','RV','RI','C','LI','LV','EL'],
}
def wire(es):
 w=Wire.combine(es,tol=1e-7)
 if len(w)!=1:raise RuntimeError(f'wire count {len(w)}')
 return w[0]
def one(s,n):
 ss=s.solids()
 if len(ss)!=1 or not ss[0].is_valid:raise RuntimeError(f'{n}: solids={len(ss)}')
 return ss[0]
def met(s):
 b=s.bounding_box();c=s.center(CenterOf.MASS)
 return {'v':float(s.volume),'a':float(s.area),'bb':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],'com':[c.X,c.Y,c.Z],'f':len(s.faces()),'e':len(s.edges())}
def er(i,e):
 b=e.bounding_box()
 try:g=str(e.geom_type)
 except:g='?'
 return {'i':i,'g':g,'L':e.length,'bb':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z]}
def prof(name,x):
 yz=[P[k] for k in SETS[name]]
 c=Edge.make_spline([(x,y,z) for y,z in yz],tol=1e-9)
 t=Edge.make_line((x,yz[-1][0],yz[-1][1]),(x,yz[0][0],yz[0][1]))
 f=Face(wire([c,t]));return f,c
def pad():
 ps=[(4.54488778941404,3.76578476453536,TOP),(7.210189558447279,3.7479184533604792,TOP),(7.21019340060459,6.41087029507891,TOP),(4.54488778941404,6.41087029507891,TOP)]
 return one(extrude(Face(wire([Edge.make_line(ps[i],ps[(i+1)%4]) for i in range(4)])),PAD_TOP-TOP,dir=(0,0,1)),'pad')
def xor(a,b):
 am=a.cut(b);bm=b.cut(a);av=float(am.volume);bv=float(bm.volume);return {'ab':av,'ba':bv,'v':av+bv,'pct':100*(av+bv)/float(a.volume)}
def build(name):
 f,c=prof(name,X0);raw=one(extrude(f,2,dir=(1,0,0)),'raw')
 rr=[er(i,e) for i,e in enumerate(raw.edges())]; ends=[]
 for i,e in enumerate(raw.edges()):
  b=e.bounding_box()
  if abs(b.min.X-X1)<1e-5 and abs(b.max.X-X1)<1e-5 and e.length>3.5:ends.append((i,e))
 if len(ends)!=1:raise RuntimeError(f'end={len(ends)}')
 roll=one(fillet([ends[0][1]],R1),'roll'); re=[er(i,e) for i,e in enumerate(roll.edges())]
 jc=[]
 for i,e in enumerate(roll.edges()):
  b=e.bounding_box()
  if abs(b.min.Z-TOP)<5e-4 and abs(b.max.Z-TOP)<5e-4 and b.max.X>X1-.04 and b.min.X>X1-R1-.04:jc.append((i,e))
 variants=[('none',[])]+[(f'e{i}',[(i,e)]) for i,e in jc]
 if len(jc)>1:variants.append(('all',jc))
 rows=[]
 for vn,sel in variants:
  r={'name':vn,'sel':[i for i,_ in sel]}
  try:
   formed=roll if not sel else one(fillet([e for _,e in sel],R2),'junction')
   final=one(formed.fuse(pad()).clean(),'final');r.update({'formed':met(formed),'final':met(final),'solid':final})
  except Exception as e:r.update({'error':f'{type(e).__name__}: {e}','tb':traceback.format_exc()})
  rows.append(r)
 return {'name':name,'datums':SETS[name],'n':len(SETS[name]),'pa':f.area,'pa_d':f.area-REF_AREA,'cl':c.length,'cl_d':c.length-REF_LEN,'raw':met(raw),'raw_edges':rr,'end':ends[0][0],'roll':met(roll),'roll_edges':re,'jc':[i for i,_ in jc],'variants':rows}
def main():
 ar=import_step(REF);rs=[s for s in ar.solids() if 1.7<s.volume<1.9 and s.center(CenterOf.MASS).X>0]
 if len(rs)!=1:raise RuntimeError(len(rs))
 ref=rs[0]; rep={'ref':met(ref),'cases':[]}
 for name in SETS:
  d={'name':name}
  try:
   d=build(name)
   for v in d['variants']:
    if 'solid' in v:
     s=v.pop('solid');v['xor']=xor(ref,s);stem=f'{name}_{v["name"]}';export_step(s,OUT/f'{stem}.step');export_stl(s,OUT/f'{stem}.stl',tolerance=.01,angular_tolerance=.05,ascii_format=True)
  except Exception as e:d.update({'error':f'{type(e).__name__}: {e}','tb':traceback.format_exc()})
  rep['cases'].append(d);(OUT/'compact_report.json').write_text(json.dumps(rep,indent=2),encoding='utf-8')
 print(json.dumps(rep,indent=2))
if __name__=='__main__':main()
