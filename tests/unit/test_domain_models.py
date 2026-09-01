from domain import Environment, MooringLine, Ship


def test_ship_model():
    ship = Ship(name="Test Ship", loa_m=100.0, beam_m=20.0)
    assert ship.name == "Test Ship"
    assert ship.loa_m == 100.0


def test_mooring_line_tail_properties_are_explicit():
    line = MooringLine(
        line_id="L1",
        line_name="Head Line 1",
        material="Polyester",
        mbl_tons=100.0,
        main_length_m=120.0,
        tail_material="Nylon",
        tail_mbl_tons=80.0,
        tail_length_m=10.0,
    )
    assert line.tail_mbl_tons == 80.0
    assert line.tail_length_m == 10.0


def test_environment_defaults():
    environment = Environment()
    assert environment.wind_speed_mps == 0.0
    assert environment.current_speed_mps == 0.0
