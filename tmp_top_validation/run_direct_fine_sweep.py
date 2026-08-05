"""Run a dense absolute-deflection sweep around the direct-solid optimum."""

from __future__ import annotations

import validate_direct_final_solid as validator

validator.LINEAR_CANDIDATES = tuple(
    round(0.006700 + index * 0.000002, 12)
    for index in range(21)
)

raise SystemExit(validator.main())
