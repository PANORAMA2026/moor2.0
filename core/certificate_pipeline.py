"""Safe application boundary for certificate import.

The pipeline deliberately separates extraction from acceptance. A certificate
must pass validation and ambiguity checks before application code can consume
it as an engineering input.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.certificate_parser import CertificateExtraction, parse_certificate_pdf, validate_extraction


@dataclass(frozen=True)
class CertificateReview:
    extraction: CertificateExtraction
    errors: tuple[str, ...]
    accepted: bool


def review_certificate_pdf(pdf_path: str | Path, certificate_type: str = "AUTO") -> CertificateReview:
    """Extract and validate a certificate without modifying application data."""
    extraction = parse_certificate_pdf(pdf_path, certificate_type)
    errors = tuple(validate_extraction(extraction))
    ambiguous = any("Ambiguous extraction" in warning for warning in extraction.warnings)
    accepted = not errors and not ambiguous and bool(extraction.fields)
    return CertificateReview(extraction=extraction, errors=errors, accepted=accepted)


def accepted_field_map(review: CertificateReview) -> dict[str, object]:
    """Return engineering values only after an explicit successful review."""
    if not review.accepted:
        raise ValueError("Certificate has not passed extraction review.")
    return {field.name: field.value for field in review.extraction.fields}
