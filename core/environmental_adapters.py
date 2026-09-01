"""Compatibility adapters between legacy tonne-force APIs and SI load models."""

from __future__ import annotations

from core.environmental_models import LoadVector
from core.units import STANDARD_GRAVITY


def load_vector_to_legacy(load: LoadVector) -> dict[str, float]:
    """Convert SI N/Nm to legacy tonne-force/tonne-force-metre outputs."""
    tonne_force_n = 1000.0 * STANDARD_GRAVITY
    return {
        "Fx_total_t": load.fx_n / tonne_force_n,
        "Fy_total_t": load.fy_n / tonne_force_n,
        "Mz_total_tm": load.mz_nm / tonne_force_n,
    }
