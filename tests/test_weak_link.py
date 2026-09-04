from core.weak_link import component_from_certificate, evaluate_weak_link


def test_single_main_line_has_breaking_capacity_but_no_weak_link():
    main = component_from_certificate(
        component_id="6FT0540120", component_type="MAIN LINE", certificate_id="W225-6918",
        break_load_linear_kn=1220.78, break_load_spliced_kn=1098.70,
        final_presentation="spliced both ends",
    )
    result = evaluate_weak_link([main])
    assert result.status == "NO_WEAK_LINK"
    assert not result.has_weak_link
    assert result.weak_link_component_id is None
    assert result.weak_link_breaking_load_kn == 1098.70
    assert result.weak_link_value_label == "Break load spliced"


def test_tail_loop_around_bollard_uses_grommet_value():
    tail = component_from_certificate(
        component_id="355600999x01", component_type="TAIL", certificate_id="W225-6919",
        break_load_spliced_kn=629.00, break_load_grommet_kn=1006.40,
        final_presentation="endless spliced",
    )
    result = evaluate_weak_link([tail])
    assert result.status == "NO_WEAK_LINK"
    assert tail.onboard_application == "LOOP_AROUND_BOLLARD"
    assert tail.applicable_load_label == "Break load grommet"
    assert result.weak_link_breaking_load_kn == 1006.40
    assert result.weak_link_value_label == "Break load grommet"


def test_composite_assembly_selects_tail_grommet_as_weak_link_after_all_components():
    main = component_from_certificate(
        component_id="6FT0540120", component_type="MAIN LINE", certificate_id="W225-6918",
        break_load_linear_kn=1220.78, break_load_spliced_kn=1098.70,
        final_presentation="spliced both ends",
    )
    tail = component_from_certificate(
        component_id="355600999x01", component_type="TAIL", certificate_id="W225-6919",
        break_load_spliced_kn=629.00, break_load_grommet_kn=1006.40,
        final_presentation="endless spliced",
    )
    geo = component_from_certificate(
        component_id="663260992", component_type="GEOLINK/LASHING", certificate_id="W225-6920",
        break_load_spliced_kn=1073.30, final_presentation="spliced one end",
    )
    result = evaluate_weak_link([main, tail, geo])
    assert result.status == "VALID"
    assert result.has_weak_link
    assert result.weak_link_component_id == "355600999x01"
    assert result.weak_link_breaking_load_kn == 1006.40
    assert result.weak_link_value_label == "Break load grommet"


def test_missing_component_strength_does_not_invent_weak_link():
    main = component_from_certificate(
        component_id="MAIN", component_type="MAIN LINE", certificate_id="CERT",
        break_load_spliced_kn=1000.0, final_presentation="spliced both ends",
    )
    unknown = component_from_certificate(component_id="TAIL", component_type="TAIL", certificate_id="CERT2")
    result = evaluate_weak_link([main, unknown])
    assert result.status == "INCOMPLETE"
    assert result.weak_link_breaking_load_kn is None
