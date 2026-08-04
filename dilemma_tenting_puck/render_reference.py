#!/usr/bin/env python3
from pathlib import Path
import urllib.parse, urllib.request
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from build123d import import_step

ROOT=Path(__file__).resolve().parent
REF=ROOT/'reference'; OUT=ROOT/'analysis_output'; REF.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
BASE='https://raw.githubusercontent.com/Bastardkb/Dilemma/main/mechanical/cases/3x5_2/tenting_puck_hex/STEP/'
FILES={
 'integrated':'Dilemma Case Integrated Tenting Puck.STEP',
 'opening':'Dilemma Case Tenting Puck Opening.STEP',
}

def get(name):
 p=REF/name
 if not p.exists(): urllib.request.urlretrieve(BASE+urllib.parse.quote(name),p)
 return p

def render(shape, key, elev, azim, suffix):
 verts, tris = shape.tessellate(0.08, 0.15)
 xyz=[(v.X,v.Y,v.Z) for v in verts]
 polys=[[xyz[i] for i in t] for t in tris]
 fig=plt.figure(figsize=(12,9),dpi=180)
 ax=fig.add_subplot(111,projection='3d')
 pc=Poly3DCollection(polys, linewidths=0.04, edgecolors='black')
 pc.set_facecolor((0.78,0.80,0.84,1.0))
 ax.add_collection3d(pc)
 xs=[p[0] for p in xyz]; ys=[p[1] for p in xyz]; zs=[p[2] for p in xyz]
 ax.set_xlim(min(xs),max(xs)); ax.set_ylim(min(ys),max(ys)); ax.set_zlim(min(zs),max(zs))
 ax.set_box_aspect((max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)))
 ax.view_init(elev=elev,azim=azim)
 ax.set_axis_off(); fig.tight_layout(pad=0)
 fig.savefig(OUT/f'{key}_{suffix}.png',bbox_inches='tight',pad_inches=0)
 plt.close(fig)

for key,name in FILES.items():
 shape=list(import_step(get(name)).solids())[0]
 render(shape,key,28,-55,'isometric')
 render(shape,key,90,-90,'top')
 render(shape,key,-90,90,'bottom')
 render(shape,key,0,-90,'front')
