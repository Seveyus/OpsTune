"""AI4I 2020 documented failure-mode thresholds, in one place."""

from __future__ import annotations

import math
from typing import Literal

ProductVariant = Literal["L", "M", "H"]

# TWF: tool wear failure window (minutes)
TWF_WEAR_MIN = 200
TWF_WEAR_MAX = 240

# HDF: heat dissipation failure
HDF_DELTA_T_MAX_K = 8.6      # process_temp - air_temp must be < this
HDF_RPM_MAX = 1380           # AND rpm must be < this

# PWF: power failure (watts)
PWF_POWER_MIN = 3500
PWF_POWER_MAX = 9000

# OSF: overstrain failure (torque * tool_wear), variant-specific
OSF_TORQUE_WEAR_LIMIT: dict[str, int] = {
    "L": 11_000,
    "M": 12_000,
    "H": 13_000,
}


def power_w(torque_nm: float, rpm: float) -> float:
    """Mechanical power = torque * angular_velocity."""
    return torque_nm * rpm * 2.0 * math.pi / 60.0


def delta_t_k(air_temp_k: float, process_temp_k: float) -> float:
    return process_temp_k - air_temp_k


def osf_limit(variant: str) -> int:
    return OSF_TORQUE_WEAR_LIMIT[variant]
