#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, math, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from build123d import Shape, export_step, export_stl, import_step
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'recovered_sources'; OUT=ROOT/'recovered_validation'; GEN=OUT/'generated'; REF=OUT/'reference'
for d in (OUT,GEN,REF): d.mkdir(parents=True,exist_ok=True)
RAW='https://raw.githubusercontent.com/Bastardkb/Dilemma/main/mechanical/cases/3x5_2/tenting_puck_hex/STEP/'
META={
 'opening':('Dilemma Case Tenting Puck Opening.STEP','adafdc2eea773a0b9fcd77e832fe459844d0d8de7617903eb9607822347eb14d','dilemma_case_tenting_puck_opening.py'),
 'integrated':('Dilemma Case Integrated Tenting Puck.STEP','9a86c9e8179889fcdeb632e50cfb1b79c7c395290231f601494ba0046bc3178e','dilemma_case_integrated_tenting_puck.py'),
}

def load_module(path:Path):
 spec=importlib.util.spec_from_file_location(path.stem,path)
 if spec is None or spec.loader is None: raise RuntimeError(f'cannot load {path}')
 mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

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

def props(s:Shape)->dict[str,Any]:
 vp=GProp_GProps(); sp=GProp_GProps(); BRepGProp.VolumeProperties_s(s.wrapped,vp); BRepGProp.SurfaceProperties_s(s.wrapped,sp)
 b=Bnd_Box(); BRepBndLib.Add_s(s.wrapped,b,True); x0,y0,z0,x1,y1,z1=b.Get(); c=vp.CentreOfMass()
 return {'volume_mm3':float(vp.Mass()),'area_mm2':float(sp.Mass()),'com_mm':[c.X(),c.Y(),c.Z()],
 'bbox_min_mm':[x0,y0,z0],'bbox_max_mm':[x1,y1,z1],'bbox_size_mm':[x1-x0,y1-y0,z1-z0],
 'solid_count':len(list(s.solids())),'face_count':len(list(s.faces())),'valid':bool(BRepCheck_Analyzer(s.wrapped,True).IsValid())}

def volume(s:Shape)->float:
 p=GProp_GProps(); BRepGProp.VolumeProperties_s(s.wrapped,p); return max(0.0,float(p.Mass()))

def compare(r:Shape,g:Shape)->dict[str,Any]:
 rp,gp=props(r),props(g)
 print('  reference minus generated',flush=True); rmg=volume(r.cut(g))
 print('  generated minus reference',flush=True); gmr=volume(g.cut(r))
 sym=rmg+gmr; dc=[gp['com_mm'][i]-rp['com_mm'][i] for i in range(3)]; cs=math.sqrt(sum(x*x for x in dc)); diag=math.sqrt(sum(x*x for x in rp['bbox_size_mm']))
 err={'volume_difference_mm3':gp['volume_mm3']-rp['volume_mm3'],'volume_difference_percent':abs(gp['volume_mm3']-rp['volume_mm3'])/rp['volume_mm3']*100,
 'area_difference_mm2':gp['area_mm2']-rp['area_mm2'],'area_difference_percent':abs(gp['area_mm2']-rp['area_mm2'])/rp['area_mm2']*100,
 'com_delta_mm':dc,'com_shift_mm':cs,'com_shift_percent_of_bbox_diagonal':cs/diag*100,
 'bbox_min_delta_mm':[gp['bbox_min_mm'][i]-rp['bbox_min_mm'][i] for i in range(3)],'bbox_max_delta_mm':[gp['bbox_max_mm'][i]-rp['bbox_max_mm'][i] for i in range(3)]}
 boolean={'reference_minus_generated_mm3':rmg,'generated_minus_reference_mm3':gmr,'symmetric_difference_mm3':sym,'symmetric_difference_percent':sym/rp['volume_mm3']*100}
 gates={'symmetric_difference_lt_0_01_percent':boolean['symmetric_difference_percent']<.01,'volume_difference_lt_0_1_percent':err['volume_difference_percent']<.1,
 'area_difference_lt_0_1_percent':err['area_difference_percent']<.1,'com_difference_lt_0_1_percent':err['com_shift_percent_of_bbox_diagonal']<.1,'com_shift_lt_0_1_mm':cs<.1}
 return {'reference':rp,'generated':gp,'directional_boolean':boolean,'errors':err,'thresholds':gates,'pass':rp['valid'] and gp['valid'] and all(gates.values())}

def main()->int:
 report={'method':'OCCT exact B-rep directional Boolean cuts','models':{}}
 for key,(name,sha,script) in META.items():
  print(f'Loading recovered standalone script: {script}',flush=True); mod=load_module(SRC/script)
  print(f'Building fresh parametric model: {key}',flush=True); g=one(mod.build_part())
  export_step(g,GEN/f'{key}.step'); export_stl(g,GEN/f'{key}.stl',tolerance=.005,angular_tolerance=.1)
  r=one(import_step(acquire(name,sha))); print(f'Exact validation: {key}',flush=True); report['models'][key]=compare(r,g)
  print(json.dumps({key:report['models'][key]},indent=2),flush=True)
 report['overall_pass']=all(x['pass'] for x in report['models'].values())
 (OUT/'exact_validation.json').write_text(json.dumps(report,indent=2,sort_keys=True))
 return 0 if report['overall_pass'] else 2
if __name__=='__main__': raise SystemExit(main())
