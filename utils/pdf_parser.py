"""
utils/pdf_parser.py
Parser minimale a prova di errore di sintassi.
"""

import json
import os
import re
import streamlit as st

try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def extract_bytes_from_file(uploaded_file) -> bytes:
    if uploaded_file is None:
        return b""
    try:
        if hasattr(uploaded_file, "getvalue"):
            return uploaded_file.getvalue()
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            data = uploaded_file.read()
            uploaded_file.seek(0)
            return data
    except Exception:
        pass
    return b""


def extract_text_from_pdf(uploaded_file) -> str:
    file_bytes = extract_bytes_from_file(uploaded_file)
    if not file_bytes or not HAS_PYMUPDF:
        return ""

    text = ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            t = page.get_text("text")
            if t:
                text += t + "\n"
        doc.close()
    except Exception:
        pass

    return text.strip()


def resolve_working_model():
    try:
        available_models = genai.list_models()
        for m in available_models:
            if "generateContent" in m.supported_generation_methods:
                return m.name
    except Exception:
        pass
    return "models/gemini-1.5-flash"


def safe_extract_json(text_response: str) -> dict:
    if not text_response:
        return None

    cleaned = text_response.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
        cleaned = cleaned.replace("```", "").strip()

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except Exception:
            pass

    try:
        return json.loads(cleaned)
    except Exception:
        return None


def parse_line_certificate(uploaded_file) -> dict:
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if text and len(text) > 40:
        parsed_data = parse_certificate_text(text)
        if parsed_data:
            return parsed_data

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = extract_bytes_from_file(uploaded_file)
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=90)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model_name = resolve_working_model()
            model = genai.GenerativeModel(model_name)

            prompt = (
                "Sei un ingegnere navale. Estrai i dati del certificato cavi MEG4 in JSON con i campi: "
                "cert_id, manufacturer, standard, main_material, main_diameter_mm, main_mbl_tons, main_length_m, "
                "has_tail, tail_material, tail_diameter_mm, tail_mbl_tons, tail_length_m."
            )

            response = model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": img_bytes}
            ])

            result_dict = safe_extract_json(response.text)
            if result_dict:
                return result_dict

        except Exception as e:
            st.warning(f"Errore Vision: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model_name = resolve_working_model()
            model = genai.GenerativeModel(model_name)

            prompt = (
                "Estrai i dati di questo certificato cavi MEG4 in formato JSON (cert_id, manufacturer, main_material, "
                "main_diameter_mm, main_mbl_tons, main_length_m):\n\n" + text[:2000]
            )

            response = model.generate_content(prompt)
            result_dict = safe_extract_json(response.text)
            if result_dict:
                return result_dict

        except Exception as e:
            st.warning(f"Errore Text Parsing: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    data = {
        "cert_id": "UNKNOWN",
        "manufacturer": "N/A",
        "main_material": "N/A",
        "main_diameter_mm": 0.0,
        "main_mbl_tons": 0.0,
        "main_length_m": 0.0,
        "has_tail": False,
        "tail_material": "",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "MEG4"
    }

    if not text:
        return data

    cert_m = re.search(r"(?:Cert|Certificate|Nr|No)\.?\s*:?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
    if cert_m:
        data["cert_id"] = cert_m.group(1)

    dia_m = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, re.IGNORECASE)
    if dia_m:
        data
