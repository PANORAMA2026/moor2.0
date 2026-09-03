"""Certificate PDF extraction with deterministic OCR and component parsing."""
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
        with fitz.open(stream=data,filetype='pdf') as doc:return '\n\n'.join(p.get_text('text') for p in doc).strip()
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
                    low=s.lower(); keys=('certificate no','item no','item description','break load','raw material','final presentation','ship name')
                    return len(s)+1000*sum(k in low for k in keys)
                pages.append(max(candidates,key=score) if candidates else '')
    except Exception as exc:return [],f'Tesseract OCR failed: {type(exc).__name__}: {exc}'
    return pages,None if any(pages) else 'Tesseract completed but returned no readable text.'

def extract_ocr_text_from_pdf(uploaded_file):
    pages,diag=extract_ocr_pages_from_pdf(uploaded_file)
    return '\n\n'.join(pages).strip(),diag

def _field(extraction,name,default=None):
    value=extraction.get(name); return default if value is None else value

def _kn_or_tons_to_tons(value,unit):
    if value is None:return 0.0
    return float(value)/9.80665 if (unit or '').lower().strip()=='kn' else float(value)

def _text_value(text,patterns,default=''):
    for pattern in patterns:
        m=re.search(pattern,text,re.I|re.M)
        if m:return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return default

def _to_legacy_dict(extraction):
    min_field=next((f for f in extraction.fields if f.name=='minimum_breaking_load'),None)
    calc_field=next((f for f in extraction.fields if f.name=='calculated_breaking_load'),None)
    ldbf_field=next((f for f in extraction.fields if f.name=='ldbf'),None)
    minimum_tons=_kn_or_tons_to_tons(min_field.value if min_field else None,min_field.unit if min_field else None)
    calculated_tons=_kn_or_tons_to_tons(calc_field.value if calc_field else None,calc_field.unit if calc_field else None)
    ldbf_tons=_kn_or_tons_to_tons(ldbf_field.value if ldbf_field else None,ldbf_field.unit if ldbf_field else None)
    text=extraction.raw_text
    cert_id=_text_value(text,[r'unique\s+id[- ]?number\s*[:=]\s*([A-Z0-9_-]+)',r'certificate\s*(?:no\.?|number)?\s*[:#=]\s*([A-Z0-9./_-]+)'],'UNKNOWN')
    manufacturer='Bexco' if re.search(r'\bbexco\b',text,re.I) else _text_value(text,[r'\bmanufacturer\s*[:=]\s*([^\n,;]+)'],'')
    return {'cert_id':cert_id,'manufacturer':manufacturer or 'N/A','main_material':_text_value(text,[r'product\s*[:=]\s*([^\n]+)'],'N/A'),'main_diameter_mm':float(_field(extraction,'diameter_mm',0.0)),'main_mbl_tons':minimum_tons,'minimum_breaking_load_tons':minimum_tons,'calculated_breaking_load_tons':calculated_tons,'ldbf_tons':ldbf_tons,'main_length_m':float(_field(extraction,'length_m',0.0)),'line_linear_density':_field(extraction,'line_linear_density',None),'rope_type':_text_value(text,[r'rope\s+type\s*[:=]\s*([^\n]+)'],''),'average_immediate_strain_pct':{},'has_tail':False,'tail_material':'','tail_diameter_mm':0.0,'tail_mbl_tons':0.0,'tail_length_m':0.0,'standard':'','_warnings':list(extraction.warnings),'_validation_errors':[],'_source_text':text,'_extraction_method':'deterministic parser','_requires_review':True}

def parse_line_certificate(uploaded_file):
    if uploaded_file is None:return None
    data=extract_bytes_from_file(uploaded_file)
    text=extract_text_from_pdf(uploaded_file)
    method='PyMuPDF + deterministic parser'
    page_texts=[]
    diag=None
    if not text:
        page_texts,diag=extract_ocr_pages_from_pdf(uploaded_file)
        text='\n\n'.join(page_texts).strip()
        method='PyMuPDF + Tesseract OCR + component parser'
    else:
        try:
            with fitz.open(stream=data,filetype='pdf') as doc: page_texts=[p.get_text('text') or '' for p in doc]
        except Exception: page_texts=[]
    if not text:
        return {'cert_id':'UNKNOWN','_warnings':[diag or 'No readable text was extracted.'],'_validation_errors':['No extractable certificate text'],'_requires_review':True,'_extraction_method':'OCR_FAILED'}

    # Gleistein multi-component document path.  It is selected from the actual
    # source terminology, not from a filename or an assumed document layout.
    if re.search(r'Gleistein|FlexTwin|GeoSquare|GeoLink',text,re.I):
        parsed=parse_gleistein_pages(page_texts or [text])
        parsed['_extraction_method']=method
        parsed['_warnings']=list(parsed.get('warnings',[]))
        parsed['_source_text']=text
        parsed['_requires_review']=True
        return parsed

    extraction=_parse_core_certificate(text)
    result=_to_legacy_dict(extraction)
    result['_extraction_method']=method
    result['_warnings']=list(result.get('_warnings',[]))
    if diag:result['_warnings'].append(diag)
    if 'Tesseract OCR' in method:result['_warnings'].append('OCR output is unverified; compare every field with the original certificate before saving.')
    if result['main_mbl_tons']<=0:result['_validation_errors'].append('Minimum Breaking Load / certificate MBL not extracted')
    if result['main_diameter_mm']<=0:result['_validation_errors'].append('Diameter not extracted')
    if result['main_length_m']<=0:result['_validation_errors'].append('Length not extracted')
    return result

def parse_certificate_text(text):
    if not text or not text.strip():return None
    extraction=_parse_core_certificate(text)
    result=_to_legacy_dict(extraction); result['_validation_errors']=[]
    if result['main_mbl_tons']<=0:result['_validation_errors'].append('Minimum Breaking Load / certificate MBL not extracted')
    if result['main_diameter_mm']<=0:result['_validation_errors'].append('Diameter not extracted')
    if result['main_length_m']<=0:result['_validation_errors'].append('Length not extracted')
    return result

def dynamic_regex_parse(text):return parse_certificate_text(text) or {}

def safe_extract_json(text_response):
    import json
    if not text_response:return None
    cleaned=re.sub(r'```(?:json)?\s*|```','',text_response.strip())
    try:return json.loads(cleaned)
    except Exception:return None
