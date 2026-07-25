from __future__ import annotations

"""Analysis-only extraction of compact five-branch Kailh meniscus datums."""

import json
from pathlib import Path

from build123d import Vector, import_step

from candidate_joint import _resolved
from five_branch_analysis import BOUNDARIES_YZ, INTERIORS_YZ, nearest_parameter
from reference_canal_probe import find_profile_contour, find_profile_face, isolate_right_solder


def main() -> None:
    out = Path("artifacts/branch_datums")
    out.mkdir(parents=True, exist_ok=True)
    reference = import_step("reference.step")
    _, solder = isolate_right_solder(reference)
    profile = find_profile_face(solder)
    contour = find_profile_contour(profile)

    boundary_parameters = [nearest_parameter(contour, point) for point in BOUNDARIES_YZ]
    interior_parameters = [nearest_parameter(contour, point) for point in INTERIORS_YZ]

    boundaries = []
    for requested, parameter in zip(BOUNDARIES_YZ, boundary_parameters):
        position = contour.position_at(parameter)
        tangent = Vector(contour.tangent_at(parameter)).normalized()
        boundaries.append(
            {
                "requested_yz": requested,
                "parameter": parameter,
                "exact_position": list(position.to_tuple()),
                "position_error": ((position.Y-requested[0])**2 + (position.Z-requested[1])**2) ** 0.5,
                "tangent": list(tangent.to_tuple()),
                "tangent_yz_normalized": list(Vector(0, tangent.Y, tangent.Z).normalized().to_tuple()),
            }
        )

    interiors = []
    for requested, parameter in zip(INTERIORS_YZ, interior_parameters):
        position = contour.position_at(parameter)
        tangent = Vector(contour.tangent_at(parameter)).normalized()
        interiors.append(
            {
                "requested_yz": requested,
                "parameter": parameter,
                "exact_position": list(position.to_tuple()),
                "position_error": ((position.Y-requested[0])**2 + (position.Z-requested[1])**2) ** 0.5,
                "tangent": list(tangent.to_tuple()),
            }
        )

    report = {
        "reference_imported_contour_length": float(_resolved(contour.length)),
        "profile_area": float(_resolved(profile.area)),
        "boundaries": boundaries,
        "interiors": interiors,
    }
    (out / "branch_datums.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
