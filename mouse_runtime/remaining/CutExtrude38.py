"""CutExtrude38 â€” true parametric Build123d engineering reconstruction.

Production principles
---------------------
* Build123d only for production geometry.
* No runtime external geometry or measurement dependency.
* No mesh, topology, face, control-net, or serialized-BRep replay.
* Freeform geometry is represented by compact design-level station splines.
* STEP and STL are exported from the same final in-memory body.

The compact spline dimensions are centralized below so the model remains directly
editable as engineering CAD rather than as a frozen boundary representation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# -----------------------------------------------------------------------------
# Global engineering datum
# -----------------------------------------------------------------------------
BASE_ORIGIN = (-27.1927261537, 4.069247124021, 29.505132325778)
BASE_X = (0.9873330604099253, 0.12122925628699083, -0.10235670589499225)
BASE_Y = (-0.14402414102394076, 0.9554448977587487, -0.2576472281028657)
BASE_N = (0.0665618131453691, 0.2691254631919963, 0.960802274191987)

THICKNESS = 3.0000000034967926
TOP_CHAMFER = 0.3999999999981267
BOTTOM_CHAMFER = 0.4000000487809249
ENTRY_CHAMFER = 0.4000000000203676

# Base-sketch analytic entities in BASE_X / BASE_Y coordinates.
P_TAN = (9.81715188024761, -7.310084213364956)
C_BOT = (9.058836533763921, -3.382622181064344)
C_TOP = (9.058836533762648, 5.901825229868524)
P_RIGHT_BOT = (13.058836533765293, -3.382622181064344)
P_RIGHT_TOP = (13.058836533765293, 5.901825229868524)
P_TOP_ARC = (9.058836533762648, 9.901825229868525)
P_TOP_LEFT = (-5.149086099731426, 9.901825229847896)
BASE_ARC_RADIUS = 4.0

# F001 long ergonomic sidewall. The source edge contains a deliberate short
# root transition before the main ergonomic run. Production expresses that
# design intent as one root cubic followed by five equal-arc ergonomic cubic
# spans. Each Bezier control point is DERIVED at runtime from a node, tangent
# direction, and handle length; no source B-spline pole/knot payload is stored.
F001_NODES_XY = (
    (-6.971674969817227, -10.551675075205164),
    (-7.042070961144828, -10.013954790567144),
    (-7.394516835176671, -6.641844031030509),
    (-7.628910916048634, -3.259311750498815),
    (-7.802272875047127, 0.126890300145170),
    (-7.941894291535687, 3.514553326182425),
    (-8.057878897744965, 6.903212009284213),
)
F001_TANGENTS_XY = (
    (-0.129807972346726, 0.991539152184739),
    (-0.129807965297206, 0.991539153107632),
    (-0.082853133965303, 0.996561768377720),
    (-0.058166790043370, 0.998306878938561),
    (-0.045353295006233, 0.998971009905732),
    (-0.037488894616629, 0.999297044316865),
    (-0.031645560330601, 0.999499153832239),
)
F001_HANDLE_LENGTHS = (
    (0.180797890183161, 0.180741245420528),
    (1.130442843692408, 1.130003098323100),
    (1.130403070865415, 1.130028472875243),
    (1.130384903171009, 1.130019282530307),
    (1.130339721108911, 1.130004841907834),
    (1.130404400878455, 1.130053004956103),
)
F001_ROOT_TRANSITION_SPANS = 1
F001_MAIN_EQUAL_ARC_SPANS = 5

# F003-F006 exact analytic trimming planes.
ANALYTIC_PLANES = {
    17: ((-35.29659716694, 12.605587491262, 27.259156993369),
         (-0.054774137330018235, 0.8659020062682883, 0.49720570131516556)),
    19: ((-29.47239889681, -5.974067175247, 32.059925158668),
         (0.2794143771158982, -0.4567983487538336, 0.8445489177286924)),
    9:  ((-33.64911853399, 12.504802608831, 24.883501432817),
         (0.6190899247633639, -0.21857487257618044, 0.7542895267301534)),
    26: ((-36.16939029012, 9.580384970823, 28.166995937729),
         (0.5249573094836927, -0.5991757397539061, -0.6044900794140478)),
}

# F009 CutExtrude38 sketch frame. s = extrusion direction, t/z = sketch plane.
CUT_SKETCH_S = -8.249920079615062
CUT_D = (0.9976089292468243, 0.0, -0.06911167981611219)
CUT_T = (-0.01859971284248814, 0.9631051266926646, -0.26848196516802314)
CUT_TERMINATION_POINT = (-32.64522386505, 14.634215637281, 23.801176487887)
CUT_TERMINATION_NORMAL = BASE_X
CUT_TERMINATION_LOCAL_X = -3.51880984653029
SOURCE_MAX_EDGE_TOL = 0.0004811162510803918

# M1: exact endpoints plus one fixed z=-2.75 mm engineering station.
F009_M1_TZ = (
    (-8.579858178370040, -3.000000255543007),
    (-9.241746912398863, -2.750000000000000),
    (-9.506714028941753, -2.375417717774031),
)
# M2: exact endpoints plus fixed z=-1.50 and -0.75 mm stations.
F009_M2_TZ = (
    (-9.506714028947531, -2.375417717755833),
    (-9.860835609307243, -1.500000000000000),
    (-10.163545536207234, -0.750000000000000),
    (-10.316282032594206, -0.371045415008155),
)
# Design-level tangent constraints: horizontal entry, exact G1 join, terminal tangent.
F009_M1_START_TANGENT_TZ = (-1.0, 0.0)
F009_G1_TANGENT_TZ = (-0.3754174622323743, 0.9268558297011482)
F009_M2_END_TANGENT_TZ = (-0.37368156850903333, 0.9275570523459076)
# Exact analytic line completing the inner cut profile.
F009_SIDE_TZ_TOP = (-10.065698564453816, 0.0)
F009_SIDE_TZ_BOTTOM = (-10.316282032590644, -0.37104541502108634)

# F010 deterministic predecessor-edge selector. This selects an edge; it does not
# drive the chamfer geometry, whose sole dimensional driver is ENTRY_CHAMFER.
ENTRY_EDGE_SIGNATURE = {
    "p0": (-33.21324159122219, -5.7260032888235255, 30.193588242290406),
    "pm": (-33.04302274327726, -5.8454644414360715, 31.247915660676902),
    "p1": (-32.87189674769418, -5.962832367674193, 32.29228664349603),
    "length": 2.139427248339715,
}

# F011 underside pocket: compact symmetric style-spline opening, then native 30Â° draft.
POCKET_DEPTH = 1.8
POCKET_DRAFT_ANGLE = 30.0
POCKET_PLANE_Z = -3.0
POCKET_XL = -1.3586101830554265
POCKET_XR = 3.841389816941242
POCKET_YB = -4.110934632976277
POCKET_YT = 6.089065367025198
POCKET_CORNER_REACH = math.sqrt(3.0) + 0.1
# Four compact handle dimensions + one diagonal station define the corner style.
POCKET_U1 = 1.324204932434067
POCKET_U2 = 0.8423369808425405
POCKET_V2 = 0.183560099731795
POCKET_DIAG = 0.5129485402896414

BLIND_HOLES = (
    {"radius": 1.0, "start": (-19.09520582634, 0.668154929498, 29.480501740072),
     "direction": BASE_N, "depth": 0.4000000000001262},
    {"radius": 1.0, "start": (-16.3243433523, 1.673156344411, 29.007037934079),
     "direction": BASE_N, "depth": 0.40000000000015534},
)
COUNTERSINK = {
    "axis_direction": (0.0665618135335809, 0.26912544309112496, 0.9608022797954461),
    "cylinder_radius": 1.2,
    "cylinder_start": (-19.868480107438465, 5.373093588075089, 25.51012366045769),
    "cylinder_height": 1.8500000438308948,
    "cone_start": (-19.745340749483876, 5.870975669589679, 27.28760792019209),
    "cone_height": 1.1499999868937805,
    "cone_r1": 1.2,
    "cone_r2": 2.3500000108932495,
}


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _scale(k, a):
    return tuple(k * a[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _distance(a, b):
    return _norm(_sub(a, b))


def _world(x, y, z=0.0):
    return _add(BASE_ORIGIN, _add(_scale(x, BASE_X), _add(_scale(y, BASE_Y), _scale(z, BASE_N))))


def _cut_world(t, z, s=CUT_SKETCH_S):
    return _add(BASE_ORIGIN, _add(_scale(s, CUT_D), _add(_scale(t, CUT_T), _scale(z, BASE_N))))


def _global_to_local(p):
    q = _sub(p, BASE_ORIGIN)
    return (_dot(q, BASE_X), _dot(q, BASE_Y), _dot(q, BASE_N))


def _global_to_stz(p):
    q = _sub(p, BASE_ORIGIN)
    return (_dot(q, CUT_D), _dot(q, CUT_T), _dot(q, BASE_N))


def _require_b3d():
    try:
        import build123d as b3d
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Build123d is required for production execution. Install requirements.txt first."
        ) from exc
    return b3d


def _point_tuple(p):
    return (float(p.X), float(p.Y), float(p.Z))


def _one_solid(shape, feature):
    solids = list(shape.solids())
    if len(solids) != 1:
        raise RuntimeError(f"{feature}: expected exactly one solid, got {len(solids)}")
    return solids[0]


def _arc_xy(center, start, end):
    b3d = _require_b3d()
    cx, cy = center
    sx, sy = start
    ex, ey = end
    a0 = math.atan2(sy - cy, sx - cx)
    a1 = math.atan2(ey - cy, ex - cx)
    while a1 <= a0:
        a1 += 2.0 * math.pi
    am = 0.5 * (a0 + a1)
    mid = (cx + BASE_ARC_RADIUS * math.cos(am), cy + BASE_ARC_RADIUS * math.sin(am))
    return b3d.ThreePointArc(_world(sx, sy), _world(*mid), _world(ex, ey))


# -----------------------------------------------------------------------------
# F001-F002 base sketch + extrusion
# -------------------------------------------------------------------------------
def build_F001_freeform_edges():
    b3d = _require_b3d()
    out = []
    for i, ((x0, y0), (x1, y1), (tx0, ty0), (tx1, ty1), (h0, h1)) in enumerate(
        zip(F001_NODES_XY[:-1], F001_NODES_XY[1:], F001_TANGENTS_XY[:-1], F001_TANGENTS_XY[1:], F001_HANDLE_LENGTHS)
    ):
        p0 = _world(x0, y0)
        p3 = _world(x1, y1)
        t0 = _add(_scale(tx0, BASE_X), _scale(ty0, BASE_Y))
        t1 = _add(_scale(tx1, BASE_X), _scale(ty1, BASE_Y))
        p1 = _add(p0, _scale(h0, t0))
        p2 = _add(p3, _scale(-h1, t1))
        out.append(b3d.Bezier(p0, p1, p2, p3))
    return out


def build_F001_base_sketch():
    b3d = _require_b3d()
    root = F001_NODES_XY[0]
    join = F001_NODES_XY[-1]
    edges = [
        b3d.Line(_world(*root), _world(*P_TAN)),
        _arc_xy(C_BOT, P_TAN, P_RIGHT_BOT),
        b3d.Line(_world(*P_RIGHT_BOT), _world(*P_RIGHT_TOP)),
        _arc_xy(C_TOP, P_RIGHT_TOP, P_TOP_ARC),
        b3d.Line(_world(*P_TOP_ARC), _world(*P_TOP_LEFT)),
        b3d.Line(_world(*P_TOP_LEFT), _world(*join)),
        *build_F001_freeform_edges(),
    ]
    return b3d.Face(b3d.Wire(edges, sequenced=True))


def build_F002_base_extrude():
    b3d = _require_b3d()
    face = build_F001_base_sketch()
    return _one_solid(
        b3d.extrude(face, amount=THICKNESS, dir=b3d.Vector(*BASE_N) * -1, mode=b3d.Mode.PRIVATE),
        "F002 BaseExtrude",
    )


# ------------------------------------------------------------------------------
# F003-F006 analytic plane trims
# -------------------------------------------------------------------------------
def _split_keep_largest(body, plane, feature):
    b3d = _require_b3d()
    pieces = b3d.split(body, bisect_by=plane, keep=b3d.Keep.BOTH, mode=b3d.Mode.PRIVATE)
    solids = list(pieces.solids())
    if len(solids) < 2:
        raise RuntimeError(f"{feature}: expected a real two-sided split, got {len(solids)} solids")
    return max(solids, key=lambda s: s.volume)


def apply_F003_to_F006(body):
    b3d = _require_b3d()
    for fid in (17, 19, 9, 26):
        origin, normal = ANALYTIC_PLANES[fid]
        n = b3d.Vector(*normal)
        x = b3d.Vector(*BASE_N).cross(n)
        if x.length < 1e-12:
            x = b3d.Vector(*BASE_X).cross(n)
        body = _split_keep_largest(
            body,
            b3d.Plane(origin=origin, x_dir=x.normalized(), z_dir=n),
            f"F{fid} analytic plane",
        )
    return body


# -----------------------------------------------------------------------------
# F007-F008 native 0.4 mm edge chamfers
# --------------------------------------------------------------------------------
def _select_F001_cap_chain(body, cap_z, feature):
    """Recover the complete segmented F001 predecessor edge chain on one cap.

    The engineering parent is intentionally piecewise.  Plane trims may shorten
    the first/last span, so each authored span is mapped to the nearest surviving
    cap edge by its design midpoint rather than by an arbitrary minimum length.
    """
    candidates = []
    for edge in body.edges():
        try:
            samples = [_global_to_local(_point_tuple(edge.position_at(t))) for t in (0.1, 0.5, 0.9)]
            if max(abs(p[2] - cap_z) for p in samples) > 5e-3:
                continue
            candidates.append(edge)
        except Exception:
            continue
    if not candidates:
        raise RuntimeError(f"{feature}: no cap edge candidates")

    selected = []
    for design_edge in build_F001_freeform_edges():
        target = _point_tuple(design_edge.position_at(0.5))
        if cap_z < -1e-9:
            target = _add(target, _scale(-THICKNESS, BASE_N))
        ranked = sorted((_distance(_point_tuple(edge.position_at(0.5)), target), edge) for edge in candidates)
        distance, edge = ranked[0]
        if distance > 0.35:
            raise RuntimeError(f"{feature}: F001 chain ownership residual {distance:.6f} mm exceeds 0.35 mm")
        if all(edge.wrapped.IsSame(prev.wrapped) is False for prev in selected):
            selected.append(edge)
    if len(selected) < 5:
        raise RuntimeError(f"{feature}: expected at least five surviving F001 cap spans, got {len(selected)}")
    return selected


def apply_F007_F008(body):
    top_edges = _select_F001_cap_chain(body, 0.0, "F007")
    body = _one_solid(body.chamfer(TOP_CHAMFER, None, top_edges), "F007 TopChamfer")
    bottom_edges = _select_F001_cap_chain(body, -THICKNESS, "F008")
    return _one_solid(body.chamfer(BOTTOM_CHAMFER, None, bottom_edges), "F008 BottomChamfer")


# ------------------------------------------------------------------------------
# F009 CutExtrude38: two station splines + analytic line + exact termination
# -----------------------------------------------------------------------------
def _cut_tangent_world(tangent_tz):
    return _add(_scale(tangent_tz[0], CUT_T), _scale(tangent_tz[1], BASE_N))


def build_F009_tool(sharp_base):
    b3d = _require_b3d()
    m1 = b3d.Spline(
        *W.·
+•Ûs~ŠíÎ)ÅÓOLÕ6mjxžÛ