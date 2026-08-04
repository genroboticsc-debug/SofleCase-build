"""Precompute F001 and F002 outside the parent BuildPart context.

The exact clipped-cap helper contains an internal clipping prism.  Calling the
helper while a parent builder is active can register that temporary tool with
the parent even though the helper correctly returns only the common.  This
transformation creates the finished analytic operands first and then adds only
those returned solids to the genuine feature tree.  No geometry changes.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "main_rolling_body = _main_rolling_body()" in text:
    print(f"Outer operands already isolated in {PATH}")
    raise SystemExit(0)

old_precompute = '''    # Build independent F003-F005 operands before opening the parent context.
    # This is still a genuine parametric feature tree: each operand is an
    # identified analytic cylinder clipped by the identified analytic envelope.
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]
    engraving_sketch = _engraving_profile_sketch()

    with BuildPart() as top:
'''
new_precompute = '''    # Build independent analytic operands before opening the parent context.
    # Only completed returned shapes are introduced into the feature tree;
    # internal construction and clipping tools cannot leak into the parent.
    main_rolling_body = _main_rolling_body()
    top_right_clipped_cap = _top_right_clipped_cap()
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]
    engraving_sketch = _engraving_profile_sketch()

    with BuildPart() as top:
'''

old_features = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        add(_main_rolling_body())

        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(_top_right_clipped_cap())
'''
new_features = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        add(main_rolling_body)

        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(top_right_clipped_cap)
'''

for old, new, label in (
    (old_precompute, new_precompute, "operand precomputation"),
    (old_features, new_features, "F001/F002 addition"),
):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} block, found {count}")
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print(f"Isolated exact outer operands in {PATH}")
