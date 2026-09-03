"""AI-assisted visual inspection of mooring lines using Google Gemini Vision."""
from __future__ import annotations
import hashlib, json, mimetypes, sqlite3, uuid
from datetime import datetime, timezone
from typing import Any
import streamlit as st
from config.constants import DB_FILE_PATH
MODEL_DEFAULT = "gemini-2.5-flash"
DAMAGE_TYPES = ("abrasion","glazing_or_heat_damage","broken_yarns_or_strands","cut_or_severed_fibres","chemical_or_contamination","deformation_or_flattening","sheath_or_cover_damage","splice_or_end_damage","unknown")
SEVERITIES = ("NONE","LOW","MODERATE","HIGH","CRITICAL","UNDETERMINED")

def _secret(name: str) -> str:
    try: return str(st.secrets.get(name, "")).strip()
    except Exception: return ""

def ai_is_configured() -> bool: return bool(_secret("GEMINI_API_KEY"))

def init_ai_repository() -> None:
    conn=sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_line_inspections (
      inspection_id TEXT PRIMARY KEY,line_id TEXT NOT NULL,timestamp_utc TEXT NOT NULL,
      model TEXT NOT NULL,provider TEXT NOT NULL DEFAULT 'Google Gemini',image_sha256 TEXT NOT NULL,
      image_mime TEXT NOT NULL,image_blob BLOB NOT NULL,image_quality TEXT NOT NULL,
      overall_severity TEXT NOT NULL,confidence REAL,findings_json TEXT NOT NULL,ai_summary TEXT NOT NULL,
      retake_requested INTEGER NOT NULL DEFAULT 0,operator_status TEXT NOT NULL DEFAULT 'PENDING_OPERATOR_CONFIRMATION',
      operator_note TEXT DEFAULT '',confirmed_at_utc TEXT)""")
    conn.commit(); conn.close()

def _parse_json(text: str) -> dict[str,Any]:
    text=text.strip(); start,end=text.find("{"),text.rfind("}")
    if start<0 or end<=start: raise ValueError("Gemini response did not contain a JSON object")
    return json.loads(text[start:end+1])

def _normalize(result: dict[str,Any]) -> dict[str,Any]:
    q=str(result.get("image_quality","UNDETERMINED")).upper(); q=q if q in {"GOOD","ACCEPTABLE","POOR","INSUFFICIENT","UNDETERMINED"} else "UNDETERMINED"
    s=str(result.get("overall_severity","UNDETERMINED")).upper(); s=s if s in SEVERITIES else "UNDETERMINED"
    try: c=max(0.0,min(1.0,float(result.get("confidence")))) if result.get("confidence") is not None else None
    except (TypeError,ValueError): c=None
    findings=[]
    for x in result.get("findings",[]) or []:
        if not isinstance(x,dict): continue
        dt=str(x.get("damage_type","unknown")).lower(); dt=dt if dt in DAMAGE_TYPES else "unknown"
        fs=str(x.get("severity","UNDETERMINED")).upper(); fs=fs if fs in SEVERITIES else "UNDETERMINED"
        findings.append({"damage_type":dt,"severity":fs,"confidence":x.get("confidence"),"observation":str(x.get("observation","")).strip(),"location":str(x.get("location","")).strip()})
    return {"image_quality":q,"overall_severity":s,"confidence":c,"findings":findings,"summary":str(result.get("summary","")).strip(),"retake_requested":bool(result.get("retake_requested",q in {"POOR","INSUFFICIENT"}))}

def inspect_image(image_bytes: bytes, filename: str, line_id: str, model: str = MODEL_DEFAULT) -> dict[str,Any]:
    if not ai_is_configured(): raise RuntimeError("GEMINI_API_KEY is not configured in Streamlit Secrets.")
    if not image_bytes: raise ValueError("Inspection image is empty.")
    if len(image_bytes)>12*1024*1024: raise ValueError("Inspection image is larger than 12 MB.")
    mime=mimetypes.guess_type(filename)[0] or "image/jpeg"
    if mime not in {"image/jpeg","image/png","image/webp","image/gif"}: raise ValueError("Unsupported image type. Use JPEG, PNG, WEBP, or GIF.")
    import google.generativeai as genai
    genai.configure(api_key=_secret("GEMINI_API_KEY"))
    prompt=f'''You are an AI visual inspection assistant for a ship's mooring-line maintenance record. Line ID: {line_id}.
Analyze ONLY what is visibly supported by the photograph. Identify abrasion, glazing/heat damage, broken yarns/strands, cuts, chemical/contamination, deformation/flattening, sheath/cover damage, splice/end damage, or unknown.
Do NOT estimate wear percentage, residual strength, MBL, LDBF, WLL, remaining life. Do NOT declare safe/unsafe or recommend replacement. Severity is visual severity only. If image quality is insufficient, request another photo. Return JSON only.
Use exactly: {{"image_quality":"GOOD|ACCEPTABLE|POOR|INSUFFICIENT|UNDETERMINED","overall_severity":"NONE|LOW|MODERATE|HIGH|CRITICAL|UNDETERMINED","confidence":0.0,"findings":[{{"damage_type":"abrasion|glazing_or_heat_damage|broken_yarns_or_strands|cut_or_severed_fibres|chemical_or_contamination|deformation_or_flattening|sheath_or_cover_damage|splice_or_end_damage|unknown","severity":"NONE|LOW|MODERATE|HIGH|CRITICAL|UNDETERMINED","confidence":0.0,"observation":"","location":""}}],"summary":"","retake_requested":false}}'''
    response=genai.GenerativeModel(model_name=model).generate_content([prompt,{"mime_type":mime,"data":image_bytes}])
    r=_normalize(_parse_json(response.text)); r.update({"inspection_id":str(uuid.uuid4()),"line_id":str(line_id),"timestamp_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"model":model,"provider":"Google Gemini","image_sha256":hashlib.sha256(image_bytes).hexdigest(),"image_mime":mime,"image_filename":filename}); return r

def save_inspection(result: dict[str,Any], image_bytes: bytes) -> None:
    init_ai_repository(); conn=sqlite3.connect(DB_FILE_PATH,check_same_thread=False)
    conn.execute("INSERT INTO ai_line_inspections (inspection_id,line_id,timestamp_utc,model,provider,image_sha256,image_mime,image_blob,image_quality,overall_severity,confidence,findings_json,ai_summary,retake_requested,operator_status,operator_note,confirmed_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(result["inspection_id"],result["line_id"],result["timestamp_utc"],result["model"],result.get("provider","Google Gemini"),result["image_sha256"],result["image_mime"],sqlite3.Binary(image_bytes),result["image_quality"],result["overall_severity"],result.get("confidence"),json.dumps(result.get("findings",[]),ensure_ascii=False),result.get("summary",""),1 if result.get("retake_requested") else 0,"PENDING_OPERATOR_CONFIRMATION","",None)); conn.commit(); conn.close()

def list_inspections(line_id: str|None=None)->list[dict[str,Any]]:
    init_ai_repository(); conn=sqlite3.connect(DB_FILE_PATH,check_same_thread=False); q="SELECT inspection_id,line_id,timestamp_utc,model,provider,image_sha256,image_mime,image_quality,overall_severity,confidence,findings_json,ai_summary,retake_requested,operator_status,operator_note,confirmed_at_utc FROM ai_line_inspections"; p=()
    if line_id: q+=" WHERE line_id=?"; p=(str(line_id),)
    rows=conn.execute(q+" ORDER BY timestamp_utc DESC",p).fetchall(); conn.close(); cols="inspection_id line_id timestamp_utc model provider image_sha256 image_mime image_quality overall_severity confidence findings_json ai_summary retake_requested operator_status operator_note confirmed_at_utc".split(); return [dict(zip(cols,r)) for r in rows]

def get_inspection_image(inspection_id:str)->bytes|None:
    init_ai_repository(); conn=sqlite3.connect(DB_FILE_PATH,check_same_thread=False); r=conn.execute("SELECT image_blob FROM ai_line_inspections WHERE inspection_id=?",(inspection_id,)).fetchone(); conn.close(); return bytes(r[0]) if r and r[0] is not None else None

def confirm_inspection(inspection_id:str,operator_note:str="")->None:
    init_ai_repository(); conn=sqlite3.connect(DB_FILE_PATH,check_same_thread=False); conn.execute("UPDATE ai_line_inspections SET operator_status='OPERATOR_CONFIRMED',operator_note=?,confirmed_at_utc=? WHERE inspection_id=?",(str(operator_note).strip(),datetime.now(timezone.utc).isoformat(timespec="seconds"),inspection_id)); conn.commit(); conn.close()
