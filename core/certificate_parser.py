"""Generic, manufacturer-independent extraction of rope certificate facts."""
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
    def get(self,name: str): return next((f.value for f in self.fields if f.name==name),None)
    def field(self,name: str): return next((f for f in self.fields if f.name==name),None)

def _num(s: str) -> float:
    s=re.sub(r"[^0-9,.-]", "", str(s))
    if "," in s and "." in s: s=s.replace(",","") if s.rfind(".")>s.rfind(",") else s.replace(".","").replace(",",".")
    elif "," in s:
        tail=s.rsplit(",",1)[1]; s=s.replace(",","") if len(tail)==3 else s.replace(",",".")
    return float(s)

def _clean(s): return re.sub(r"\s+"," ",str(s or "")).strip(" :\t")
def _add(r,name,value,source,unit=None,confidence=.95):
    if value is not None:r.fields.append(ExtractedField(name,value,_clean(source),confidence,None,unit))
def _first(text,patterns):
    for p in patterns:
        m=re.search(p,text,re.I|re.M|re.S)
        if m:return m.group(1),m.group(0)
    return None,None

def parse_certificate_text(text: str, certificate_type: str="AUTO") -> CertificateExtraction:
    text=text or ""
    if certificate_type=="AUTO": certificate_type="MOORING_TAIL" if re.search(r"\b(?:tail|tdbf)\b",text,re.I) else "MOORING_LINE"
    r=CertificateExtraction(certificate_type=certificate_type,raw_text=text,pages_with_text=1 if text.strip() else 0,total_pages=1 if text.strip() else 0,extraction_method="text")
    aliases={
      "certificate_id":[r"certificate\s*(?:no\.?|number)\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]*)"],
      "component_id":[r"unique\s+id[- ]?number\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",r"product\s+identification\s+code\s*\(\s*PIC\s*\)\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",r"(?:rope|product|item)\s+identification(?:\s+code)?\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",r"(?:serial|unique|rope)\s*(?:no\.?|number|id)\s*[:#=]\s*([A-Z0-9][A-Z0-9._/-]*)"],
      "manufacturer":[r"(?:manufacturer|producer)\s*[:=]\s*([^\n]+)",r"examination\s+performed\s+by\s*[:=]\s*([^\n]+)"],
      "product":[r"product\s*[:=]\s*([^\n]+)",r"description\s*[:=]\s*([^\n]+)"],
      "diameter_mm":[r"(?:nominal\s+)?diam(?:eter)?\s*(?:\(\s*mm\s*\))?\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*mm\b",r"(?:nominal\s+)?diam(?:eter)?[^\n]{0,30}?\b(\d+(?:[.,]\d+)?)\s*mm\b"],
      "length_m":[r"length\s*\(?(?:m|mtr|metres?)\)?\s*[:=]\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m",r"length\s*\(?(?:m|mtr|metres?)\)?\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*m",r"quantity\s*[:=]\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m",r"\bCL\s*(\d+(?:[.,]\d+)?)\s*MTR\b"],
      "minimum_breaking_load_kn":[r"minimum\s+breaking\s+load[^\n]{0,90}?([\d.,]+)\s*kN\b",r"min(?:imum)?\s+breaking\s+load[^\n]{0,40}?([\d.,]+)\s*kN\b"],
      "calculated_breaking_load_kn":[r"calculated\s+breaking\s+load[^\n]{0,90}?([\d.,]+)\s*kN\b"],
      "ldbf_kn":[r"(?:line\s*/\s*tail|line|tail)\s+design\s+break\s+force\s*\(?(?:ldbf|tdbf)[^\n]{0,60}?([\d.,]+)\s*kN\b",r"\bLDBF\b[^\n]{0,35}?([\d.,]+)\s*kN\b"],
      "tdbf_kn":[r"\bTDBF\b[^\n]{0,35}?([\d.,]+)\s*kN\b"],
    }
    for name,patterns in aliases.items():
        value,source=_first(text,patterns)
        if value is None:continue
        if name.endswith("_kn") or name in {"diameter_mm","length_m"}: _add(r,name,_num(value),source,"kN" if name.endswith("_kn") else ("mm" if name=="diameter_mm" else "m"))
        else:_add(r,name,_clean(value),source)
    # Legacy aliases retained for existing callers/tests; the *_kn fields are authoritative for the new engine.
    if r.get("ldbf_kn") is not None:_add(r,"ldbf",r.get("ldbf_kn"),"normalized LDBF","kN")
    if r.get("tdbf_kn") is not None:_add(r,"tail_design_break_force",r.get("tdbf_kn"),"normalized TDBF","kN")
    if r.get("minimum_breaking_load_kn") is not None:_add(r,"minimum_breaking_load",r.get("minimum_breaking_load_kn"),"normalized minimum breaking load","kN")
    if r.get("calculated_breaking_load_kn") is not None:_add(r,"calculated_breaking_load",r.get("calculated_breaking_load_kn"),"normalized calculated breaking load","kN")
    for m in re.finditer(r"(?:average\s+)?(?:immediate\s+)?strain[^\n]*?at\s*(\d+)\s*%\s*(?:ldbf)?[^\n]*?([\d.,]+)\s*%",text,re.I):
        _add(r,f"average_immediate_strain_{m.group(1)}_pct_ldbf",_num(m.group(2)),m.group(0),"%")
    unique={}
    for f in r.fields:
        if f.name not in unique:unique[f.name]=f
        elif unique[f.name].value!=f.value:r.warnings.append(f"Ambiguous extraction for {f.name}: conflicting values {unique[f.name].value!r} and {f.value!r}")
    r.fields=list(unique.values()); return r

def validate_extraction(extraction: CertificateExtraction) -> list[str]:
    if extraction.get("ldbf") is not None or extraction.get("minimum_breaking_load") is not None or extraction.get("tail_design_break_force") is not None: return []
    return ["No declared breaking-load value extracted"]

def extract_pdf_text(pdf_path: str|Path):
    path=Path(pdf_path)
    if not path.exists():raise FileNotFoundError(path)
    import fitz
    with fitz.open(path) as doc:pages=[p.get_text("text") or "" for p in doc]
    return "\n\n".join(pages),sum(bool(p.strip()) for p in pages),len(pages),"pymupdf",[]

def parse_certificate_pdf(pdf_path: str|Path,certificate_type: str="AUTO") -> CertificateExtraction:
    text,n,total,method,warnings=extract_pdf_text(pdf_path); r=parse_certificate_text(text,certificate_type); r.pages_with_text=n; r.total_pages=total; r.extraction_method=method; r.warnings=warnings+r.warnings; return r
