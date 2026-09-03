from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: object
    source_text: str
    confidence: float
    page: Optional[int] = None
    unit: Optional[str] = None

@dataclass
class CertificateExtraction:
    certificate_type: str = "UNKNOWN"
    fields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    pages_with_text: int = 0
    total_pages: int = 0
    extraction_method: str = "none"
    def get(self, name: str):
        return next((f.value for f in self.fields if f.name == name), None)

# Keep the legacy parser compatible with common MEG4 certificate wording,
# including labels such as "Line Design Break Force (LDBF): ..." and
# "Tail Design Break Force (TDBF): ...". The LDBF/TDBF patterns are anchored
# to the start of a line so references such as "10% LDBF" in strain tables are
# not mistaken for the declared break-force field.
FIELD_PATTERNS = {
    "ship_design_mbl": [r"ship\s+design\s+mbl\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "ldbf": [r"(?:^|\n)\s*(?:line\s+design\s+break\s+force\s*(?:\(\s*ldbf\s*\))?|ldbf)\s*[:=]\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "diameter_mm": [r"(?:rope\s+)?diam(?:eter)?\s*[:=]?\s*([\d.,]+)\s*mm\b"],
    "length_m": [r"length\s*[:=]?\s*([\d.,]+)\s*(m|meter|metre|ft)\b", r"quantity\s*[:=]?\s*\d+\s*x\s*([\d.,]+)\s*m\b"],
    "line_linear_density": [r"line\s+linear\s+density\s*[:=]?\s*([\d.,]+)\s*(kg/m|kg/m2)?"],
    "tail_design_break_force": [r"(?:^|\n)\s*(?:tail\s+design\s+break\s+force\s*(?:\(\s*tdbf\s*\))?|tdbf)\s*[:=]\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "tail_linear_density": [r"tail\s+linear\s+density\s*[:=]?\s*([\d.,]+)"],
    "minimum_breaking_load": [r"(?:minimum|min\.?)\s+breaking\s+load(?:\s+(?:of|for))?(?:\s+rope)?\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)\b", r"\bmbl\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)\b"],
    "calculated_breaking_load": [r"calculated\s+breaking\s+load(?:\s+rope)?\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)\b"],
}

def _number(s: str) -> float:
    v=s.strip().replace(' ','')
    if ',' in v and '.' in v: v=v.replace('.','').replace(',','.') if v.rfind(',')>v.rfind('.') else v.replace(',','')
    elif ',' in v: v=v.replace(',','.')
    return float(v)

def _extract_from_text(text: str, page: int|None=None, certificate_type: str='MOORING_LINE') -> CertificateExtraction:
    r=CertificateExtraction(certificate_type=certificate_type, raw_text=text)
    normalized=re.sub(r'[\t ]+',' ',text)
    for name,patterns in FIELD_PATTERNS.items():
        matches=[]
        for p in patterns: matches += list(re.finditer(p,normalized,re.I|re.M))
        if not matches: continue
        vals={_number(m.group(1)) for m in matches}
        if len(vals)!=1:
            r.warnings.append(f'Ambiguous extraction for {name}: {len(matches)} conflicting matches'); continue
        m=matches[0]; unit=m.group(2) if m.lastindex and m.lastindex>=2 else None
        r.fields.append(ExtractedField(name,_number(m.group(1)),m.group(0),0.95,page,unit))
    if r.get('calculated_breaking_load') is not None and r.get('ldbf') is None:
        r.warnings.append('Calculated Breaking Load found, but it is not labelled LDBF; LDBF left blank.')
    return r

def parse_certificate_text(text: str, certificate_type: str='MOORING_LINE') -> CertificateExtraction:
    return _extract_from_text(text,None,certificate_type)

def extract_pdf_text(pdf_path: str|Path) -> tuple[str,int,int,str,list[str]]:
    path=Path(pdf_path)
    if not path.exists(): raise FileNotFoundError(path)
    warnings=[]
    try:
        import fitz
        with fitz.open(path) as doc: pages=[p.get_text('text') or '' for p in doc]
        text='\n\n'.join(pages); n=sum(bool(p.strip()) for p in pages)
        if n: return text,n,len(pages),'pymupdf',warnings
    except Exception as exc: warnings.append(f'PyMuPDF extraction failed: {exc}')
    try:
        from pypdf import PdfReader
        pages=[p.extract_text() or '' for p in PdfReader(str(path)).pages]
        text='\n\n'.join(pages); n=sum(bool(p.strip()) for p in pages)
        if n: return text,n,len(pages),'pypdf',warnings
        warnings.append('PDF appears image-only; OCR is required.')
        return text,0,len(pages),'none',warnings
    except Exception as exc: raise RuntimeError('Unable to extract PDF text.') from exc

def parse_certificate_pdf(pdf_path: str|Path, certificate_type: str='AUTO') -> CertificateExtraction:
    text,n,total,method,warnings=extract_pdf_text(pdf_path)
    if certificate_type=='AUTO': certificate_type='MOORING_TAIL' if re.search(r'\b(?:tail design break force|tdbf)\b',text,re.I) else 'MOORING_LINE'
    r=CertificateExtraction(certificate_type=certificate_type,raw_text=text,pages_with_text=n,total_pages=total,extraction_method=method,warnings=warnings)
    if not text.strip(): r.warnings.append('No machine-readable PDF text; OCR/manual review required.'); return r
    try:
        import fitz
        with fitz.open(pdf_path) as doc: page_texts=[p.get_text('text') or '' for p in doc]
    except Exception: page_texts=text.split('\n\n')
    for i,p in enumerate(page_texts,1):
        if p.strip():
            x=_extract_from_text(p,i,certificate_type); r.fields.extend(x.fields); r.warnings.extend(x.warnings)
    unique={}
    for f in r.fields:
        if f.name not in unique: unique[f.name]=f
        elif unique[f.name].value != f.value: r.warnings.append(f'Ambiguous extraction for {f.name}: conflicting page values')
    r.fields=list(unique.values()); return r

def validate_extraction(extraction: CertificateExtraction) -> list[str]:
    errors=[]; present={f.name for f in extraction.fields}
    required={'tail_design_break_force'} if extraction.certificate_type=='MOORING_TAIL' else {'minimum_breaking_load','diameter_mm','length_m'}
    for name in required-present: errors.append(f'Required field not extracted: {name}')
    for name in ('ship_design_mbl','ldbf','minimum_breaking_load','calculated_breaking_load','tail_design_break_force','diameter_mm','length_m'):
        v=extraction.get(name)
        if v is not None and v<=0: errors.append(f'{name} must be greater than zero')
    return errors
