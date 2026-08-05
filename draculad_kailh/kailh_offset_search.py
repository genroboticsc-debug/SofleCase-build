from __future__ import annotations
import json, traceback
from pathlib import Path
from build123d import CenterOf, Edge, Face, Wire, Kind, Side, export_step, extrude, import_step, offset
ROOT=Path(__file__).resolve().parent; REF=ROOT/'kailh_reference.step'; OUT=ROOT/'results_offset';OUT.mkdir(exist_ok=True)
X0=5.010191487800;R=.375;TOP=1.75
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
DATUMS=[(6.26449438808344,1.75),(5.9056168509451865,.7353586477870302),(5.727176591347377,1.0896800429967701),(5.070910946871318,1.561888982007823),(4.409299950016339,1.0327790431952582),(4.268512060541968,.6942119954420493),(3.90576714704497,1.75)]
def wire(es):
 w=Wire.combine(es,tol=1e-7)
 if len(w)!=1:raise RuntimeError(f'wire={len(w)}')
 return w[0]
def bezier_face():
 def p(q):return (X0,q[0],q[1])
 es=[Edge.make_bezier(*(p(q) for q in s)) for s in SPANS];es.append(Edge.make_line(p(SPANS[-1][-1]),p(SPANS[0][0])))
 return Face(wire(es))
def spline_face():
 c=Edge.make_spline([(X0,y,z) for y,z in DATUMS],tol=1e-9);return Face(wire([c,Edge.make_line((X0,DATUMS[-1][0],TOP),(X0,DATUMS[0][0],TOP))]))
def rec(o):
 b=o.bounding_box();return {'type':type(o).__name__,'area':float(o.area),'length':float(o.length),'bb':[b.min.X,b.min.Y,b.min.Z,b.max.X,b.max.Y,b.max.Z],'faces':len(o.faces()),'wires':len(o.wires()),'edges':len(o.edges())}
def main():
 rep={'cases':[]}
 for name,f in [('bezier10',bezier_face()),('spline7',spline_face())]:
  for amount in [-R,R]:
   for kind in [Kind.ARC,Kind.INTERSECTION]:
    row={'name':name,'amount':amount,'kind':str(kind),'source':rec(f)}
    try:
     q=offset(f,amount=amount,kind=kind)
     row['result']=rec(q)
     if len(q.faces()):
      export_step(extrude(q,0.01,dir=(1,0,0)),OUT/f'{name}_{amount}_{kind.name}.step')
    except Exception as e:row.update({'error':f'{type(e).__name__}: {e}','tb':traceback.format_exc()})
    rep['cases'].append(row)
 (OUT/'offset_report.json').write_text(json.dumps(rep,indent=2),encoding='utf-8');print(json.dumps(rep,indent=2))
if __name__=='__main__':main()
