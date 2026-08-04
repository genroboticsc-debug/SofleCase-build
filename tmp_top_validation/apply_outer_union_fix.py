"""Create one regularized exact outer-body operand from F001 and F002.

Both analytic features remain independently generated and explicitly ordered.
Their completed B-Rep union is evaluated before the parent BuildPart to avoid a
kernel context issue that retained only the overlapping local cap.  This is a
normal parametric Boolean union, not geometry replay or approximation.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "outer_body = main_rolling_body.fuse(top_right_clipped_cap)" in text:
    print(f"F001-F002 outer union already regularized in {PATH}")
    raise SystemExit(0)

old_precompute = '''    main_rolling_body = _main_rolling_body()
    top_right_clipped_cap = _top_right_clipped_cap()
    boss_solids = [
'''
new_precompute = '''    main_rolling_body = _main_rolling_body()
    top_right_clipped_cap = _top_right_clipped_cap()
    outer_body = main_rolling_body.fuse(top_right_clipped_cap)
    if len(outer_body.solids()) != 1 or not outer_body.is_valid:
        raise RuntimeError("F001-F002 exact outer-body union is invalid")
    boss_solids = [
'''

old_add = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        add(main_rolling_body)

        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(top_right_clipped_cap)
'''
new_add = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(outer_body)
'''

for old, new, label in (
    (old_precompute, new_precompute, "F001-F002 precomputation"),
    (old_add, new_add, "F001-F002 parent addition"),
):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} block, found {count}")
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print(f"Regularized exact F001-F002 union in {PATH}")
