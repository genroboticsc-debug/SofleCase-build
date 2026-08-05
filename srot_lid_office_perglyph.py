from __future__ import annotations
from pathlib import Path
import json
from build123d import Align, Axis, Compound, FontStyle, Location, Matrix, Text, export_stl, extrude

OUT = Path('lid_office_perglyph_results')
OUT.mkdir(exist_ok=True)
CHARS = list('LogicAnalyzer')
ENVELOPES = [
    (10.204837799072266,12.454838752746582,13.228985786437988,17.728986740112305),
    (12.858684539794922,16.43560791015625,14.325139999389648,17.786678314208984),
    (17.012531280517578,20.531761169433594,14.325139999389648,18.99821662902832),
    (21.22406768798828,22.147144317626953,13.055909156799316,17.728986740112305),
    (22.608684539794922,26.18560791015625,14.325139999389648,17.786678314208984),
    (28.377914428710938,32.76253128051758,13.228985786437988,17.728986740112305),
    (33.281761169433594,36.281761169433594,14.325139999389648,17.728986740112305),
    (36.97406768798828,40.55099105834961,14.325139999389648,17.786678314208984),
    (41.416378021240234,41.99330139160156,13.113600730895996,17.728986740112305),
    (42.454837799072266,45.74330139160156,14.382832527160645,18.94052505493164),
    (45.68560791015625,48.45484161376953,14.382832527160645,17.728986740112305),
    (48.68560791015625,52.261627197265625,14.325139999389648,17.786678314208984),
    (52.781761169433594,54.57022476196289,14.325139999389648,17.728986740112305),
]
FONTS = {
    'regular': Path(r'C:\Windows\Fonts\GOTHIC.TTF'),
    'bold': Path(r'C:\Windows\Fonts\GOTHICB.TTF'),
}
SETTINGS = [(0.01,0.04),(0.05,0.10),(0.10,0.12),(0.20,0.18),(0.30,0.25),(0.50,0.35)]

def build(font: Path):
    solids=[]
    for ch,(x0,x1,z0,z1) in zip(CHARS,ENVELOPES,strict=True):
        glyph=Text(ch,10.0,font_path=str(font),font_style=FontStyle.REGULAR,align=(Align.MIN,Align.MIN))
        bb=glyph.bounding_box()
        sx=(x1-x0)/bb.size.X
        sy=(z1-z0)/bb.size.Y
        glyph=glyph.transform_geometry(Matrix([[sx,0,0,x0-bb.min.X*sx],[0,sy,0,z0-bb.min.Y*sy],[0,0,1,0]]))
        for face in glyph.faces():
            solids.append(extrude(face,1.0).rotate(Axis.X,90).moved(Location((0,15,0))))
    return Compound(children=solids)

rows=[]
for name,font in FONTS.items():
    if not font.exists():
        raise FileNotFoundError(font)
    for tolerance,angular in SETTINGS:
        body=build(font)
        path=OUT/f'{name}_t{tolerance:.3f}_a{angular:.3f}.stl'
        export_stl(body,path,tolerance=tolerance,angular_tolerance=angular)
        rows.append({'name':name,'font_file':font.name,'tolerance':tolerance,'angular':angular,'brep_volume':body.volume,'file':path.name})
        print(json.dumps(rows[-1]),flush=True)
(OUT/'inventory.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
