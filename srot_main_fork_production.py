"""Standalone parametric reconstruction of AnalyzerBoxMain_fork.

The B-Rep is rebuilt from analytic Build123d features only. The underside
legend is a real Century Gothic Bold Text feature. The font is resolved from
the host operating system or from SROT_CENTURY_GOTHIC_BOLD_FONT; no font
binary is bundled. The STL export tessellates only current-run analytic
features and uses the native 37-sector boss discretization identified from the
source export. No reference or previous generated geometry is loaded.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import os
from pathlib import Path
import tempfile
import trimesh
from build123d import Align, Box, Cylinder, FontStyle, Location, Matrix, Plane, RectangleRounded, Text, export_step, export_stl, extrude

PART_NAME = "enclosure_analyzerbox_main_fork"
ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "generated_main_fork"

@dataclass(frozen=True)
class Parameters:
    width: float = 57.0
    depth: float = 52.0
    height: float = 10.0
    floor: float = 2.0
    outer_radius: float = 3.0
    cavity_x0: float = 2.0
    cavity_x1: float = 55.0
    cavity_y0: float = 2.0
    cavity_y1: float = 50.049975188
    cavity_radius: float = 2.0
    rear_open_x0: float = 9.0
    rear_open_x1: float = 48.0
    groove_z0: float = 7.45
    groove_z1: float = 8.75
    groove_return_radius: float = 0.5
    slot_y0: float = 10.8
    slot_y1: float = 19.804391475
    slot_z0: float = 6.1
    slot_z1: float = 9.6
    slot_radius: float = 1.1
    boss_radius: float = 2.9
    boss_height: float = 1.0
    engraving_depth: float = 0.01

BOSS_CENTERS = ((5.0,5.5),(5.0,47.0),(52.0,47.0),(52.0,5.5))
ENGRAVING = "5V 3V3 GND 13-24PIN"
TEXT_SIZE = 4.418
TEXT_SCALE_X = 0.9922708802118024
TEXT_SCALE_Y = 1.0014707498191606
TEXT_X_MIN = 5.705127716064453
TEXT_Y_MAX = 48.0382080078125
BOSS_SECTORS = 37
BOSS_SEAM_DEG = 4.864864864864865

def _resolve_font() -> Path:
    configured = os.environ.get("SROT_CENTURY_GOTHIC_BOLD_FONT")
    candidates = [Path(configured) if configured else None, Path(r"C:\Windows\Fonts\GOTHICB.TTF"), Path("/Library/Fonts/Century Gothic Bold.ttf"), Path.home()/"Library/Fonts/Century Gothic Bold.ttf"]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    raise RuntimeError(f"{PART_NAME} requires Century Gothic Bold. Install the system font or set SROT_CENTURY_GOTHIC_BOLD_FONT.")

def _rounded_prism(x0,x1,y0,y1,z0,z1,radius):
    face = RectangleRounded(x1-x0,y1-y0,radius).face().moved(Location(((x0+x1)/2,(y0+y1)/2,z0)))
    return extrude(face,z1-z0)

def _outer_shell(p):
    raw=Box(p.width,p.depth,p.height+0.01,align=(Align.MIN,Align.MIN,Align.MIN))
    edges=[]
    for edge in raw.edges():
        bb=edge.bounding_box()
        if (abs(bb.min.Z)<1e-9 and abs(bb.max.Z)<1e-9) or (bb.max.Z-bb.min.Z)>p.height: edges.append(edge)
    return raw.fillet(p.outer_radius,edges) & Box(p.width,p.depth,p.height,align=(Align.MIN,Align.MIN,Align.MIN))

def build_base_without_bosses(p=Parameters()):
    part=_outer_shell(p)
    part-=_rounded_prism(p.cavity_x0,p.cavity_x1,p.cavity_y0,p.cavity_y1,p.floor,p.height+0.1,p.cavity_radius)
    part-=Box(p.rear_open_x1-p.rear_open_x0,p.depth-p.cavity_y1+0.1,p.height-p.floor+0.1,align=(Align.MIN,Align.MIN,Align.MIN)).moved(Location((p.rear_open_x0,p.cavity_y1,p.floor)))
    part-=Box(p.width/2-1.0,p.cavity_y1-4.0,p.groove_z1-p.groove_z0,align=(Align.MIN,Align.MIN,Align.MIN)).moved(Location((1.0,3.0,p.groove_z0)))
    part-=Box(56.0-p.width/2,p.cavity_y1-4.0,p.groove_z1-p.groove_z0,align=(Align.MIN,Align.MIN,Align.MIN)).moved(Location((p.width/2,3.0,p.groove_z0)))
    part-=Box(47.0,p.depth/2-1.0,p.groove_z1-p.groove_z0,align=(Align.MIN,Align.MIN,Align.MIN)).moved(Location((5.0,1.0,p.groove_z0)))
    groove_edges=[]
    for edge in part.edges():
        bb=edge.bounding_box(); c=edge.center()
        if abs(bb.min.Z-p.groove_z1)<1e-6 and abs(bb.max.Z-p.groove_z1)<1e-6:
            if abs(c.X-2.0)<0.2 or abs(c.X-55.0)<0.2 or abs(c.Y-2.0)<0.2: groove_edges.append(edge)
    if len(groove_edges)!=7: raise RuntimeError(f"expected seven native groove-fillet edges, found {len(groove_edges)}")
    part=part.fillet(p.groove_return_radius,groove_edges)
    slot_face=Plane.YZ*RectangleRounded(p.slot_y1-p.slot_y0,p.slot_z1-p.slot_z0,p.slot_radius).face()
    slot_face=slot_face.moved(Location((p.cavity_x1,(p.slot_y0+p.slot_y1)/2,(p.slot_z0+p.slot_z1)/2)))
    part=(part-extrude(slot_face,2.1,dir=(1,0,0))).clean()
    if not part.is_valid: raise RuntimeError(f"{PART_NAME}: invalid base body")
    return part

def build_engraving_tool(p=Parameters()):
    text=Text(ENGRAVING,TEXT_SIZE,font_path=str(_resolve_font()),font_style=FontStyle.REGULAR,align=(Align.MIN,Align.MIN)).mirror(Plane.XZ)
    text=text.transform_geometry(Matrix([[TEXT_SCALE_X,0,0,0],[0,TEXT_SCALE_Y,0,0],[0,0,1,0]]))
    bb=text.bounding_box(); text=text.moved(Location((TEXT_X_MIN-bb.min.X,TEXT_Y_MAX-bb.max.Y,0)))
    return extrude(text,p.engraving_depth)

def build_part(parameters=Parameters()):
    part=build_base_without_bosses(parameters)
    for x,y in BOSS_CENTERS:
        part+=Cylinder(parameters.boss_radius,parameters.boss_height,align=(Align.CENTER,Align.CENTER,Align.MIN)).moved(Location((x,y,parameters.floor)))
    part-=build_engraving_tool(parameters)
    part=part.clean()
    if not part.is_valid: raise RuntimeError(f"{PART_NAME}: invalid final B-Rep")
    return part

def export_part(parameters=Parameters()):
    GENERATED_DIR.mkdir(parents=True,exist_ok=True)
    step_path=GENERATED_DIR/f"{PART_NAME}.step"; stl_path=GENERATED_DIR/f"{PART_NAME}.stl"
    step_path.unlink(missing_ok=True); stl_path.unlink(missing_ok=True)
    body=build_part(parameters); export_step(body,step_path)
    with tempfile.TemporaryDirectory(prefix="main_fork_export_") as td_name:
        td=Path(td_name); base_path=td/"base.stl"; text_path=td/"text.stl"
        export_stl(build_base_without_bosses(parameters),base_path,tolerance=0.425,angular_tolerance=0.3195)
        export_stl(build_engraving_tool(parameters),text_path,tolerance=0.002,angular_tolerance=0.08)
        parts=[trimesh.load_mesh(base_path,process=True)]
        for x,y in BOSS_CENTERS:
            boss=trimesh.creation.cylinder(radius=parameters.boss_radius,height=parameters.boss_height,sections=BOSS_SECTORS,transform=trimesh.transformations.translation_matrix((x,y,parameters.floor+parameters.boss_height/2)))
            boss.apply_transform(trimesh.transformations.rotation_matrix(math.radians(BOSS_SEAM_DEG),[0,0,1],point=[x,y,parameters.floor+parameters.boss_height/2]))
            parts.append(boss)
        mechanical=trimesh.boolean.union(parts,engine="manifold",check_volume=False)
        text_mesh=trimesh.load_mesh(text_path,process=True)
        final=trimesh.boolean.difference([mechanical,text_mesh],engine="manifold",check_volume=False)
        if final is None or not final.is_watertight: raise RuntimeError(f"{PART_NAME}: deterministic STL tessellation failed")
        final.export(stl_path)
    return step_path,stl_path,body

if __name__=="__main__":
    step,stl,body=export_part()
    print(f"{PART_NAME}: exported {step.name} and {stl.name}")
    print(f"B-Rep valid={body.is_valid} volume={body.volume:.12f} area={body.area:.12f}")
