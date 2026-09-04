"""PDF/OCR certificate ingestion and manufacturer-independent normalization."""
from __future__ import annotations
import io, os, re, shutil
try:
    import fitz
    HAS_PYMUPDF=True
except ImportError: HAS_PYMUPDF=False
try:
    import pytesseract
    from PIL import Image, ImageOps, ImageFilter
    HAS_OCR=True
except ImportError: HAS_OCR=False
from core.certificate_parser import parse_certificate_text as _parse_core_certificate
from core.gleistein_parser import parse_gleistein_pages
from core.weak_link import component_from_certificate, evaluate_weak_link

def extract_bytes_from_file(uploaded_file)->bytes:
    if uploaded_file is None:return b""
    try:
        if hasattr(uploaded_file,'getvalue'): return uploaded_file.getvalue()
        if hasattr(uploaded_file,'read'):
            uploaded_file.seek(0); data=uploaded_file.read(); uploaded_file.seek(0); return data
    except Exception:return b""
    return b""

def extract_text_from_pdf(uploaded_file)->str:
    data=extract_bytes_from_file(uploaded_file)
    if not data or not HAS_PYMUPDF:return ""
    try:
        with fitz.open(stream=data,filetype='pdf') as doc:return '\n\n'.join(p.get_text('text') or '' for p in doc).strip()
    except Exception:return ""

def _tesseract_available():
    if not HAS_OCR:return False
    configured=os.environ.get('TESSERACT_CMD','').strip()
    if configured and os.path.exists(configured): pytesseract.pytesseract.tesseract_cmd=configured; return True
    return bool(shutil.which('tesseract'))

def extract_ocr_pages_from_pdf(uploaded_file):
    data=extract_bytes_from_file(uploaded_file)
    if not data:return [],'No PDF bytes received.'
    if not HAS_PYMUPDF:return [],'PyMuPDF is not installed.'
    if not HAS_OCR:return [],'pytesseract/Pillow is not installed.'
    if not _tesseract_available():return [],'Tesseract executable is not installed in the Streamlit runtime.'
    pages=[]
    try:
        with fitz.open(stream=data,filetype='pdf') as doc:
            for page in doc:
                pix=page.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
                image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('L')
                image=ImageOps.autocontrast(image).filter(ImageFilter.SHARPEN)
                right=image.crop((int(image.width*.40),0,image.width,image.height))
                candidates=[]
                for source in (right,image):
                    for psm in (3,6,11):
                        try:
                            t=pytesseract.image_to_string(source,lang='eng',config=f'--psm {psm}')
                            if t and t.strip(): candidates.append(t.strip())
                        except Exception: pass
                def score(s):
                    low=s.lower(); keys=('certificate no','certificate number','unique id','product identification','item no','diameter','minimum breaking load','break load','description')
                    return len(s)+1500*sum(k in low for k in keys)
                pages.append(max(candidates,key=score) if candidates else '')
    except Exception as exc:return [],f'Tesseract OCR failed: {type(exc).__name__}: {exc}'
    return pages,None if any(pages) else 'Tesseract completed but returned no readable text.'

def extract_ocr_text_from_pdf(uploaded_file):
    pages,diag=extract_ocr_pages_from_pdf(uploaded_file); return '\n\n'.join(pages).strip(),diag

def _text_value(text,patterns,default=''):
    for pattern in patterns:
        m=re.search(pattern,text,re.I|re.M|re.S)
        if m:return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return default

def _kn_to_tons(v): return float(v)/9.80665 if v is not None else 0.0

def _generic_component(extraction, text):
    cert=extraction.get('certificate_id') or _text_value(text,[r'certificate\s*(?:no\.?|number)\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]*)'], 'UNKNOWN')
    cid=extraction.get('component_id') or cert
    product=extraction.get('product') or 'Unknown product'
    # Product and description terminology are used only for classification;
    # no physical assembly is invented when the document does not state it.
    upper=text.upper()
    if any(x in upper for x in ('GEOLINK','LASHING')): ctype='GEOLINK/LASHING'
    elif any(x in upper for x in ('TAIL DESIGN','TDBF','TAIL','GEOSQUARE')): ctype='TAIL'
    else: ctype='MAIN LINE'
    minimum=extraction.get('minimum_breaking_load_kn')
    ldbf=extraction.get('ldbf_kn')
    tdbf=extraction.get('tdbf_kn')
    presentation=extraction.get('presentation_hint') or ''
    onboard='LOOP_AROUND_BOLLARD' if ctype=='TAIL' else None
    # For a single rope certificate, a declared LDBF is the applicable line
    # capacity when present. Otherwise use the declared minimum breaking load.
    if ldbf is not None:
        applicable_label='LDBF'
    elif minimum is not None:
        applicable_label='Minimum breaking load'
    else:
        applicable_label=None
    strength=component_from_certificate(component_id=str(cid),component_type=ctype,certificate_id=str(cert),
        minimum_breaking_load_kn=minimum,ldbf_kn=ldbf,final_presentation=presentation,
        onboard_application=onboard,applicable_load_label=applicable_label)
    loads={x.label:x.value_kn for x in strength.breaking_loads}
    return {
        'certificate_id':str(cert),'component_id':str(cid),'component_type':ctype,
        'item_description':str(product),'raw_material':'','final_presentation':str(presentation),
        'onboard_application':onboard,'applicable_break_load_label':strength.applicable_load_label,
        'diameter_mm':extraction.get('diameter_mm'),'length_m':extraction.get('length_m'),
        'break_load_linear_kn':loads.get('Break load linear'),'break_load_spliced_kn':loads.get('Break load spliced'),
        'break_load_grommet_kn':loads.get('Break load grommet'),'calculated_breaking_load_kn':extraction.get('calculated_breaking_load_kn'),
        'minimum_breaking_load_kn':minimum,'ldbf_kn':ldbf,'tdbf_kn':tdbf,
        'source_pages':(1,)
    }, strength

def _to_legacy_dict(extraction,text):
    min_v=extraction.get('minimum_breaking_load_kn'); calc=extraction.get('calculated_breaking_load_kn'); ldbf=extraction.get('ldbf_kn')
    cert=extraction.get('certificate_id') or _text_value(text,[r'unique\s+id[- ]?number\s*[:=]\s*([A-Z0-9._/-]+)',r'certificate\s*(?:no\.?|number)\s*[:#=]\s*([A-Z0-9./_-]+)'],'UNKNOWN')
    product=extraction.get('product') or _text_value(text,[r'product\s*[:=]\s*([^\n]+)',r'description\s*[:=]\s*([^\n]+)'],'N/A')
    component_id=extraction.get('component_id') or cert
    ctype='MAIN LINE'
    comp,_= _generic_component(extraction,text)
    loads = comp
    # Keep the legacy fields consumed by existing database code while the new
    # component list is the authoritative representation.
    return {'cert_id':str(cert),'manufacturer':str(extraction.get('manufacturer') or 'N/A'),
        'main_material':str(product),'main_diameter_mm':float(extraction.get('diameter_mm') or 0),
        'main_mbl_tons':_kn_to_tons(ldbf if ldbf is not None else min_v),
        'minimum_breaking_load_tons':_kn_to_tons(min_v),'calculated_breaking_load_tons':_kn_to_tons(calc),
        'ldbf_tons':_kn_to_tons(ldbf),'main_length_m':float(extraction.get('length_m') or 0),
        'line_linear_density':None,'rope_type':'','average_immediate_strain_pct':{},
        'has_tail':False,'tail_material':'','tail_diameter_mm':0.0,'tail_mbl_tons':0.0,'tail_length_m':0.0,
        'standard':'','_warnings':list(extraction.warnings),'_validation_errors':[],
        '_source_text':text,'_extraction_method':'generic certificate parser','_requires_review':True,
        'components':[loads]}

def parse_line_certificate(uploaded_file):
    if uploaded_file is None:return None
    data=extract_bytes_from_file(uploaded_file); text=extract_text_from_pdf(uploaded_file); method='PyMuPDF + generic certificate parser'; page_texts=[]; diag=None
    if not text:
        page_texts,diag=extract_ocr_pages_from_pdf(uploaded_file); text='\n\n'.join(page_texts).strip(); method='PyMuPDF + Tesseract OCR + generic certificate parser'
    else:
        try:
            with fitz.open(stream=data,filetype='pdf') as doc: page_texts=[p.get_text('text') or '' for p in doc]
        except Exception: page_texts=[]
    if not text:
        return {'cert_id':'UNKNOWN','_warnings':[diag or 'No readable text was extracted.'],'_validation_errors':['No extractable certificate text'],'_requires_review':True,'_extraction_method':'OCR_FAILED'}

    # Multi-component Gleistein certificates use their own source adapter,
    # but the returned schema is identical to the generic engine.
    if re.search(r'Gleistein|FlexTwin|GeoSquare|GeoLink',text,re.I):
        parsed=parse_gleistein_pages(page_texts or [text]); parsed['_extraction_method']=method; parsed['_warnings']=list(parsed.get('warnings',[])); parsed['_source_text']=text; parsed['_requires_review']=True; return parsed

    extraction=_parse_core_certificate(text)
    component,strength=_generic_component(extraction,text)
    # A generic certificate describes one physical rope unless the document
    # itself explicitly identifies multiple components. Never invent a weak link.
    weak=evaluate_weak_link([strength])
    result=_to_legacy_dict(extraction,text)
    result['components']=[component]; result['weak_link']=weak.as_dict(); result['_extraction_method']=method; result['_source_text']=text; result['_requires_review']=True
    if diag:result['_warnings'].append(diag)
    result['_validation_errors']=[]
    for name,label in (("component_id","Physical rope/component ID"),("diameter_mm","Diameter"),("length_m","Length")):
        if extraction.get(name) is None: result['_validation_errors'].append(f'{label} not extracted')
    if extraction.get('minimum_breaking_load_kn') is None and extraction.get('ldbf_kn') is None: result['_validation_errors'].append('No declared breaking-load value extracted')
    if extraction.warnings: result['_warnings'].extend(extraction.warnings)
    if 'Tesseract OCR' in method: result['_warnings'].append('OCR output is unverified; compare every field with the original certificate before saving.')
    return result

def parse_certificate_text(text):
    if not text or not text.strip():return None
    extraction=_parse_core_certificate(text); result=_to_legacy_dict(extraction,text); result['_validation_errors']=[]
    comp,strength=_generic_component(extraction,text); result['components']=[comp]; result['weak_link']=evaluate_weak_link([strength]).as_dict()
    for name,label in (("component_id","Physical rope/component ID"),("diameter_mm","Diameter"),("length_m","Length")):
        if extraction.get(name) is None: result['_validation_errors'].append(f'{label} not extracted')
    return result

def dynamic_regex_parse(text): return parse_certificate_text(text) or {}

def safe_extract_json(text_response):
    import json
    if not text_response:return None
    cleaned=re.sub(r'```(?:json)?\s*|```','',text_response.strip())
    try:return json.loads(cleaned)
    except Exception:return None
