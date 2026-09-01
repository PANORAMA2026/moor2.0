"""Load-extension curves for mooring lines.

A curve may be populated from manufacturer/certificate data. The model uses
explicit strain points at defined percentages of LDBF and performs bounded
piecewise-linear interpolation. It intentionally refuses unsupported
extrapolation beyond the supplied data.

A material-name-only curve is never treated as certified data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class LoadStrainPoint:
    load_fraction_ldbf: float
    strain: float

    def __post_init__(self) -> None:
        if not 0.0 < self.load_fraction_ldbf <= 1.0:
            raise ValueError("Load fraction must be in (0, 1].")
        if self.strain < 0:
            raise ValueError("Strain cannot be negative.")


@dataclass(frozen=True)
class LineLoadExtensionCurve:
    """A bounded line load/strain curve with provenance metadata."""

    ldbf_kn: float
    points: tuple[LoadStrainPoint, ...]
    source: str
    certified: bool = False

    def __post_init__(self) -> None:
        if self.ldbf_kn <= 0:
            raise ValueError("LDBF must be greater than zero.")
        if len(self.points) < 2:
            raise ValueError("At least two load-strain points are required.")
        fractions = [p.load_fraction_ldbf for p in self.points]
        if fractions != sorted(fractions) or len(set(fractions)) != len(fractions):
            raise ValueError("Curve load fractions must be strictly increasing.")

    @property
    def max_fraction(self) -> float:
        return self.points[-1].load_fraction_ldbf

    def strain_at_load(self, load_kn: float) -> float:
        if load_kn < 0:
            raise ValueError("Line load cannot be negative.")
        fraction = load_kn / self.ldbf_kn
        fractions = np.array([p.load_fraction_ldbf for p in self.points], dtype=float)
        strains = np.array([p.strain for p in self.points], dtype=float)
        if fraction < fractions[0] or fraction > fractions[-1]:
            raise ValueError(
                f"Load fraction {fraction:.4f} is outside the supplied curve "
                f"range [{fractions[0]:.4f}, {fractions[-1]:.4f}]."
            )
        return float(np.interp(fraction, fractions, strains))

    def load_at_strain(self, strain: float) -> float:
        if strain < 0:
            raise ValueError("Strain cannot be negative.")
        fractions = np.array([p.load_fraction_ldbf for p in self.points], dtype=float)
        strains = np.array([p.strain for p in self.points], dtype=float)
        if strain < strains[0] or strain > strains[-1]:
            raise ValueError("Requested strain is outside the supplied curve range.")
        return float(np.interp(strain, strains, fractions) * self.ldbf_kn)

    def secant_stiffness_kn_per_m(self, load_kn: float, length_m: float) -> float:
        if length_m <= 0:
            raise ValueError("Line length must be greater than zero.")
        strain = self.strain_at_load(load_kn)
        if strain <= 0:
            raise ValueError("Zero strain does not define a finite secant stiffness.")
        extension_m = strain * length_m
        return load_kn / extension_m


def curve_from_certificate(
    ldbf_kn: float,
    strain_at_percent_ldbf: dict[float, float],
    source: str,
) -> LineLoadExtensionCurve:
    """Build a bounded curve from certificate strain values.

    Keys are load percentages (e.g. 10, 20, 30, 40, 50); values are decimal
    strain (e.g. 0.015 for 1.5%). The source should identify the actual
    certificate/report. This is certificate-derived data, not a generic
    material curve.
    """
    points = tuple(
        LoadStrainPoint(float(percent) / 100.0, float(strain))
        for percent, strain in sorted(strain_at_percent_ldbf.items())
    )
    if any(percent <= 0 or percent > 100 for percent in strain_at_percent_ldbf):
        raise ValueError("Certificate load percentages must be within (0, 100].")
    return LineLoadExtensionCurve(
        ldbf_kn=ldbf_kn,
        points=points,
        source=source,
        certified=True,
    )


def curve_from_generic_material(
    material: str,
    ldbf_kn: float,
    source: str = "GENERIC_ENGINEERING_ASSUMPTION",
) -> LineLoadExtensionCurve:
    """Create a clearly non-certified fallback curve.

    This function is intentionally conservative only in software behaviour;
    its values are engineering assumptions and must not be represented as
    MEG4 or manufacturer data.
    """
    break_strain = {
        "HMPE": 0.025,
        "POLYESTER": 0.070,
        "NYLON": 0.180,
        "STEEL_WIRE": 0.012,
    }.get(material.upper().strip(), 0.050)
    fractions = (0.10, 0.20, 0.30, 0.40, 0.50)
    points = tuple(LoadStrainPoint(f, break_strain * f) for f in fractions)
    return LineLoadExtensionCurve(
        ldbf_kn=ldbf_kn,
        points=points,
        source=source,
        certified=False,
    )
