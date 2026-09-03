from core.gleistein_parser import parse_gleistein_pages

def test_gleistein_main_tail_geolink_weak_link():
    pages=[
        'Certificate no.: W225-6918\nShip name: CARNIVAL PANORAMA\nIMO no.: 9802384\nOrder no.: V-AU25-2715 / G23625100178\nItem No. client / Gleistein: MAIN LINE / 6FT0540120\nItem description: FlexTwin 54 mm Ø, 120 ton\nFinal presentation: spliced both ends\nRaw material: Dyneema SK78\nDelivered quantity\n1 190,00 50045321',
        'Certificate no.: W225-6918\nBreak load linear [kN] 1.220,78\nBreak load spliced [kN] 1.098,70\nWeight [kg/100m] 160,4',
        'Certificate no.: W225-6919\nItem No. client / Gleistein: TAIL / 355600999x01\nItem description: GeoSquare Plus Loop, 60 mm\nFinal presentation: endless spliced\nRaw material: PP/PE Bipo PES\nDelivered quantity\n1 11,00 50045238',
        'Certificate no.: W225-6919\nBreak load spliced [kN] 629,00\nBreak load grommet [kN] 1.006,40\nWeight [kg/STCK] 42,5',
        'Certificate no.: W2Z25-6920\nItem No. client / Gleistein: LASHING / 663260992\nItem description: GeoLink Lashing with PES-Cover 26 mm Ø\nFinal presentation: spliced one end\nRaw material: Dyneema SK78\nDelivered quantity\n1 1,00 50045131',
        'Certificate no.: W225-6920\nBreak load spliced [kN] 1.073,30\nWeight [kg/100m] 124',
    ]
    result=parse_gleistein_pages(pages)
    assert len(result['components'])==3
    assert result['weak_link']['status']=='VALID'
    assert result['weak_link']['weak_link_component_id']=='355600999x01'
    assert result['weak_link']['weak_link_breaking_load_kn']==629.00
    assert result['weak_link']['weak_link_breaking_load_t']>64.0
