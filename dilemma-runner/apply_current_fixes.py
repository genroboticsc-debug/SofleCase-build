from pathlib import Path

root = Path(__file__).resolve().parent / 'project'

# P025: retain the currently proved right-wall datum experiment for diagnostics.
p025 = root / 'scripts' / 'dilemma_4x6_4_top.py'
text = p025.read_text(encoding='utf-8')
old = "    ((237.40062, -83.10167), (244.51852, -80.01642), (246.668798, -80.01642)),\n"
new = "    ((237.40062, -83.10167), (244.51852, -80.01642), (246.668798, -80.01642), (244.56601, -80.06390), (244.56601, -80.06788)),\n"
if old not in text:
    raise SystemExit('P025 exact rib-10 anchor not found')
p025.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Applied P025 exact rib-10 return/contact points')

# P029: replace the singular whole-wire loft with the proved exact 76-face
# ruled shell assembled from the same analytic station wires.
p029 = root / 'scripts' / 'dilemma_4x6_4_hotswap_mid.py'
text = p029.read_text(encoding='utf-8')
text = text.replace('    Side,\n    Solid,', '    Side,\n    Shell,\n    Solid,', 1)
old = '''def _drafted_branch_band(
    path: Wire,
    p: P029UpperParameters,
    label: str,
) -> Solid:
    """Build the exact 1:1 upper draft from analytic offset wires."""
    bottom = _branch_band_at_offsets(
        path, p.lower_outer_inset, p.inner_inset
    ).moved(Location((0.0, 0.0, p.draft_break_y)))
    top = _branch_band_at_offsets(
        path, p.top_outer_inset, p.inner_inset
    ).moved(Location((0.0, 0.0, p.top_y)))

    # Each open-branch rail station is one simply connected closed band wire.
    # Lofting those complete station boundaries lets OCCT own the seam and cap
    # orientation as one solid operation.  The previous manually assembled
    # outer/inner shells could carry opposed seam orientations even though all
    # six constituent faces were individually exact.
    result = Solid.make_loft(
        (bottom.outer_wire(), top.outer_wire()),
        ruled=True,
    )
    if not result.is_valid or len(result.solids()) != 1:
        raise RuntimeError(f"P029 {label} exact ruled draft failed")
    return result
'''
new = '''def _drafted_branch_band(
    path: Wire,
    p: P029UpperParameters,
    label: str,
) -> Solid:
    """Build the exact 1:1 upper draft as a sewn ruled shell."""
    bottom_outer = _oriented_open_offset(path, p.lower_outer_inset).moved(
        Location((0.0, 0.0, p.draft_break_y))
    )
    top_outer = _oriented_open_offset(path, p.top_outer_inset).moved(
        Location((0.0, 0.0, p.top_y))
    )
    bottom_inner = _oriented_open_offset(path, p.inner_inset).moved(
        Location((0.0, 0.0, p.draft_break_y))
    )
    top_inner = _oriented_open_offset(path, p.inner_inset).moved(
        Location((0.0, 0.0, p.top_y))
    )

    bottom = _branch_band_face(bottom_outer, bottom_inner)
    top = _branch_band_face(top_outer, top_inner)
    outer_side = Face.make_surface_from_curves(bottom_outer, top_outer)
    inner_side = Face.make_surface_from_curves(bottom_inner, top_inner)

    def endpoint_cap(a: Vector, b: Vector, c: Vector, d: Vector) -> Face:
        cap = Face(Wire.make_polygon((a, b, c, d), close=True))
        if not cap.is_valid:
            raise RuntimeError(f"P029 {label} exact endpoint cap is invalid")
        return cap

    start_cap = endpoint_cap(
        bottom_outer.start_point(), bottom_inner.start_point(),
        top_inner.start_point(), top_outer.start_point(),
    )
    end_cap = endpoint_cap(
        bottom_outer.end_point(), top_outer.end_point(),
        top_inner.end_point(), bottom_inner.end_point(),
    )
    faces = [bottom, top]
    faces.extend(outer_side.faces())
    faces.extend(inner_side.faces())
    faces.extend((start_cap, end_cap))
    sewn = Face.sew_faces(faces)
    if len(sewn) != 1:
        raise RuntimeError(
            f"P029 {label} exact ruled faces did not sew into one shell "
            f"(shell_group_count={len(sewn)})"
        )
    result = Solid(Shell(sewn[0])).fix()
    if not result.is_valid or result.volume <= 0.0 or len(result.shells()) != 1:
        raise RuntimeError(f"P029 {label} exact ruled shell failed")
    return result
'''
if old not in text:
    raise SystemExit('P029 ruled-draft anchor not found')
text = text.replace(old, new, 1)
old = '''    result = lower.fuse(draft).clean()
    solids = result.solids()
    if len(solids) != 1 or not solids[0].is_valid:
        raise RuntimeError(f"P029 {label} exact offset-band fusion failed")
    return solids[0]
'''
new = '''    result = lower.fuse(draft).clean()
    return _require_one_solid(result, f"{label} exact offset-band fusion")
'''
if old not in text:
    raise SystemExit('P029 upper fusion anchor not found')
text = text.replace(old, new, 1)
old = '''def _require_one_solid(shape: Solid, label: str) -> Solid:
    """Return one valid solid or reject the exact operation without repair."""
    solids = shape.solids()
    if not shape.is_valid or len(solids) != 1:
        raise RuntimeError(
            f"P029 {label} did not form one valid solid "
            f"(solid_count={len(solids)}); no bridge or fuzzy repair is permitted"
        )
    return solids[0].clean()
'''
new = '''def _require_one_solid(shape: Solid, label: str) -> Solid:
    """Return one valid solid or reject the exact operation without repair."""
    if isinstance(shape, Solid) and shape.is_valid and shape.volume > 0.0:
        if len(shape.shells()) == 1:
            return shape.clean()
    solids = shape.solids()
    valid_solids = [solid for solid in solids if solid.is_valid and solid.volume > 0.0]
    if not shape.is_valid or len(valid_solids) != 1:
        raise RuntimeError(
            f"P029 {label} did not form one valid solid "
            f"(solid_count={len(valid_solids)}); no bridge or fuzzy repair is permitted"
        )
    return valid_solids[0].clean()
'''
if old not in text:
    raise SystemExit('P029 one-solid anchor not found')
text = text.replace(old, new, 1)
p029.write_text(text, encoding='utf-8')
print('Applied P029 exact sewn ruled-shell construction')
