"""Weak-link evaluation for composite mooring lines.

A physical mooring line may be a main rope only or a series assembly such as
main line + tail + GeoLink/lashing component.  The governing breaking load is
therefore the lowest applicable *declared* breaking-load value among the
components.  This module deliberately preserves the source terminology and
never invents MBL/LDBF from a differently named certificate value.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class BreakingLoadValue:
    value_kn: float
    label: str
    source: str = "CERTIFICATE"


@dataclass(frozen=True)
class ComponentStrength:
    component_id: str
    component_type: str
    certificate_id: str | None
    breaking_loads: tuple[BreakingLoadValue, ...]

    @property
    def governing_breaking_load_kn(self) -> float | None:
        values = [x.value_kn for x in self.breaking_loads if x.value_kn > 0]
        return min(values) if values else None

    @property
    def governing_breaking_load_label(self) -> str | None:
        if not self.breaking_loads:
            return None
        selected = min(self.breaking_loads, key=lambda x: x.value_kn)
        return selected.label


@dataclass(frozen=True)
class WeakLinkResult:
    status: str
    weak_link_component_id: str | None
    weak_link_component_type: str | None
    weak_link_certificate_id: str | None
    weak_link_breaking_load_kn: float | None
    weak_link_breaking_load_t: float | None
    weak_link_value_label: str | None
    components: tuple[ComponentStrength, ...]
    diagnostic: str

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID" and self.weak_link_breaking_load_kn is not None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "weak_link_component_id": self.weak_link_component_id,
            "weak_link_component_type": self.weak_link_component_type,
            "weak_link_certificate_id": self.weak_link_certificate_id,
            "weak_link_breaking_load_kn": self.weak_link_breaking_load_kn,
            "weak_link_breaking_load_t": self.weak_link_breaking_load_t,
            "weak_link_value_label": self.weak_link_value_label,
            "components": [
                {
                    "component_id": c.component_id,
                    "component_type": c.component_type,
                    "certificate_id": c.certificate_id,
                    "governing_breaking_load_kn": c.governing_breaking_load_kn,
                    "governing_breaking_load_label": c.governing_breaking_load_label,
                    "breaking_loads": [asdict(v) for v in c.breaking_loads],
                }
                for c in self.components
            ],
            "diagnostic": self.diagnostic,
        }


def _component_from_dict(data: dict) -> ComponentStrength:
    loads = []
    for item in data.get("breaking_loads", ()):
        value = float(item.get("value_kn", 0.0))
        if value > 0:
            loads.append(
                BreakingLoadValue(
                    value_kn=value,
                    label=str(item.get("label", "BREAKING LOAD")).strip(),
                    source=str(item.get("source", "CERTIFICATE")).strip(),
                )
            )
    return ComponentStrength(
        component_id=str(data.get("component_id", "UNKNOWN")).strip(),
        component_type=str(data.get("component_type", "UNKNOWN")).strip(),
        certificate_id=(str(data["certificate_id"]).strip() if data.get("certificate_id") else None),
        breaking_loads=tuple(loads),
    )


def evaluate_weak_link(components: Iterable[ComponentStrength | dict]) -> WeakLinkResult:
    """Return the lowest declared applicable breaking load in the assembly.

    The function works for a single MAIN LINE as well as a composite assembly.
    A component without a usable breaking-load value makes the result
    ``INCOMPLETE`` rather than silently assuming a strength.
    """
    normalized = tuple(
        c if isinstance(c, ComponentStrength) else _component_from_dict(c)
        for c in components
    )
    if not normalized:
        return WeakLinkResult(
            status="INCOMPLETE",
            weak_link_component_id=None,
            weak_link_component_type=None,
            weak_link_certificate_id=None,
            weak_link_breaking_load_kn=None,
            weak_link_breaking_load_t=None,
            weak_link_value_label=None,
            components=(),
            diagnostic="No mooring-line components were supplied.",
        )

    missing = [c.component_id for c in normalized if c.governing_breaking_load_kn is None]
    if missing:
        return WeakLinkResult(
            status="INCOMPLETE",
            weak_link_component_id=None,
            weak_link_component_type=None,
            weak_link_certificate_id=None,
            weak_link_breaking_load_kn=None,
            weak_link_breaking_load_t=None,
            weak_link_value_label=None,
            components=normalized,
            diagnostic=(
                "Breaking-load data are missing for component(s): "
                + ", ".join(missing)
                + ". The assembly cannot be assigned a governing weak link."
            ),
        )

    weak = min(normalized, key=lambda c: c.governing_breaking_load_kn or float("inf"))
    value_kn = weak.governing_breaking_load_kn
    return WeakLinkResult(
        status="VALID",
        weak_link_component_id=weak.component_id,
        weak_link_component_type=weak.component_type,
        weak_link_certificate_id=weak.certificate_id,
        weak_link_breaking_load_kn=value_kn,
        weak_link_breaking_load_t=value_kn / 9.80665 if value_kn is not None else None,
        weak_link_value_label=weak.governing_breaking_load_label,
        components=normalized,
        diagnostic=(
            f"Governing weak link is {weak.component_id} ({weak.component_type}) "
            f"at {value_kn:.2f} kN, based on the lowest declared breaking-load value."
        ),
    )


def component_from_certificate(
    *,
    component_id: str,
    component_type: str,
    certificate_id: str | None,
    break_load_linear_kn: float | None = None,
    break_load_spliced_kn: float | None = None,
    break_load_grommet_kn: float | None = None,
) -> ComponentStrength:
    """Build a component strength record from explicitly named certificate fields."""
    values = []
    for value, label in (
        (break_load_linear_kn, "Break load linear"),
        (break_load_spliced_kn, "Break load spliced"),
        (break_load_grommet_kn, "Break load grommet"),
    ):
        if value is not None and float(value) > 0:
            values.append(BreakingLoadValue(float(value), label))
    return ComponentStrength(
        component_id=component_id,
        component_type=component_type,
        certificate_id=certificate_id,
        breaking_loads=tuple(values),
    )
