"""Generic, manufacturer-independent extraction of rope certificate facts."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

@dataclass(frozen=True)
class ExtractedField:
    name: str; value: object; source_text: str; confidence: float; page: Optional[int] = None; unit: Optional[str] = None

@dataclass
class CertificateExtraction:
    certificate_type: str = "UNKNOWN"
    fields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    pages_with_text: int = 0
    total_pages: int = 0
    extraction_method: str = "none"
    def get(self,name): return next((f.value for f in self.fields if f.name==name),None)
    def field(self,name): return next((f for f in self.fields if f.name==name),None)

def _num(s):
    s=re.sub(r"[^0-9,.-]","",str(s))
    if not s: raise ValueError("No numeric value")
    if "," in s and "." in s: s=s.replace(",","") if s.rfind(".")>s.rfind(",") else s.replace(".","").replace(",",".")
    elif "," in s: s=s.replace(",","") if len(s.rsplit(",",1)[1])==3 else s.replace(",",".")
    return float(s)

def _clean(s): return re.sub(r"\s+"," ",str(s or "")).strip(" :\t-")
def _add(r,name,value,source,unit=None,confidence=.95):
    if value is not None: r.fields.append(ExtractedField(name,value,_clean(source),confidence,None,unit))
def _first(text,patterns):
    for p in patterns:
        m=re.search(p,text,re.I|re.M|re.S)
        if m:return m.group(1),m.group(0)
    return None,None

def parse_certificate_text(text: str, certificate_type: str="AUTO"):
    text=text or ""
    if certificate_type=="AUTO": certificate_type="MOORING_LINE"
    r=CertificateExtraction(certificate_type=certificate_type,raw_text=text,pages_with_text=1 if text.strip() else 0,total_pages=1 if text.strip() else 0,extraction_method="text")
    aliases={
      "certificate_id":[
          r"certificate\s*(?:no\.?|number)\s*[:#=]?\s*([A-Z0-9][A-Z0-9./_-]*)",
          r"our\s+ref(?:erence)?\s*[:=]\s*([A-Z0-9][A-Z0-9./_-]*(?:\s*/\s*\d+)?)",
          r"report\s+(?:no\.?|number)\s*[:#=]\s*([A-Z0-9][A-Z0-9./_-]*)"
      ],
      "component_id":[
          r"product\s+identification\s+code\s*\(\s*PIC\s*\)\s*[:=\-]?\s*([A-Z0-9][A-Z0-9._/-]*)",
          r"\bPIC\s*[:=\-]?\s*([A-Z0-9][A-Z0-9._/-]*)",
          r"unique\s+id[- ]?number\s*[:=\-]\s*([A-Z0-9][A-Z0-9._/-]*)",
          r"(?:rope|product|item)\s+identification(?:\s+code)?\s*[:=\-]\s*([A-Z0-9][A-Z0-9._/-]*)",
          r"(?:serial|unique|rope)\s*(?:no\.?|number|id)\s*[:#=\-]\s*([A-Z0-9][A-Z0-9._/-]*)"
      ],
      "manufacturer":[r"(?:manufacturer|producer)\s*[:=\-]\s*([^\n]+)",r"examination\s+performed\s+by\s*[:=\-]\s*([^\n]+)"],
      "product":[
          r"product\s*[:=\-]\s*([^\n]+)",
          r"description\s*[:=\-]\s*([^\n]+)",
          r"product\s+(?:name|type)\s*[:=\-]\s*([^\n]+)"
      ],
      "diameter_mm":[
          r"(?:nominal\s+)?diam(?:eter)?\s*(?:\(\s*mm\s*\))?\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*mm\b",
          r"(?:nominal\s+)?diam(?:eter)?[^\n]{0,80}?\b(\d+(?:[.,]\d+)?)\s*mm\b",
          r"\b(?:DIA|Ø)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*mm\b"
      ],
      "length_m":[
          r"length\s*(?:\([^)]*m[^)]*\))?\s*[:=\-]?\s*(?:\d+\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*m\b",
          r"delivered\s+quantity[^\n]{0,80}?\n\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m\b",
          r"quantity\s*[:=\-]?\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m\b",
          r"\bCL\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*M(?:TR|ETER|ETERS)?\b",
          r"\b(\d+(?:[.,]\d+)?)\s*m\s*(?:long|length)\b"
      ],
      "minimum_breaking_load_kn":[
          r"(?:minimum|min)\s+breaking\s+load[^\n]{0,120}?([\d.,]+)\s*kN\b",
          # Certificate tables frequently put the value on the next line.
          r"\bMBL\b(?:\s*\([^)]*\))?[\s\S]{0,120}?([\d.,]+)\s*kN\b",
          r"\b(?:minimum\s+)?breaking\s+load\s*\(?\s*MBL\s*\)?[\s\S]{0,120}?([\d.,]+)\s*kN\b"
      ],
      "calculated_breaking_load_kn":[r"calculated\s+breaking\s+load[^\n]{0,90}?([\d.,]+)\s*kN\b"],
      "ldbf_kn":[
          r"(?:line\s*/\s*tail|line|tail)\s+design\s+break\s+force\s*\(?(?:ldbf|tdbf)\)?[\s\S]{0,120}?([\d.,]+)\s*kN\b",
          r"\bLDBF(?:\s*/\s*TDBF)?\b[\s\S]{0,120}?([\d.,]+)\s*kN\b",
          r"\bTDBF(?:\s*/\s*LDBF)?\b[\s\S]{0,120}?([\d.,]+)\s*kN\b"
      ],
      "tdbf_kn":[
          r"\bTDBF\b[\s\S]{0,120}?([\d.,]+)\s*kN\b",
          r"\bLDBF\s*/\s*TDBF\b[\s\S]{0,120}?([\d.,]+)\s*kN\b"
      ],
    }
    for name,patterns in aliases.items():
        value,source=_first(text,patterns)
        if value is None: continue
        if name.endswith("_kn") or name in {"diameter_mm","length_m"}:
            try:_add(r,name,_num(value),source,"kN" if name.endswith("_kn") else ("mm" if name=="diameter_mm" else "m"))
            except ValueError:r.warnings.append(f"Unable to parse numeric field {name}: {source!r}")
        else:_add(r,name,_clean(value),source)

    pair=re.search(r"\bLDBF\s*/\s*TDBF\b[\s\S]{0,120}?([\d.,]+)\s*kN\b",text,re.I)
    if pair:
        try:
            paired=_num(pair.group(1))
            if r.get("ldbf_kn") is None:_add(r,"ldbf_kn",paired,pair.group(0),"kN")
            if r.get("tdbf_kn") is None:_add(r,"tdbf_kn",paired,pair.group(0),"kN")
        except ValueError:pass

    ldbf_matches=[]
    for m in re.finditer(r"\bLDBF\b[\s\S]{0,120}?([\d.,]+)\s*kN\b",text,re.I):
        try:ldbf_matches.append(_num(m.group(1)))
        except ValueError:pass
    if len(set(ldbf_matches))>1:
        r.fields=[f for f in r.fields if f.name not in {"ldbf_kn","ldbf"}]
        r.warnings.append(f"Ambiguous extraction for ldbf: conflicting values {ldbf_matches}")
    if r.get("ldbf_kn") is not None:_add(r,"ldbf",r.get("ldbf_kn"),"normalized LDBF","kN")
    if r.get("tdbf_kn") is not None:_add(r,"tail_design_break_force",r.get("tdbf_kn"),"normalized TDBF","kN")
    if r.get("minimum_breaking_load_kn") is not None:_add(r,"minimum_breaking_load",r.get("minimum_breaking_load_kn"),"normalized minimum breaking load","kN")
    if r.get("calculated_breaking_load_kn") is not None:_add(r,"calculated_breaking_load",r.get("calculated_breaking_load_kn"),"normalized calculated breaking load","kN")
    strain_pattern=re.compile(r"(?:average\s+)?(?:immediate\s+)?strain[^\n]*?\b(\d+)\s*%\s*(?:ldbf)?[^\n]*?([\d.,]+)\s*%",re.I)
    for m in strain_pattern.finditer(text):
        try:_add(r,f"average_immediate_strain_{m.group(1)}_pct_ldbf",_num(m.group(2)),m.group(0),"%")
        except ValueError:pass
    unique={}
    for f in r.fields:
        if f.name not in unique:unique[f.name]=f
        elif unique[f.name].value!=f.value:r.warnings.append(f"Ambiguous extraction for {f.name}: conflicting values {unique[f.name].value!r} and {f.value!r}")
    r.fields=list(unique.values());return r

def validate_extraction(extraction):
    return [] if (extraction.get("ldbf") is not None or extraction.get("minimum_breaking_load") is not None or extraction.get("tail_design_break_force") is not None) else ["No declared breaking-load value extracted"]

def extract_pdf_text(pdf_path):
    path=Path(pdf_path)
    if not path.exists():raise FileNotFoundError(path)
    import fitz
    with fitz.open(path) as doc:pages=[p.get_text("text") or "" for p in doc]
    return "\n\n".join(pages),sum(bool(p.strip()) for p in pages),len(pages),"pymupdf",[]

def parse_certificate_pdf(pdf_path,certificate_type="AUTO"):
    text,n,total,method,warnings=extract_pdf_text(pdf_path);r=parse_certificate_text(text,certificate_type);r.pages_with_text=n;r.total_pages=total;r.extraction_method=method;r.warnings=warnings+r.warnings;return r
