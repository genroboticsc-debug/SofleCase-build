from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

ROOT=Path(__file__).resolve().parent
PRODUCTION=ROOT/'production.py'
PARTS={
 'P010':('Dilemma Case Integrated Tenting Puck.STEP','dilemma_case_integrated_tenting_puck.step','9a86c9e8179889fcdeb632e50cfb1b79c7c395290231f601494ba0046bc3178e'),
 'P011':('Dilemma Case Tenting Puck Opening.STEP','dilemma_case_tenting_puck_opening.step','adafdc2eea773a0b9fcd77e832fe459844d0d8de7617903eb9607822347eb14d'),
}
LIMITS={'symdiff_percent':.01,'volume_percent':.1,'area_percent':.1,'com_percent_of_bbox_diagonal':.1,'bbox_percent_of_diagonal':.1}


def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()


def static_srot():
 text=PRODUCTION.read_text(); tree=ast.parse(text)
 imports=[]; calls=[]; bytes_count=0
 def dotted(n):
  if isinstance(n,ast.Name): return n.id
  if isinstance(n,ast.Attribute): return dotted(n.value)+'.'+n.attr
  return ''
 for node in ast.walk(tree):
  if isinstance(node,ast.Import): imports += [a.name for a in node.names]
  elif isinstance(node,ast.ImportFrom): imports.append(node.module or '')
  elif isinstance(node,ast.Call): calls.append(dotted(node.func))
  elif isinstance(node,ast.Constant) and isinstance(node.value,bytes): bytes_count += len(node.value)
 forbidden_imports={'trimesh','manifold3d','cadquery','FreeCAD','pickle','base64','stl'}
 forbidden_calls={'import_step','import_stl','read_step','read_stl','load_mesh','make_bspline_surface','make_bezier_surface','make_spline'}
 forbidden_text=('STEPControl_Reader','StlAPI_Reader','BRepTools.Read','serialized_brep','cached_brep','read_bytes(','frombuffer(','.brep')
 hits={
  'imports':sorted(i for i in imports if i.split('.')[0] in forbidden_imports),
  'calls':sorted(c for c in calls if c.rsplit('.',1)[-1] in forbidden_calls),
  'text':[x for x in forbidden_text if x.lower() in text.lower()],
  'binary_bytes':bytes_count,
 }
 required=('CASE_PERIMETER_FEATURES','HONEYCOMB_CELL_INDICES','LOWER_WALL_SUPPORT_DATA','HexCaseParameters','IntegratedPuckParameters','build_case_base')
 missing=[name for name in required if name not in text]
 passed=not hits['imports'] and not hits['calls'] and not hits['text'] and not bytes_count and not missing
 return {'status':'STRICT_SROT_STATIC_PASS' if passed else 'STRICT_SROT_STATIC_FAIL','production_sha256':digest(PRODUCTION),'hits':hits,'missing_required_symbols':missing,'allowlisted_design_data':['35 named analytic perimeter entities','50 integer honeycomb indices','seven exact support profiles']}


def read_step(path):
 reader=STEPControl_Reader(); status=reader.ReadFile(str(path))
 if int(status)!=1: raise RuntimeError(f'STEP read status {int(status)}: {path}')
 if reader.TransferRoots()<1: raise RuntimeError(f'no transferred roots: {path}')
 return reader.OneShape()


def solids(shape):
 n=0; ex=TopExp_Explorer(shape,TopAbs_SOLID)
 while ex.More(): n+=1; ex.Next()
 return n


def props(shape):
 vp=GProp_GProps(); BRepGProp.VolumeProperties_s(shape,vp)
 ap=GProp_GProps(); BRepGProp.SurfaceProperties_s(shape,ap)
 c=vp.CentreOfMass(); box=Bnd_Box(); BRepBndLib.Add_s(shape,box,True); xmin,ymin,zmin,xmax,ymax,zmax=box.Get()
 return {'volume':vp.Mass(),'area':ap.Mass(),'com':[c.X(),c.Y(),c.Z()],'bbox_min':[xmin,ymin,zmin],'bbox_max':[xmax,ymax,zmax],'bbox_diagonal':math.dist((xmin,ymin,zmin),(xmax,ymax,zmax)),'solid_count':solids(shape),'valid':bool(BRepCheck_Analyzer(shape).IsValid())}


def cut_volume(a,b,label):
 op=BRepAlgoAPI_Cut(a,b); op.Build()
 if not op.IsDone(): raise RuntimeError(f'boolean failed: {label}')
 result=op.Shape()
 if not BRepCheck_Analyzer(result).IsValid(): raise RuntimeError(f'invalid boolean result: {label}')
 gp=GProp_GProps(); BRepGProp.VolumeProperties_s(result,gp)
 return gp.Mass(),solids(result)


def validate(pid,config):
 ref_name,gen_name,expected=config; ref_path=ROOT/'reference'/ref_name; gen_path=ROOT/'generated'/gen_name
 actual=digest(ref_path)
 if actual!=expected: raise RuntimeError(f'{pid} reference hash {actual}')
 ref_shape=read_step(ref_path); gen_shape=read_step(gen_path); ref=props(ref_shape); gen=props(gen_shape)
 if not ref['valid'] or ref['solid_count']!=1: raise RuntimeError(f'{pid} invalid reference topology')
 if not gen['valid'] or gen['solid_count']!=1: raise RuntimeError(f'{pid} invalid generated topology')
 a_minus_b,ab_solids=cut_volume(ref_shape,gen_shape,pid+' A-B'); b_minus_a,ba_solids=cut_volume(gen_shape,ref_shape,pid+' B-A')
 sym=a_minus_b+b_minus_a; sym_pct=sym/ref['volume']*100
 vol_pct=abs(gen['volume']-ref['volume'])/ref['volume']*100
 area_pct=abs(gen['area']-ref['area'])/ref['area']*100
 com_mm=math.dist(ref['com'],gen['com']); com_pct=com_mm/ref['bbox_diagonal']*100
 shifts=[abs(a-b) for a,b in zip(ref['bbox_min']+ref['bbox_max'],gen['bbox_min']+gen['bbox_max'])]; bbox_mm=max(shifts); bbox_pct=bbox_mm/ref['bbox_diagonal']*100
 checks={'one_valid_solid':True,'symdiff':sym_pct<LIMITS['symdiff_percent'],'volume':vol_pct<LIMITS['volume_percent'],'area':area_pct<LIMITS['area_percent'],'com':com_pct<LIMITS['com_percent_of_bbox_diagonal'],'bbox':bbox_pct<LIMITS['bbox_percent_of_diagonal']}
 return {'part_id':pid,'method':'NATIVE_OCCT_STEP_BREP_TWO_DIRECTION_CUT_NO_MESH_NO_FALLBACK','reference_sha256':actual,'reference':ref,'generated':gen,'boolean':{'reference_minus_generated_mm3':a_minus_b,'generated_minus_reference_mm3':b_minus_a,'symmetric_difference_mm3':sym,'symmetric_difference_percent':sym_pct,'directional_solid_counts':[ab_solids,ba_solids]},'differences':{'volume_percent':vol_pct,'area_percent':area_pct,'com_shift_mm':com_mm,'com_percent_of_bbox_diagonal':com_pct,'bbox_shifts_mm':shifts,'bbox_max_shift_mm':bbox_mm,'bbox_percent_of_diagonal':bbox_pct},'checks':checks,'status':'VALIDATION_PASS' if all(checks.values()) else 'VALIDATION_FAIL'}


def main():
 report_dir=ROOT/'reports'; report_dir.mkdir(exist_ok=True)
 srot=static_srot(); (report_dir/'STRICT_SROT_STATIC_AUDIT.json').write_text(json.dumps(srot,indent=2))
 results=[]
 for pid,cfg in PARTS.items():
  try: results.append(validate(pid,cfg))
  except Exception as exc: results.append({'part_id':pid,'status':'VALIDATION_ERROR','error':f'{type(exc).__name__}: {exc}'})
 numeric={'thresholds':LIMITS,'results':results,'overall_status':'VALIDATION_PASS' if all(r['status']=='VALIDATION_PASS' for r in results) else 'VALIDATION_FAIL'}
 (report_dir/'TRUE_BREP_VALIDATION.json').write_text(json.dumps(numeric,indent=2))
 passed=srot['status']=='STRICT_SROT_STATIC_PASS' and numeric['overall_status']=='VALIDATION_PASS'
 final={'reference_commit':'Bastardkb/Dilemma@f5cffb4821fe560b095418b71382ac7d8043c61a','strict_srot':srot['status'],'numeric_validation':numeric['overall_status'],'overall_status':'STRICT_SROT_AND_VALIDATION_PASS' if passed else 'FAIL'}
 (report_dir/'FINAL_CERTIFICATION.json').write_text(json.dumps(final,indent=2))
 print(json.dumps({'srot':srot,'numeric':numeric,'final':final},indent=2))
 return 0 if passed else 1


if __name__=='__main__': raise SystemExit(main())
