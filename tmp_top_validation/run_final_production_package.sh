#!/usr/bin/env bash
set -euxo pipefail

ROOT=tmp_top_validation
NAME=Dilemma_top_STRICT_SROT_PASS_2026-08-05
PKG="$ROOT/$NAME"

python "$ROOT/apply_explicit_boolean_tree_fix.py"
python "$ROOT/apply_f005_boolean_tolerance_fix.py"
python "$ROOT/apply_f012_all_faces_fix.py"
python "$ROOT/apply_f012_font_size_fix.py"
python "$ROOT/apply_f012_lowercase_v_fix.py"

python -m py_compile \
  "$ROOT/top_parametric.py" \
  "$ROOT/top_production_export.py" \
  "$ROOT/strict_srot_check.py" \
  "$ROOT/validate_fast_manifold.py" \
  "$ROOT/validate_feature_tree_manifold.py" \
  "$ROOT/validate_direct_final_solid.py" \
  "$ROOT/validate_final_production_package.py"

python "$ROOT/strict_srot_check.py"

python - <<'PY'
import ast
import json
from pathlib import Path

path = Path('tmp_top_validation/top_production_export.py')
source = path.read_text(encoding='utf-8')
tree = ast.parse(source)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        imports.add(node.module or '')
names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
forbidden_serialization_tokens = (
    'pickle.dump',
    'pickle.load',
    'BRepTools.Write',
    'BRepTools.Read',
    'export_brep',
    'import_brep',
    'breptools_Write',
    'breptools_Read',
)
checks = {
    'no_validation_imports': not bool(imports & {
        'validate_direct_final_solid',
        'validate_fast_manifold',
        'validate_feature_tree_manifold',
    }),
    'no_reference_identifiers': not bool(names & {
        'REFERENCE', 'REFERENCE_STL', 'reference_mesh'
    }),
    'no_geometry_import_calls': (
        'import_step(' not in source and 'import_stl(' not in source
    ),
    'no_serialized_brep': not any(
        token in source for token in forbidden_serialization_tokens
    ),
    'analytic_feature_tree_dependency': 'import top_parametric as tp' in source,
    'formula_based_adaptive_bores': (
        'analytic_strip' in source and 'ADAPTIVE_BORE_NAMES' in source
    ),
}
report = {'checks': checks, 'pass': all(checks.values())}
Path('tmp_top_validation/strict_production_export_report.json').write_text(
    json.dumps(report, indent=2), encoding='utf-8'
)
if not report['pass']:
    raise SystemExit(report)
print(json.dumps(report, indent=2))
PY

git diff --check
rm -rf "$ROOT/generated/final_top" "$ROOT/generated/final_authoritative_validation"
python "$ROOT/top_production_export.py"
python "$ROOT/validate_final_production_package.py" | tee "$ROOT/final_validation.log"

python - <<'PY'
import json
from pathlib import Path

path = Path('tmp_top_validation/generated/final_top/final_validation_report.json')
report = json.loads(path.read_text(encoding='utf-8'))
validation = report['authoritative_validation']
assert report['overall_pass'] is True, report
assert validation['strict_pass'] is True, validation
assert validation['symmetric_difference_percent'] < 0.01, validation
print(json.dumps({
    'overall_pass': report['overall_pass'],
    'symmetric_difference_mm3': validation['symmetric_difference_mm3'],
    'symmetric_difference_percent': validation['symmetric_difference_percent'],
    'volume_difference_percent': validation['volume_difference_percent'],
    'area_difference_percent': validation['area_difference_percent'],
    'com_shift_percent_bbox_diagonal': (
        validation['com_shift_percent_bbox_diagonal']
    ),
}, indent=2))
PY

rm -rf "$PKG" "$ROOT/$NAME.zip" "$ROOT/$NAME.zip.sha256"
mkdir -p "$PKG/source" "$PKG/output" "$PKG/validation" "$PKG/provenance"
cp "$ROOT/top_parametric.py" "$PKG/source/"
cp "$ROOT/top_production_export.py" "$PKG/source/"
cp "$ROOT/strict_srot_check.py" "$PKG/source/"
cp "$ROOT/requirements.txt" "$PKG/source/"
cp "$ROOT/generated/final_top/top_parametric.step" "$PKG/output/"
cp "$ROOT/generated/final_top/top_parametric.stl" "$PKG/output/"
cp "$ROOT/generated/final_top/top_native_raw.stl" "$PKG/output/"
cp "$ROOT/generated/final_top/top_export_audit.json" "$PKG/validation/"
cp "$ROOT/generated/final_top/final_validation_report.json" "$PKG/validation/"
cp "$ROOT/generated/strict_srot_report.json" "$PKG/validation/"
cp "$ROOT/strict_production_export_report.json" "$PKG/validation/"
cp "$ROOT/final_validation.log" "$PKG/validation/"
cp -r "$ROOT/generated/final_authoritative_validation" \
  "$PKG/validation/authoritative_evidence"
printf '%s\n' 'cc3523043a98f97d5a7938e48cdbb947990f4a09' \
  > "$PKG/provenance/immutable_source_commit.txt"
git rev-parse origin/tmp/top-engraving-frozen-validation-20260805 \
  > "$PKG/provenance/frozen_workflow_commit.txt"

python - <<'PY'
import json
import platform
from pathlib import Path
import build123d
import manifold3d
import numpy
import scipy
import shapely
import trimesh

pkg = Path('tmp_top_validation/Dilemma_top_STRICT_SROT_PASS_2026-08-05')
environment = {
    'python': platform.python_version(),
    'build123d': getattr(build123d, '__version__', '0.11.1'),
    'ocp': 'cadquery-ocp-novtk 7.9.3.1.1',
    'manifold3d': getattr(manifold3d, '__version__', '3.5.2'),
    'numpy': numpy.__version__,
    'scipy': scipy.__version__,
    'shapely': shapely.__version__,
    'trimesh': trimesh.__version__,
    'font': 'Arial Regular',
    'font_sha256': (
        '35c0f3559d8db569e36c31095b8a60d441643d95f59139de40e23fada819b833'
    ),
}
(pkg / 'provenance/environment.json').write_text(
    json.dumps(environment, indent=2), encoding='utf-8'
)
report = json.loads((
    Path('tmp_top_validation/generated/final_top')
    / 'final_validation_report.json'
).read_text(encoding='utf-8'))
validation = report['authoritative_validation']
readme = f'''# Dilemma top — Strict SROT PASS

- Strict SROT: PASS
- Bidirectional symmetric difference: {validation['symmetric_difference_mm3']:.12f} mm³ ({validation['symmetric_difference_percent']:.12f}%)
- Volume difference: {validation['volume_difference_percent']:.12f}%
- Surface-area difference: {validation['area_difference_percent']:.12f}%
- COM shift / bbox diagonal: {validation['com_shift_percent_bbox_diagonal']:.12f}%
- Production STL canonical congruence: {report['final_checks']['production_stl_canonical_triangle_congruent']}

The STEP is generated by the analytic Build123d F001–F012 feature tree. The production exporter reads no reference geometry; the reference STL is used only by the validation workflow.
'''
(pkg / 'README.md').write_text(readme, encoding='utf-8')
PY

(
  cd "$PKG"
  find . -type f ! -name checksums.sha256 -print0 \
    | sort -z | xargs -0 sha256sum > checksums.sha256
  sha256sum -c checksums.sha256
)
(
  cd "$ROOT"
  zip -q -9 -r "$NAME.zip" "$NAME"
)
sha256sum "$ROOT/$NAME.zip" > "$ROOT/$NAME.zip.sha256"
