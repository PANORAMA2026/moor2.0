import pytest

from domain import Environment, MooringLine, Ship
from validation import InputValidationError
from validation import (
    validate_environment,
    validate_mooring_line,
    validate_ship,
)


def test_valid_ship_passes():
    validate_ship(Ship(name="Test", loa_m=100.0, beam_m=20.0))


def test_invalid_ship_raises():
    with pytest.raises(InputValidationError):
        validate_ship(Ship(name="Test", loa_m=0.0, beam_m=20.0))


def test_invalid_line_mbl_raises():
    line = MooringLine(
        line_id="L1",
        line_name="Line 1",
        material="Polyester",
        mbl_tons=0.0,
        main_length_m=100.0,
    )
    with pytest.raises(InputValidationError):
        validate_mooring_line(line)


def test_invalid_tail_mbl_raises():
    line = MooringLine(
        line_id="L1",
        line_name="Line 1",
        material="Polyester",
        mbl_tons=100.0,
        main_length_m=100.0,
        tail_mbl_tons=0.0,
    )
    with pytest.raises(InputValidationError):
        validate_mooring_line(line)


def test_invalid_environment_direction_raises():
    with pytest.raises(InputValidationError):
        validate_environment(Environment(wind_direction_deg=360.0))
