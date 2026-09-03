"""Deterministic parser for multi-component Gleistein mooring certificates."""
from __future__ import annotations
import re
from dataclasses import dataclass,asdict
from core.weak_link import component_from_certificate,evaluate_weak_link

@dataclass
class GleisteinComponent:
    certificate_id:str; component_id:str; component_type:str; item_description:str=''; raw_material:str=''; final_presentation:str=''; diameter_mm:float|None=None; length_m:float|None=None; break_load_linear_kn:float|None=None; break_load_spliced_kn:float|None=None; break_load_grommet_kn:float|None=None; calculated_breaking_load_kn:float|None=None; source_pages:tuple[int,...]=()
    def strength(self):
        return component_from_certificate(component_id=self.component_id,component_type=self.component_type,certificate_id=self.certificate_id,break_load_linear_kn=self.break_load_linear_kn,break_load_spliced_kn=self.break_load_spliced_kn,break_load_grommet_kn=self.break_load_grommet_kn)

def _num(s):
    s=str(s).replace(' ','')
    if ',' in s and '.' in s:s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s:s=s.replace(',','.')
    return float(s)

def _clean(s):return re.sub(r'\s+',' ',s or '').strip()

def _normalize_cert_id(s):
    s=_clean(s).upper(); s=re.sub(r'^W2Z25-', 'W225-', s); return s

def _label(text,label):
    m=re.search(rf'{re.escape(label)}\s*:\s*(.+)',text,re.I); return _clean(m.group(1)) if m else ''

def _classify(item,desc):
    b=f'{item} {desc}'.upper()
    if 'MAIN LINE' in b:return 'MAIN LINE'
    if 'TAIL' in b:return 'TAIL'
    if 'GEOLINK' in b or 'LASHING' in b:return 'GEOLINK/LASHING'
    return 'OTHER'

def _value(text,label):
    m=re.search(rf'{re.escape(label)}\s*\[kN\]\s*([\d.,]+)',text,re.I); return _num(m.group(1)) if m else None

def _diameter(text):
    m=re.search(r'(\d+(?:[.,]\d+)?)\s*mm',text,re.I); return _num(m.group(1)) if m else None

def _length(text):
    m=re.search(r'Delivered\s+quantity.*?\n\s*\d+\s+([\d.,]+)',text,re.I|re.S)
    if m:return _num(m.group(1))
    m=re.search(r'\b\d+\s*[x×]\s*([\d.,]+)\s*m\b',text,re.I); return _num(m.group(1)) if m else None

def _groups(pages):
    """Group consecutive pages by physical item, not only OCR'd certificate ID."""
    groups=[]; current=None
    for n,text in enumerate(pages,1):
        item_m=re.search(r'Item\s+No\.\s+client\s*/\s*Gleistein\s*:\s*(.+)',text,re.I)
        cert_m=re.search(r'Certificate\s+no\.\s*:\s*([A-Z0-9-]+)',text,re.I)
        if item_m:
            current={'pages':[(n,text)],'item':_clean(item_m.group(1)),'cert_id':_normalize_cert_id(cert_m.group(1) if cert_m else '')}
            groups.append(current)
        elif current is not None:
            current['pages'].append((n,text))
    return groups

def parse_gleistein_pages(page_texts):
    pages=list(page_texts or []); components=[]; warnings=[]
    for group in _groups(pages):
        text='\n'.join(t for _,t in group['pages']); item=group['item']; cert_id=group['cert_id']
        parts=re.split(r'\s*/\s*',item,maxsplit=1); comp_id=_clean(parts[1]) if len(parts)==2 else cert_id
        desc_m=re.search(r'Item\s+description\s*:\s*(.+?)(?=\n(?:Final\s+presentation|Raw\s+material|Delivered\s+quantity))',text,re.I|re.S); desc=_clean(desc_m.group(1)) if desc_m else ''
        ctype=_classify(item,desc)
        c=GleisteinComponent(certificate_id=cert_id,component_id=comp_id,component_type=ctype,item_description=desc,raw_material=_label(text,'Raw material'),final_presentation=_label(text,'Final presentation'),diameter_mm=_diameter(desc),length_m=_length(text),break_load_linear_kn=_value(text,'Break load linear'),break_load_spliced_kn=_value(text,'Break load spliced'),break_load_grommet_kn=_value(text,'Break load grommet'),calculated_breaking_load_kn=_value(text,'Calculated breaking load'),source_pages=tuple(n for n,_ in group['pages']))
        if not cert_id:warnings.append(f'{comp_id}: certificate number not extracted.')
        components.append(c)
    weak=evaluate_weak_link([c.strength() for c in components])
    combined='\n'.join(pages)
    return {'manufacturer':'Gleistein GmbH' if re.search(r'\bGleistein\b',combined,re.I) else '', 'ship_name':_label(combined,'Ship name'),'imo':_label(combined,'IMO no.'),'order_no':_label(combined,'Order no.'),'components':[asdict(c) for c in components],'weak_link':weak.as_dict(),'warnings':warnings,'requires_review':True,'total_pages':len(pages),'raw_text':'\n\n'.join(pages)}
