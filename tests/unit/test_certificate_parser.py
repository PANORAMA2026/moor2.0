import pytest
from pathlib import Path

from core.certificate_parser import parse_certificate_text, validate_extraction


def test_extracts_line_certificate_fields():
    text = """
    Ship Design MBL 900 t
    Line Design Break Force (LDBF): 1000 kN
    Diameter: 44 mm
    Length: 220 m
    Average Immediate Strain at 10% LDBF: 0.42 %
    Average Immediate Strain at 20% LDBF: 0.85 %
    Average Immediate Strain at 30% LDBF: 1.31 %
    """
    result = parse_certificate_text(text)
    assert result.get("ldbf") == 1000
    assert result.get("diameter_mm") == 44
    assert result.get("length_m") == 220
    assert result.get("average_immediate_strain_10_pct_ldbf") == pytest.approx(0.42)
    assert not validate_extraction(result)


def test_conflicting_duplicate_is_not_accepted():
    # Text parser sees multiple matches and reports ambiguity rather than
    # selecting an arbitrary engineering value.
    result = parse_certificate_text("LDBF 1000 kN\nLDBF 1100 kN")
    assert result.get("ldbf") is None
    assert any("Ambiguous extraction" in w for w in result.warnings)


def test_tail_certificate_uses_tdbf():
    result = parse_certificate_text("Tail Design Break Force (TDBF): 800 kN", "MOORING_TAIL")
    assert result.get("tail_design_break_force") == 800
    assert not validate_extraction(result)
