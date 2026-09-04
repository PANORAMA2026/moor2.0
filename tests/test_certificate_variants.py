import pytest

from core.certificate_parser import parse_certificate_text
from utils.pdf_parser import parse_certificate_text as parse_normalized


def test_bexco_b11_extracts_physical_id_diameter_length_and_loads():
    text = '''
    BEXCO
    Test report Werkzeugnis
    Customer: GLOBAL MARINE SUPPLIES SPA
    Our ref: VO0004380 / 2
    Product: BEXCOLINE (Combination of Bexcord & Polyester Fibres)
    Diameter : 60mm
    Unique ID-number : P11264
    Min Breaking Load rope : 81,1T = 796,0 kN
    Calculated Breaking Load rope : 83,1T = 815,1 kN
    Order : BexcoFlex - 12 strand
    Quantity : 1x 200m
    '''
    r = parse_normalized(text)
    c = r["components"][0]
    assert c["component_type"] == "MAIN LINE"
    assert c["component_id"] == "P11264"
    assert c["diameter_mm"] == pytest.approx(60)
    assert c["length_m"] == pytest.approx(200)
    assert c["minimum_breaking_load_kn"] == pytest.approx(796.0)
    assert c["calculated_breaking_load_kn"] == pytest.approx(815.1)
    assert c["applicable_break_load_label"] == "Minimum breaking load"
    assert r["weak_link"]["status"] == "NO_WEAK_LINK"


def test_lankhorst_e12_extracts_pic_diameter_length_and_ldbf():
    text = '''
    Lankhorst Ropes
    CERTIFICATE OF ROPES
    Certificate number: 21R123134
    Description: EUROFLOAT PREMIUM 72 MM
    8 STRANDS PLAITED
    CL 220 MTR WITH 2 EYES OF 1.80 MTR
    Dimension: Nominal diameter (mm) 72MM
    Length (mtr) 1x 220
    Product Identification Code (PIC) 59576-5
    Strength: Minimum breaking load (MBL) acc. ISO.2307 1000 KN
    Spliced - Line/Tail Design Break Force (LDBF / TDBF) 900 kN / 91,7 Mt
    '''
    r = parse_normalized(text)
    c = r["components"][0]
    assert c["component_type"] == "MAIN LINE"
    assert c["component_id"] == "59576-5"
    assert c["certificate_id"] == "21R123134"
    assert c["diameter_mm"] == pytest.approx(72)
    assert c["length_m"] == pytest.approx(220)
    assert c["minimum_breaking_load_kn"] == pytest.approx(1000)
    assert c["ldbf_kn"] == pytest.approx(900)
    assert c["applicable_break_load_label"] == "LDBF"
    assert r["weak_link"]["status"] == "NO_WEAK_LINK"


def test_legacy_parser_still_extracts_ldbf_and_strain():
    text = '''
    Ship Design MBL 900 t
    Line Design Break Force (LDBF): 1000 kN
    Diameter: 44 mm
    Length: 220 m
    Average Immediate Strain at 10% LDBF: 0.42 %
    Average Immediate Strain at 20% LDBF: 0.85 %
    Average Immediate Strain at 30% LDBF: 1.31 %
    '''
    result = parse_certificate_text(text)
    assert result.get("ldbf") == 1000
    assert result.get("diameter_mm") == 44
    assert result.get("length_m") == 220
    assert result.get("average_immediate_strain_10_pct_ldbf") == pytest.approx(0.42)
