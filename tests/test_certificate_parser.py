from core.certificate_parser import parse_certificate_text


def test_e12_tabular_certificate_extracts_pic_mbl_and_ldbf():
    text = """Certificate No: 21R123134
Manufacturer: LANKHORST ROPES
Product: EUROFLOAT PREMIUM 72 MM
Product Identification Code (PIC): 59576-5
Diameter: 72 mm
Delivered quantity:
1 x 220 m
CL 220 m with 2 eyes 1.80 m
84% polyolefin / 16% polyester
MBL (ISO2307):
1000 kN
Spliced Line/Tail Design Break Force LDBF/TDBF:
900 kN / 91.7 Mt
"""
    result = parse_certificate_text(text)

    assert result.get("certificate_id") == "21R123134"
    assert result.get("component_id") == "59576-5"
    assert result.get("manufacturer") == "LANKHORST ROPES"
    assert result.get("product") == "EUROFLOAT PREMIUM 72 MM"
    assert result.get("diameter_mm") == 72.0
    assert result.get("length_m") == 220.0
    assert result.get("minimum_breaking_load_kn") == 1000.0
    assert result.get("ldbf_kn") == 900.0
    assert result.get("tdbf_kn") == 900.0


def test_mbl_and_ldbf_can_be_on_separate_lines():
    text = """Product Identification Code (PIC)
59576-5
MBL (ISO2307)
1000 kN
LDBF/TDBF
900 kN / 91.7 Mt
"""
    result = parse_certificate_text(text)
    assert result.get("component_id") == "59576-5"
    assert result.get("minimum_breaking_load_kn") == 1000.0
    assert result.get("ldbf_kn") == 900.0
    assert result.get("tdbf_kn") == 900.0
