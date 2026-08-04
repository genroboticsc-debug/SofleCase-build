"""Isolate and regularize the exact F001/F002 outer-body operands.

The helpers contain internal construction tools, so they are evaluated outside
the parent BuildPart.  The independently generated rolling body and clipped
cap are then fused into one valid exact B-Rep before the parent feature tree is
opened.  This changes no dimensions or surfaces and introduces no replay.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")
changed = False

if "main_rolling_body = _main_rolling_body()" not in text:
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
    changed = True

if "outer_body = main_rolling_body.fuse(top_right_clipped_cap)" not in text:
    old_union_precompute = '''    main_rolling_body = _main_rolling_body()
    top_right_clipped_cap = _top_right_clipped_cap()
    boss_solids = [
'''
    new_union_precompute = '''    main_rolling_body = _main_rolling_body()
    top_right_clipped_cap = _top_right_clipped_cap()
    outer_body = main_rolling_body.fuse(top_right_clipped_cap)
    if len(outer_body.solids()) != 1 or not outer_body.is_valid:
        raise RuntimeError("F001-F002 exact outer-body union is invalid")
    boss_solids = [
'''
    old_union_add = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        add(main_rolling_body)

        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(top_right_clipped_cap)
'''
    new_union_add = '''        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(outer_body)
'''
    for old, new, label in (
        (old_union_precompute, new_union_precompute, "F001-F002 union"),
        (old_union_add, new_union_add, "F001-F002 parent addition"),
    ):
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"Expected one {label} block, found {count}")
        text = text.replace(old, new)
    changed = True

if changed:
    PATH.write_text(text, encoding="utf-8")
    print(f"Isolated and regularized exact outer operands in {PATH}")
else:
    print(f"Exact outer operands already isolated and regularized in {PATH}")
