"""Robust extractor for Gleistein multi-component rope certificates.

This is a source adapter only. Engineering capacity/weak-link logic remains
manufacturer-independent in core.weak_link.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from core.weak_link import component_from_certificate, evaluate_weak_link, ONBOARD_TAIL_APPLICATION

@dataclass
class GleisteinComponent:
    certificate_id: str
    component_id: str
    component_type: str
    item_description: str = ""
    raw_material: str = ""
    final_presentation: str = ""
    onboard_application: str | None = None
    applicable_break_load_label: str | None = None
    diameter_mm: float | None = None
    length_m: float | None = None
    break_load_linear_kn: float | None = None
    break_load_spliced_kn: float | None = None
    break_load_grommet_kn: float | None = None
    calculated_breaking_load_kn: float | None = None
    source_pages: tuple[int, ...] = ()
    def strength(self):
        return component_from_certificate(component_id=self.component_id, component_type=self.component_type,
            certificate_id=self.certificate_id, break_load_linear_kn=self.break_load_linear_kn,
            break_load_spliced_kn=self.break_load_spliced_kn, break_load_grommet_kn=self.break_load_grommet_kn,
            final_presentation=self.final_presentation, onboard_application=self.onboard_application,
            applicable_load_label=self.applicable_break_load_label)

def _num(value):
    s=re.sub(r"[^0-9,.-]", "", str(value))
    if "," in s and "." in s: s=s.replace(",", "") if s.rfind(".")>s.rfind(",") else s.replace(".","").replace(",",".")
    elif "," in s:
        s=s.replace(",", "") if len(s.rsplit(",",1)[1])==3 else s.replace(",", ".")
    return float(s)

def _clean(s): return re.sub(r"\s+", " ", s or "").strip(" :\t")

def _normalize_cert_id(s):
    s=_clean(s).upper()
    s=re.sub(r"^W(?:2Z25|WZ25|Z25|225)-", "W225-", s)
    return s

def _field(text,label):
    m=re.search(rf"{re.escape(label)}\s*:\s*(.+)",text,re.I)
    return _clean(m.group(1)) if m else ""

def _classify(text,item,desc,cert_id):
    b=f"{text} {item} {desc}".upper()
    if any(x in b for x in ("GEOSQUARE", "ENDLESS", "TAIL")):
        return "TAIL"
    if any(x in b for x in ("GEOLINK", "LASHING")):
        return "GEOLINK/LASHING"
    if any(x in b for x in ("FLEXTWIN", "MAIN LINE")):
        return "MAIN LINE"
    return "OTHER"

def _value(text,label):
    m=re.search(rf"{re.escape(label)}[^\n]*",text,re.I)
    if not m: return None
    lines=text[m.end():].splitlines()
    probe=" ".join(x.strip() for x in lines[:3] if x.strip())
    n=re.search(r"[-+]?\d[\d\s]*(?:[.,]\d[\d\s.,]*)?",probe)
    return _num(n.group(0)) if n else None

def _diameter(text):
    for p in (r"diameter[^\n]{0,50}?([\d.,]+)\s*mm", r"(?:dia\.?|Ø)\s*([\d.,]+)\s*mm"):
        m=re.search(p,text,re.I)
        if m:return _num(m.group(1))
    return None

def _length(text):
    for p in (r"(?:quantity|length)[^\n]{0,40}?\b\d+\s*[x×]\s*([\d.,]+)\s*m\b", r"\bCL\s*([\d.,]+)\s*MTR\b"):
        m=re.search(p,text,re.I)
        if m:return _num(m.group(1))
    return None

def _cert_id_from_text(text):
    m=re.search(r"Certificate\s+no\.\s*:\s*([A-Z0-9-]+)",text,re.I)
    return _normalize_cert_id(m.group(1)) if m else ""

def _item_from_text(text):
    m=re.search(r"Item\s+No\.\s+client\s*/\s*Gleistein\s*:\s*(.+?)(?=\n|$)",text,re.I)
    return _clean(m.group(1)) if m else ""

def _component_id(text,ctype,item,cert_id):
    # Prefer explicit physical IDs. These patterns are deliberately generic for
    # rope-product IDs, not tied to a single certificate page position.
    patterns = {
        "TAIL": [r"\b\d{6,}[xX]\d{1,3}\b", r"(?:TAIL|GEOSQUARE[^\n]{0,40})[^\n]*?\b([A-Z0-9][A-Z0-9_-]{6,})\b"],
        "GEOLINK/LASHING": [r"\b\d{8,}\b", r"(?:LASHING|GEOLINK)[^\n]*?\b([A-Z0-9][A-Z0-9_-]{6,})\b"],
        "MAIN LINE": [r"\b6FT[A-Z0-9_-]+\b", r"(?:MAIN LINE|FLEXTWIN)[^\n]*?\b([A-Z0-9][A-Z0-9_-]{6,})\b"],
    }
    for p in patterns.get(ctype,[]):
        m=re.search(p,text,re.I)
        if m:return _clean(m.group(1) if m.lastindex else m.group(0))
    if item and item.lower() not in {"item description", "item description:"}: return _clean(item.split("/")[-1])
    return cert_id or "UNKNOWN"

def _groups(pages):
    groups=[]; current=None
    for n,text in enumerate(pages,1):
        cert=_cert_id_from_text(text)
        if current is None: current={"pages":[],"cert_id":""}; groups.append(current)
        if cert and current["cert_id"] and cert!=current["cert_id"]:
            current={"pages":[],"cert_id":cert}; groups.append(current)
        if cert: current["cert_id"]=cert
        current["pages"].append((n,text))
    return groups

def parse_gleistein_pages(page_texts):
    pages=list(page_texts or []); components=[]; warnings=[]
    for group in _groups(pages):
        text="\n".join(t for _,t in group["pages"]); cert=group["cert_id"] or _cert_id_from_text(text)
        item=_item_from_text(text)
        # If OCR loses the item field, classify from the complete document text.
        desc_m=re.search(r"Item\s+description\s*:\s*(.+?)(?=\n(?:Final\s+presentation|Raw\s+material|Delivered\s+quantity|Break\s+load))",text,re.I|re.S)
        desc=_clean(desc_m.group(1)) if desc_m else ""
        ctype=_classify(text,item,desc,cert)
        cid=_component_id(text,ctype,item,cert)
        presentation=_field(text,"Final presentation")
        onboard=ONBOARD_TAIL_APPLICATION if ctype=="TAIL" else None
        linear=_value(text,"Break load linear"); spliced=_value(text,"Break load spliced"); grommet=_value(text,"Break load grommet"); calculated=_value(text,"Calculated breaking load")
        probe=component_from_certificate(component_id=cid,component_type=ctype,certificate_id=cert,
            break_load_linear_kn=linear,break_load_spliced_kn=spliced,break_load_grommet_kn=grommet,
            final_presentation=presentation,onboard_application=onboard)
        c=GleisteinComponent(certificate_id=cert,component_id=cid,component_type=ctype,item_description=desc,
            raw_material=_field(text,"Raw material"),final_presentation=presentation,onboard_application=onboard,
            applicable_break_load_label=probe.applicable_load_label,diameter_mm=_diameter(text),length_m=_length(text),
            break_load_linear_kn=linear,break_load_spliced_kn=spliced,break_load_grommet_kn=grommet,
            calculated_breaking_load_kn=calculated,source_pages=tuple(n for n,_ in group["pages"]))
        if not cert: warnings.append(f"{cid}: certificate number not extracted.")
        if ctype=="OTHER": warnings.append(f"{cid}: component type could not be classified from the certificate.")
        if c.applicable_break_load_label and not probe.applicable_breaking_load:
            warnings.append(f"{cid}: applicable load '{c.applicable_break_load_label}' is not present in extracted values.")
        components.append(c)
    weak=evaluate_weak_link([c.strength() for c in components]); combined="\n".join(pages)
    return {"manufacturer":"Gleistein GmbH" if re.search(r"\bGleistein\b",combined,re.I) else "",
        "ship_name":_field(combined,"Ship name"),"imo":_field(combined,"IMO no."),"order_no":_field(combined,"Order no."),
        "components":[asdict(c) for c in components],"weak_link":weak.as_dict(),"warnings":warnings,
        "requires_review":True,"total_pages":len(pages),"raw_text":"\n\n".join(pages)}
