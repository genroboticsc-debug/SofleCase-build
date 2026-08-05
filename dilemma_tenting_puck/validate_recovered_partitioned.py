#!/usr/bin/env python3
"""Exact OCCT partitioned Boolean validation for the recovered candidates.

Both reference and generated B-reps are intersected with the same disjoint
axis-aligned cells. Directional A-B and B-A volumes are summed over every cell;
no cell is omitted and no mesh/fallback metric is accepted.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from build123d import Compound, Location, Shape, Solid, export_step, export_stl, import_step
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'recovered_sources'; OUT=ROOT/'partitioned_validation'; GEN=OUT/'generated'; REF=OUT/'reference'
for d in (OUT,GEN,REF): d.mkdir(parents=True,exist_ok=True)
RAW='https://raw.githubusercontent.com/Bastardkb/Dilemma/main/mechanical/cases/3x5_2/tenting_puck_hex/STEP/'
META={
 'opening':('Dilemma Case Tenting Puck Opening.STEP','adafdc2eea773a0b9fcd77e832fe459844d0d8de7617903eb9607822347eb14d','dilemma_case_tenting_puck_opening.py'),
 'integrated':('Dilemma Case Integrated Tenting Puck.STEP','9a86c9e8179889fcdeb632e50cfb1b79c7c395290231f601494ba0046bc3178e','dilemma_case_integrated_tenting_puck.py'),
}
X=[-106.0,-70.0,-35.0,0.0,35.0]
Y=[-78.0,-42.0,-10.0,25.0]
Z={
 'opening':[-8.61,-7.85,-7.35,-5.60,-4.60,-4.40,-4.20,-1.60,-1.15,-0.39],
 'integrated':[-9.14,-8.60,-7.85,-7.35,-6.60,-5.60,-4.60,-4.40,-4.20,-4.10,-1.60,-1.15,-0.39],
}

def load_module(path:Path):
 spec=importlib.util.spec_from_file_location(path.stem,path)
 if spec is None or spec.loader is None: raise RuntimeError(f'cannot load {path}')
 mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def one(shape:Shape)->Shape:
 solids=list(shape.solids())
 if len(solids)!=1: raise RuntimeError(f'expected one solid, found {len(solids)}')
 return solids[0]

def acquire(name:str,sha:str)->Path:
 p=REF/name
 if not p.exists(): urllib.request.urlretrieve(RAW+urllib.parse.quote(name),p)
 got=hashlib.sha256(p.read_bytes()).hexdigest()
 if got!=sha: raise RuntimeError(f'reference hash mismatch {name}: {got}')
 return p

def mass(s:Shape, kind:str='volume')->float:
 p=GProp_GProps()
 if kind=='volume': BRepGProp.VolumeProperties_s(s.wrapped,p)
 else: BRepGProp.SurfaceProperties_s(s.wrapped,p)
 return max(0.0,float(p.Mass()))

def props(s:Shape)->dict[str,Any]:
 vp=GProp_GProps(); sp=GProp_GProps(); BRepGProp.VolumeProperties_s(s.wrapped,vp); BRepGProp.SurfaceProperties_s(s.wrapped,sp)
 b=Bnd_Box(); BRepBndLib.Add_s(s.wrapped,b,True); x0,y0,z0,x1,y1,z1=b.Get(); c=vp.CentreOfMass()
 return {'volume_mm3':float(vp.Mass()),'area_mm2':float(sp.Mass()),'com_mm':[c.X(),c.Y(),c.Z()],
 'bbox_min_mm':[x0,y0,z0],'bbox_max_mm':[x1,y1,z1],'bbox_size_mm':[x1-x0,y1-y0,z1-z0],
 'solid_count':len(list(s.solids())),'face_count':len(list(s.faces())),'valid':bool(BRepCheck_Analyzer(s.wrapped,True).IsValid())}

def box(bounds):
 x0,x1,y0,y1,z0,z1=bounds
 return Solid.make_box(x1-x0,y1-y0,z1-z0).moved(Location((x0,y0,z0)))

def clipped(shape:Shape, cell:Solid):
 result=shape.intersect(cell)
 solids=list(result.solids())
 if not solids: return None
 return result

def residual(a,b)->float:
 if a is None: return 0.0
 if b is None: return mass(a)
 return mass(a.cut(b))

def validate_partitioned(key:str, ref:Shape, gen:Shape)->dict[str,Any]:
 rp,gp=props(ref),props(gen); cells=[]; rv=gv=rmg=gmr=0.0
 zs=Z[key]
 total=(len(X)-1)*(len(Y)-1)*(len(zs)-1); n=0
 for iz in range(len(zs)-1):
  for iy in range(len(Y)-1):
   for ix in range(len(X)-1):
    n+=1; bounds=[X[ix],X[ix+1],Y[iy],Y[iy+1],zs[iz],zs[iz+1]]
    c=box(bounds); a=clipped(ref,c); b=clipped(gen,c)
    av=0.0 if a is None else mass(a); bv=0.0 if b is None else mass(b)
    ab=residual(a,b); ba=residual(b,a)
    rv+=av; gv+=bv; rmg+=ab; gmr+=ba
    if ab+ba>1e-8:
     cells.append({'index':[ix,iy,iz],'bounds_mm':bounds,'reference_volume_mm3':av,'generated_volume_mm3':bv,
                   'reference_minus_generated_mm3':ab,'generated_minus_reference_mm3':ba,'xor_mm3':ab+ba})
    if n%10==0 or n==total: print(f'  {key}: exact cells {n}/{total}',flush=True)
 coverage={'reference_partition_sum_mm3':rv,'generated_partition_sum_mm3':gv,
           'reference_coverage_error_mm3':rv-rp['volume_mm3'],'generated_coverage_error_mm3':gv-gp['volume_mm3']}
 if abs(coverage['reference_coverage_error_mm3'])>1e-4 or abs(coverage['generated_coverage_error_mm3'])>1e-4:
  raise RuntimeError(f'partition coverage failure: {coverage}')
 sym=rmg+gmr; dc=[gp['com_mm'][i]-rp['com_mm'][i] for i in range(3)]; cs=math.sqrt(sum(x*x for x in dc)); diag=math.sqrt(sum(x*x for x in rp['bbox_size_mm']))
 errors={'volume_difference_mm3':gp['volume_mm3']-rp['volume_mm3'],'volume_difference_percent':abs(gp['volume_mm3']-rp['volume_mm3'])/rp['volume_mm3']*100,
 'area_difference_mm2':gp['area_mm2']-rp['area_mm2'],'area_difference_percent':abs(gp['area_mm2']-rp['area_mm2'])/rp['area_mm2']*100,
 'com_delta_mm':dc,'com_shift_mm':cs,'com_shift_percent_of_bbox_diagonal':cs/diag*100}
 boolean={'reference_minus_generated_mm3':rmg,'generated_minus_reference_mm3':gmr,'symmetric_difference_mm3':sym,'symmetric_difference_percent':sym/rp['volume_mm3']*100}
 gates={'symmetric_difference_lt_0_01_percent':boolean['symmetric_difference_percent']<.01,'volume_difference_lt_0_1_percent':errors['volume_difference_percent']<.1,
 'area_difference_lt_0_1_percent':errors['area_difference_percent']<.1,'com_difference_lt_0_1_percent':errors['com_shift_percent_of_bbox_diagonal']<.1,'com_shift_lt_0_1_mm':cs<.1}
 return {'reference':rp,'generated':gp,'coverage':coverage,'directional_boolean':boolean,'errors':errors,'thresholds':gates,
         'nonzero_residual_cells':sorted(cells,key=lambda c:c['xor_mm3'],reverse=True),'pass':rp['valid'] and gp['valid'] and all(gates.values())}

def main()->int:
 report={'method':'exact OCCT B-rep directional Boolean summed over identical disjoint XYZ cells','grid':{'x_mm':X,'y_mm':Y,'z_mm':Z},'models':{}}
 for key,(name,sha,script) in META.items():
  print(f'Fresh-build recovered parametric script: {script}',flush=True); mod=load_module(SRC/script); gen=one(mod.build_part())
  export_step(gen,GEN/f'{key}.step'); export_stl(gen,GEN/f'{key}.stl',tolerance=.005,angular_tolerance=.1)
  ref=one(import_step(acquire(name,sha))); print(f'Partitioned exact validation: {key}',flush=True)
  report['models'][key]=validate_partitioned(key,ref,gen)
  print(json.dumps({key:{k:v for k,v in report['models'][key].items() if k!='nonzero_residual_cells'}},indent=2),flush=True)
 report['overall_pass']=all(v['pass'] for v in report['models'].values())
 (OUT/'partitioned_exact_validation.json').write_text(json.dumps(report,indent=2,sort_keys=True))
 return 0 if report['overall_pass'] else 2
if __name__=='__main__': raise SystemExit(main())
