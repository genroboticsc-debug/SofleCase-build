#!/usr/bin/env python3
"""Apply all identified honeycomb cells as one Boolean tool without altering them."""
from pathlib import Path
path=Path(__file__).with_name('dilemma_tenting_puck_family.py')
s=path.read_text()
old='''    for cutter in cutters:
        cut_pieces=pieces(body.cut(cutter))
        if len(cut_pieces)==1:
            body=cut_pieces[0]
    if cutters:
        body=one(body.clean(),"honeycomb floor")

'''
new='''    if cutters:
        body=one(
            body.cut(Compound(cutters)).fix().clean(),
            "honeycomb floor",
        )

'''
if old not in s:
    raise RuntimeError('sequential honeycomb block not found')
path.write_text(s.replace(old,new,1))
print(f'batched {"identified"} honeycomb cutter feature set')
