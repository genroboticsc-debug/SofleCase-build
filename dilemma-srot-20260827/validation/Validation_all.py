
import os
import csv
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from build123d import import_step, export_stl

SCRIPT_DIR = Path(__file__).resolve().parent

ROOT = SCRIPT_DIR.parent

GENERATED_DIR = ROOT / "generated"
REFERENCE_DIR = ROOT / "reference"

VALID_EXTS = {".stl", ".step", ".stp"}

# VALID_EXTS = {".stl", ".step", ".stp"}

# ============================================================
# TOLERANCES
# ============================================================

VOL_TOL  = 0.5     # %
AREA_TOL = 0.5     # %
BBOX_TOL = 0.2     # mm
COM_TOL  = 0.2     # mm
SYM_TOL  = 0.5     # %

def load_mesh(path):

    ext = path.suffix.lower()

    if ext == ".stl":

        mesh = trimesh.load(str(path), force="mesh")

    elif ext in [".step", ".stp"]:

        shape = import_step(str(path))

        tmp = tempfile.NamedTemporaryFile(
            suffix=".stl",
            delete=False
        )

        tmp.close()

        export_stl(shape, tmp.name)

        mesh = trimesh.load(
            tmp.name,
            force="mesh"
        )

        os.unlink(tmp.name)

    else:
        raise ValueError(f"Unsupported file: {path}")

    if not isinstance(mesh, trimesh.Trimesh):
        mesh = trimesh.util.concatenate(mesh.dump())

    try:
        trimesh.repair.fix_normals(mesh)
    except:
        pass

    return mesh


# ============================================================
# VOLUME
# ============================================================

def signed_volume(mesh):

    verts = mesh.vertices
    faces = mesh.faces

    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]

    cross = np.cross(v1, v2)

    vol = abs(
        np.sum(
            np.einsum("ij,ij->i", v0, cross)
        ) / 6.0
    )

    return float(vol)


def get_volume(mesh):

    try:

        if mesh.is_watertight:

            vol = abs(mesh.volume)

            if vol > 0:
                return vol

    except:
        pass

    return signed_volume(mesh)


# ============================================================
# SYMMETRIC DIFFERENCE
# ============================================================

def symmetric_difference(mesh_a, mesh_b, vol_a, vol_b):

    avg_vol = max(
        (vol_a + vol_b) / 2.0,
        1e-9
    )

    for engine in ["manifold", "blender"]:

        try:

            a_minus_b = trimesh.boolean.difference(
                [mesh_a, mesh_b],
                engine=engine
            )

            b_minus_a = trimesh.boolean.difference(
                [mesh_b, mesh_a],
                engine=engine
            )

            vol1 = (
                get_volume(a_minus_b)
                if a_minus_b is not None
                else 0.0
            )

            vol2 = (
                get_volume(b_minus_a)
                if b_minus_a is not None
                else 0.0
            )

            sym = vol1 + vol2

            return (
                sym / avg_vol
            ) * 100.0

        except:
            continue

    return abs(vol_a - vol_b) / avg_vol * 100.0


# ============================================================
# HELPERS
# ============================================================

def pct_error(a, b):

    if b == 0:
        return 0.0

    return abs(a - b) / abs(b) * 100.0


# ============================================================
# FIND PROJECTS
# ============================================================

# projects = []

# for generated_dir in ROOT.rglob("generated"):

#     reference_dir = (
#         generated_dir.parent / "reference"
#     )

#     if reference_dir.exists():

#         project_name = generated_dir.parent.name

#         projects.append(
#             (
#                 project_name,
#                 generated_dir,
#                 reference_dir
#             )
#         )

projects = []

if GENERATED_DIR.exists() and REFERENCE_DIR.exists():

    projects.append(
        (
            ROOT.name,
            GENERATED_DIR,
            REFERENCE_DIR
        )
    )

else:

    raise FileNotFoundError(
        f"\nGenerated folder : {GENERATED_DIR}"
        f"\nReference folder : {REFERENCE_DIR}"
        "\nOne or both folders do not exist."
    )

# ============================================================
# REPORTS
# ============================================================

validation_rows = []
project_summary = []

# ============================================================
# PROCESS PROJECTS
# ============================================================

for project_name, gen_dir, ref_dir in projects:

    gen_files = {
        (
            f.stem.lower(),
            f.suffix.lower()
        ): f
        for f in gen_dir.iterdir()
        if f.suffix.lower() in VALID_EXTS
    }

    ref_files = {
        (
            f.stem.lower(),
            f.suffix.lower()
        ): f
        for f in ref_dir.iterdir()
        if f.suffix.lower() in VALID_EXTS
    }

    common = sorted(
        set(gen_files.keys())
        &
        set(ref_files.keys())
    )

    project_pass = 0
    project_fail = 0

    for key in common:

        gen_file = gen_files[key]
        ref_file = ref_files[key]

        try:

            gm = load_mesh(gen_file)
            rm = load_mesh(ref_file)

            gv = get_volume(gm)
            rv = get_volume(rm)

            ga = float(gm.area)
            ra = float(rm.area)

            gb = gm.bounding_box.extents
            rb = rm.bounding_box.extents

            gcom = gm.center_mass
            rcom = rm.center_mass

            volume_err = pct_error(gv, rv)
            area_err = pct_error(ga, ra)

            bbox_dx = abs(gb[0] - rb[0])
            bbox_dy = abs(gb[1] - rb[1])
            bbox_dz = abs(gb[2] - rb[2])

            com_shift = float(
                np.linalg.norm(
                    gcom - rcom
                )
            )

            sym_pct = symmetric_difference(
                gm,
                rm,
                gv,
                rv
            )

            volume_pass = (
                volume_err <= VOL_TOL
            )

            area_pass = (
                area_err <= AREA_TOL
            )

            bbox_pass = (
                bbox_dx <= BBOX_TOL
                and
                bbox_dy <= BBOX_TOL
                and
                bbox_dz <= BBOX_TOL
            )

            com_pass = (
                com_shift <= COM_TOL
            )

            sym_pass = (
                sym_pct <= SYM_TOL
            )

            overall = all([
                volume_pass,
                area_pass,
                bbox_pass,
                com_pass,
                sym_pass
            ])

            if overall:
                project_pass += 1
            else:
                project_fail += 1

            validation_rows.append({

                "Project_Name":
                    project_name,

                "Part_Name":
                    gen_file.stem,

                "Format":
                    gen_file.suffix,

                "Reference_File":
                    ref_file.name,

                "Generated_File":
                    gen_file.name,

                "Ref_Volume_mm3":
                    round(rv, 6),

                "Gen_Volume_mm3":
                    round(gv, 6),

                "Volume_Error_%":
                    round(volume_err, 6),

                "Ref_SurfaceArea_mm2":
                    round(ra, 6),

                "Gen_SurfaceArea_mm2":
                    round(ga, 6),

                "Area_Error_%":
                    round(area_err, 6),

                "BBox_X_Diff_mm":
                    round(bbox_dx, 6),

                "BBox_Y_Diff_mm":
                    round(bbox_dy, 6),

                "BBox_Z_Diff_mm":
                    round(bbox_dz, 6),

                "COM_Shift_mm":
                    round(com_shift, 6),

                "Ref_Vertices":
                    len(rm.vertices),

                "Gen_Vertices":
                    len(gm.vertices),

                "Ref_Faces":
                    len(rm.faces),

                "Gen_Faces":
                    len(gm.faces),

                "Symmetric_Difference_%":
                    round(sym_pct, 6),

                "Volume_PASS":
                    volume_pass,

                "Area_PASS":
                    area_pass,

                "BBox_PASS":
                    bbox_pass,

                "COM_PASS":
                    com_pass,

                "SymDiff_PASS":
                    sym_pass,

                "OVERALL_PASS":
                    overall

            })

        except Exception as e:

            project_fail += 1

            validation_rows.append({

                "Project_Name":
                    project_name,

                "Part_Name":
                    gen_file.stem,

                "Format":
                    gen_file.suffix,

                "ERROR":
                    str(e),

                "OVERALL_PASS":
                    False
            })

    total_parts = (
        project_pass +
        project_fail
    )

    pass_rate = (
        project_pass /
        total_parts * 100
        if total_parts
        else 0
    )

    project_summary.append({

        "Project_Name":
            project_name,

        "Total_Parts":
            total_parts,

        "Passed_Parts":
            project_pass,

        "Failed_Parts":
            project_fail,

        "Pass_Rate_%":
            round(pass_rate, 2),

        "Project_Result":
            (
                "PASS"
                if project_fail == 0
                else "FAIL"
            )
    })


# ============================================================
# SAVE REPORTS
# ============================================================

if validation_rows:

    with open(
        "validation_report.csv",
        "w",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=validation_rows[0].keys()
        )

        writer.writeheader()
        writer.writerows(validation_rows)

if project_summary:

    with open(
        "project_summary.csv",
        "w",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=project_summary[0].keys()
        )

        writer.writeheader()
        writer.writerows(project_summary)

print()
print("Validation Complete")
print("Generated:")
print("  validation_report.csv")
print("  project_summary.csv")
print()
