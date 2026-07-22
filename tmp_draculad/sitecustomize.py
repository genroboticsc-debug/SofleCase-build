"""Temporary analysis-only startup patch for the Kailh solder candidate.

This file modifies only tmp_draculad/interrogate_solder_solids.py immediately
before that analysis script executes. Production CAD scripts and reference files
are never modified.
"""

from __future__ import annotations

from pathlib import Path
import sys


def _patch_candidate_selector() -> None:
    target = Path(__file__).with_name("interrogate_solder_solids.py")
    if not target.exists():
        return

    old = '''        if abs(bounds[0] - raw_end_x) <= 2.0e-5 and abs(bounds[3] - raw_end_x) <= 2.0e-5:
            terminal_edges.append(edge)
            terminal_edge_bounds.append(bounds)
    if len(terminal_edges) != 2:
        raise RuntimeError(
            f"Expected two terminal perimeter edges at X={raw_end_x}, found {len(terminal_edges)}: {terminal_edge_bounds}"
        )
'''

    new = '''        on_terminal_plane = (
            abs(bounds[0] - raw_end_x) <= 2.0e-5
            and abs(bounds[3] - raw_end_x) <= 2.0e-5
        )
        is_horizontal_top_land = (
            abs(bounds[2] - PAD_Z_MIN_MM) <= 2.0e-5
            and abs(bounds[5] - PAD_Z_MIN_MM) <= 2.0e-5
        )
        if on_terminal_plane and not is_horizontal_top_land:
            terminal_edges.append(edge)
            terminal_edge_bounds.append(bounds)
    if len(terminal_edges) != 10:
        raise RuntimeError(
            f"Expected ten curved terminal perimeter edges at X={raw_end_x}, found {len(terminal_edges)}: {terminal_edge_bounds}"
        )
'''

    text = target.read_text()
    if new in text:
        return
    if old not in text:
        raise RuntimeError("Temporary Kailh selector patch could not locate the audited source block")
    target.write_text(text.replace(old, new, 1))
    print(f"[sitecustomize] Applied ten-edge selector patch to {target}", file=sys.stderr)


_patch_candidate_selector()
