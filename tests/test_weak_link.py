from core.weak_link import component_from_certificate, evaluate_weak_link

def test_main_line_uses_lowest_declared_breaking_load():
    main=component_from_certificate(component_id='6FT0540120',component_type='MAIN LINE',certificate_id='W225-6918',break_load_linear_kn=1220.78,break_load_spliced_kn=1098.70)
    result=evaluate_weak_link([main])
    assert result.is_valid
    assert result.weak_link_breaking_load_kn == 1098.70
    assert result.weak_link_value_label == 'Break load spliced'

def test_composite_assembly_selects_tail_as_weak_link():
    main=component_from_certificate(component_id='6FT0540120',component_type='MAIN LINE',certificate_id='W225-6918',break_load_linear_kn=1220.78,break_load_spliced_kn=1098.70)
    tail=component_from_certificate(component_id='355600999x01',component_type='TAIL',certificate_id='W225-6919',break_load_spliced_kn=629.00,break_load_grommet_kn=1006.40)
    geo=component_from_certificate(component_id='663260992',component_type='GEOLINK/LASHING',certificate_id='W225-6920',break_load_spliced_kn=1073.30)
    result=evaluate_weak_link([main,tail,geo])
    assert result.is_valid
    assert result.weak_link_component_id == '355600999x01'
    assert result.weak_link_breaking_load_kn == 629.00
    assert result.weak_link_value_label == 'Break load spliced'

def test_missing_component_strength_does_not_invent_weak_link():
    main=component_from_certificate(component_id='MAIN',component_type='MAIN LINE',certificate_id='CERT',break_load_spliced_kn=1000.0)
    unknown=component_from_certificate(component_id='TAIL',component_type='TAIL',certificate_id='CERT2')
    result=evaluate_weak_link([main,unknown])
    assert result.status == 'INCOMPLETE'
    assert result.weak_link_breaking_load_kn is None
