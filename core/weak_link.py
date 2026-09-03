"""Weak-link evaluation for composite mooring lines.

The certificate may contain several breaking-load values for the same
component (linear, spliced, grommet). We select the value applicable to the
physical configuration, rather than blindly taking the smallest number.

For the Panorama mooring arrangement the onboard tail application is treated
as a default ``LOOP_AROUND_BOLLARD``. For an endless-spliced GeoSquare Plus
loop, this corresponds to the manufacturer's grommet configuration when the
certificate provides a grommet breaking-load value.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable
import re

ONBOARD_TAIL_APPLICATION = "LOOP_AROUND_BOLLARD"

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
    applicable_load_label: str | None = None
    onboard_application: str | None = None

    @property
    def applicable_breaking_load(self) -> BreakingLoadValue | None:
        if not self.applicable_load_label:
            return None
        wanted = self.applicable_load_label.strip().lower()
        return next((x for x in self.breaking_loads if x.label.strip().lower() == wanted), None)

    @property
    def governing_breaking_load_kn(self) -> float | None:
        value = self.applicable_breaking_load
        return value.value_kn if value and value.value_kn > 0 else None

    @property
    def governing_breaking_load_label(self) -> str | None:
        value = self.applicable_breaking_load
        return value.label if value else None

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
                    "applicable_load_label": c.applicable_load_label,
                    "onboard_application": c.onboard_application,
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
            loads.append(BreakingLoadValue(value, str(item.get("label", "BREAKING LOAD")).strip(), str(item.get("source", "CERTIFICATE")).strip()))
    return ComponentStrength(
        component_id=str(data.get("component_id", "UNKNOWN")).strip(),
        component_type=str(data.get("component_type", "UNKNOWN")).strip(),
        certificate_id=(str(data["certificate_id"]).strip() if data.get("certificate_id") else None),
        breaking_loads=tuple(loads),
        applicable_load_label=(str(data["applicable_load_label"]).strip() if data.get("applicable_load_label") else None),
        onboard_application=(str(data["onboard_application"]).strip() if data.get("onboard_application") else None),
    )

def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())

def infer_applicable_load_label(*, component_type: str, final_presentation: str = "", onboard_application: str | None = None) -> str | None:
    """Infer the applicable certificate value from physical configuration.

    Panorama default: every TAIL is used as a loop around the bollard. For a
    Gleistein endless-spliced loop, the manufacturer's grommet value is the
    applicable configuration value. Main/auxiliary components explicitly
    presented as spliced use their spliced value.
    """
    ctype = _normalize_text(component_type)
    presentation = _normalize_text(final_presentation)
    application = _normalize_text(onboard_application)
    if "tail" in ctype and not application:
        application = _normalize_text(ONBOARD_TAIL_APPLICATION)
    if "loop_around_bollard" in application or "loop around bollard" in application:
        return "Break load grommet"
    if "splice" in presentation:
        return "Break load spliced"
    if "linear" in presentation and "splice" not in presentation:
        return "Break load linear"
    return None

def evaluate_weak_link(components: Iterable[ComponentStrength | dict]) -> WeakLinkResult:
    """Return the lowest *applicable* declared breaking load in the assembly."""
    normalized = tuple(c if isinstance(c, ComponentStrength) else _component_from_dict(c) for c in components)
    if not normalized:
        return WeakLinkResult("INCOMPLETE", None, None, None, None, None, None, (), "No mooring-line components were supplied.")
    missing = [c.component_id for c in normalized if c.governing_breaking_load_kn is None]
    if missing:
        return WeakLinkResult("INCOMPLETE", None, None, None, None, None, None, normalized, "Applicable breaking-load data are missing for component(s): " + ", ".join(missing) + ". The assembly cannot be assigned a governing weak link.")
    weak = min(normalized, key=lambda c: c.governing_breaking_load_kn or float("inf"))
    value_kn = weak.governing_breaking_load_kn
    return WeakLinkResult(
        "VALID", weak.component_id, weak.component_type, weak.certificate_id,
        value_kn, value_kn / 9.80665 if value_kn is not None else None,
        weak.governing_breaking_load_label, normalized,
        f"Governing weak link is {weak.component_id} ({weak.component_type}) at {value_kn:.2f} kN, using the applicable certificate value for the recorded physical configuration.",
    )

def component_from_certificate(*, component_id: str, component_type: str, certificate_id: str | None,
                                break_load_linear_kn: float | None = None,
                                break_load_spliced_kn: float | None = None,
                                break_load_grommet_kn: float | None = None,
                                final_presentation: str = "",
                                onboard_application: str | None = None,
                                applicable_load_label: str | None = None) -> ComponentStrength:
    """Build a component record and select the applicable certificate value."""
    values = []
    for value, label in ((break_load_linear_kn, "Break load linear"), (break_load_spliced_kn, "Break load spliced"), (break_load_grommet_kn, "Break load grommet")):
        if value is not None and float(value) > 0:
            values.append(BreakingLoadValue(float(value), label))
    selected = applicable_load_label or infer_applicable_load_label(component_type=component_type, final_presentation=final_presentation, onboard_application=onboard_application)
    return ComponentStrength(
        component_id=component_id, component_type=component_type, certificate_id=certificate_id,
        breaking_loads=tuple(values), applicable_load_label=selected.strip() if selected else None,
        onboard_application=onboard_application or (ONBOARD_TAIL_APPLICATION if "tail" in _normalize_text(component_type) else None),
    )
