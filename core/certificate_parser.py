"""Engineering certificate extraction and validation.

PDF parsing is intentionally separated from engineering validation. Extraction
never makes a value 'certified'; every imported field retains provenance and
confidence information.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import re

@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: object
    source_text: str
    confidence: float
    page: Optional[int] = None

@dataclass
class CertificateExtraction:
    certificate_type: str = "UNKNOWN"
    fields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""

    def get(self, name: str):
        for f in self.fields:
            if f.name == name:
                return f.value
        return None

FIELD_PATTERNS = {
    "ship_design_mbl": [r"ship\s+design\s+mbl\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "ldbf": [r"(?:line\s+design\s+break\s+force|ldbf)\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "diameter_mm": [r"diameter\s*[:=]?\s*([\d.,]+)\s*(mm|m)?"],
    "length_m": [r"length\s*[:=]?\s*([\d.,]+)\s*(m|meter|metre|ft)?"],
    "line_linear_density": [r"line\s+linear\s+density\s*[:=]?\s*([\d.,]+)"],
}

STRAIN_RE = re.compile(r"%\s*LDBF\s*[:=]?\s*(10|20|30|40|50)\s*.*?([\d.,]+)", re.I)

def _number(s: str) -> float:
    s = s.strip().replace(",", "")
    return float(s)

def parse_certificate_text(text: str, certificate_type: str = "MOORING_LINE") -> CertificateExtraction:
    """Extract obvious certificate fields from already-extracted PDF text.

    This is deliberately conservative: ambiguous matches are warnings rather
    than silently converted into engineering values.
    """
    result = CertificateExtraction(certificate_type=certificate_type, raw_text=text)
    normalized = re.sub(r"[\t ]+", " ", text)
    for name, patterns in FIELD_PATTERNS.items():
        matches = []
        for pattern in patterns:
            matches.extend(re.finditer(pattern, normalized, re.I))
        if len(matches) == 1:
            m = matches[0]
            result.fields.append(ExtractedField(name, _number(m.group(1)), m.group(0), 0.95))
        elif len(matches) > 1:
            result.warnings.append(f"Ambiguous extraction for {name}: {len(matches)} matches")

    strain_matches = list(STRAIN_RE.finditer(normalized))
    for m in strain_matches:
        pct = int(m.group(1))
        result.fields.append(ExtractedField(f"average_immediate_strain_{pct}_pct_ldbf", _number(m.group(2)), m.group(0), 0.90))
    if not strain_matches:
        result.warnings.append("No Average Immediate Strain table values detected; inspect PDF/table layout.")
    return result

def validate_extraction(extraction: CertificateExtraction) -> list[str]:
    errors = []
    required = {"ldbf", "diameter_mm", "length_m"}
    present = {f.name for f in extraction.fields}
    for name in required - present:
        errors.append(f"Required field not extracted: {name}")
    ldbf = extraction.get("ldbf")
    if ldbf is not None and ldbf <= 0:
        errors.append("LDBF must be greater than zero")
    diameter = extraction.get("diameter_mm")
    if diameter is not None and diameter <= 0:
        errors.append("Diameter must be greater than zero")
    return errors
