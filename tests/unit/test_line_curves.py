import pytest

from core.line_curves import curve_from_certificate, curve_from_generic_material


def test_certificate_curve_interpolates_without_extrapolation():
    curve = curve_from_certificate(
        1000.0,
        {10: 0.01, 20: 0.02, 30: 0.035, 40: 0.055, 50: 0.080},
        "TEST_CERTIFICATE.pdf",
    )
    assert curve.certified is True
    assert curve.source == "TEST_CERTIFICATE.pdf"
    assert curve.strain_at_load(200.0) == pytest.approx(0.02)
    assert curve.strain_at_load(250.0) == pytest.approx(0.0275)


def test_certificate_curve_rejects_extrapolation():
    curve = curve_from_certificate(1000.0, {10: 0.01, 20: 0.02, 50: 0.08}, "CERT")
    with pytest.raises(ValueError):
        curve.strain_at_load(50.0)
    with pytest.raises(ValueError):
        curve.strain_at_load(600.0)


def test_generic_curve_is_not_certified():
    curve = curve_from_generic_material("POLYESTER", 1000.0)
    assert curve.certified is False
    assert curve.source == "GENERIC_ENGINEERING_ASSUMPTION"
