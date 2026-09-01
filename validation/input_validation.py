"""Validation functions for canonical engineering domain models."""

from __future__ import annotations

from domain.models import Environment, MooringLine, Ship
from .exceptions import InputValidationError


def validate_ship(ship: Ship) -> None:
    if not ship.name.strip():
        raise InputValidationError("Ship name is required.")
    if ship.loa_m <= 0:
        raise InputValidationError("Ship LOA must be greater than zero.")
    if ship.beam_m <= 0:
        raise InputValidationError("Ship beam must be greater than zero.")

    for field_name, value in (
        ("frontal_windage_area_m2", ship.frontal_windage_area_m2),
        ("lateral_windage_area_m2", ship.lateral_windage_area_m2),
        ("lateral_current_area_m2", ship.lateral_current_area_m2),
    ):
        if value is not None and value < 0:
            raise InputValidationError(f"{field_name} cannot be negative.")


def validate_mooring_line(line: MooringLine) -> None:
    if not line.line_id.strip():
        raise InputValidationError("Mooring line ID is required.")
    if line.mbl_tons <= 0:
        raise InputValidationError(
            f"Line {line.line_id}: MBL must be greater than zero."
        )
    if line.main_length_m <= 0:
        raise InputValidationError(
            f"Line {line.line_id}: main length must be greater than zero."
        )
    if line.tail_length_m < 0:
        raise InputValidationError(
            f"Line {line.line_id}: tail length cannot be negative."
        )
    if line.tail_mbl_tons is not None and line.tail_mbl_tons <= 0:
        raise InputValidationError(
            f"Line {line.line_id}: tail MBL must be greater than zero."
        )
    if not 0 <= line.wear_pct <= 100:
        raise InputValidationError(
            f"Line {line.line_id}: wear percentage must be between 0 and 100."
        )


def validate_environment(environment: Environment) -> None:
    if environment.wind_speed_mps < 0:
        raise InputValidationError("Wind speed cannot be negative.")
    if environment.current_speed_mps < 0:
        raise InputValidationError("Current speed cannot be negative.")

    for field_name, value in (
        ("wind_direction_deg", environment.wind_direction_deg),
        ("current_direction_deg", environment.current_direction_deg),
    ):
        if not 0 <= value < 360:
            raise InputValidationError(
                f"{field_name} must be in the range [0, 360)."
            )
