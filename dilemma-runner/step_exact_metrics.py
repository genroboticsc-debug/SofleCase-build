from __future__ import annotations
import csv, importlib.util, json, tempfile
from pathlib import Path
from build123d import import_step
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

root = Path(__file__).resolve().parent / 'project'
validator_path = root / 'validation' / 'Final_validation_check.py'
spec = importlib.util.spec_from_file_location('validator', validator_path)
v = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(v)
original_metrics = v._metrics

def fixed_metrics(path: Path, mesh=None):
    if path.suffix.lower() not in {'.step','.stp'}:
        return original_metrics(path, mesh)
    shape = import_step(path)
    if shape is None or not shape.is_valid:
        raise v.ValidationFailure(f'{path}: invalid STEP B-Rep')
    bb = shape.bounding_box()
    vp = GProp_GProps(); BRepGProp.VolumeProperties_s(shape.wrapped, vp)
    sp = GProp_GProps(); BRepGProp.SurfaceProperties_s(shape.wrapped, sp)
    com = vp.CentreOfMass()
    if mesh is None:
        with tempfile.TemporaryDirectory(prefix='step_exact_') as td:
            mesh = v._as_mesh(path, Path(td))
    components = mesh.split(only_watertight=False)
    solids = len(shape.solids())
    volume = float(abs(vp.Mass()))
    if solids == 0 and volume > 1e-12:
        solids = 1
    return v.GeometryMetrics(
        volume_mm3=volume,
        area_mm2=float(abs(sp.Mass())),
        bbox_min=[float(bb.min.X),float(bb.min.Y),float(bb.min.Z)],
        bbox_max=[float(bb.max.X),float(bb.max.Y),float(bb.max.Z)],
        bbox_extents=[float(bb.size.X),float(bb.size.Y),float(bb.size.Z)],
        com=[float(com.X()),float(com.Y()),float(com.Z())],
        body_count=solids,
        watertight=bool(mesh.is_watertight),
        connected_components=len(components),
        vertices=int(len(mesh.vertices)), faces=int(len(mesh.faces)),
    )

v._metrics = fixed_metrics
expected = json.loads((root/'inventory'/'expected_generated_inventory.json').read_text())
rows=[]
with tempfile.TemporaryDirectory(prefix='p010_p011_') as td:
    for item in expected:
        if item['canonical_part_id'] not in {'P010','P011'}:
            continue
        gp=root/'XYZ'/'generated'/item['validation_filename']
        rp=root/'XYZ'/'reference'/item['validation_filename']
        row=v.validate_pair(item,gp,rp,Path(td))
        rows.append(row)
        print('EXACT STEP RESULT', item['canonical_part_id'], row.get('Overall_PASS'),
              row.get('Symmetric_Difference_%'), row.get('Failure_Reason',''))
out=root/'validation'/'p010_p011_exact_metrics.json'
out.write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
with (root/'validation'/'p010_p011_exact_metrics.csv').open('w',newline='') as f:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
