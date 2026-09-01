from core.units import knots_to_mps, kn_to_tonne_force, tonne_force_to_kn


def test_knot_conversion():
    assert abs(knots_to_mps(1.0) - 0.5144444444444445) < 1e-12


def test_force_round_trip():
    value = 100.0
    assert abs(kn_to_tonne_force(tonne_force_to_kn(value)) - value) < 1e-12
