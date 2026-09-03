"""Operator-facing AI visual inspection workflow for mooring lines."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.ai_inspection import (
    MODEL_DEFAULT,
    ai_is_configured,
    confirm_inspection,
    get_inspection_image,
    inspect_image,
    list_inspections,
    save_inspection,
)
from core.auth import require_login, logout_button
from database.db_manager import load_lines_inventory_from_db

st.set_page_config(page_title="AI Line Inspection — OpenMooring", layout="wide")
require_login()
logout_button()

st.title("🤖 AI Line Inspection")
st.caption("AI-assisted visual inspection: damage classification → operator confirmation → inspection history.")

st.info(
    "AI is advisory only. It does not calculate wear %, residual strength, MBL/LDBF/WLL, remaining life, or replacement criteria. "
    "A confirmed AI observation is an inspection record, not an engineering acceptance decision."
)

inventory = st.session_state.get("lines_inventory")
if not isinstance(inventory, pd.DataFrame) or inventory.empty:
    try:
        inventory = load_lines_inventory_from_db()
    except Exception:
        inventory = pd.DataFrame()

if inventory.empty or "line_id" not in inventory.columns:
    st.warning("Line inventory non disponibile. Carica/configura le linee prima dell'ispezione AI.")
    st.stop()

inventory = inventory.copy()
inventory["line_id"] = inventory["line_id"].astype(str)
name_col = "line_name" if "line_name" in inventory.columns else None
labels = inventory.apply(
    lambda r: f"{r['line_id']} — {r[name_col]}" if name_col and str(r.get(name_col, "")).strip() else str(r["line_id"]),
    axis=1,
).tolist()

left, right = st.columns([1, 1])
with left:
    selected_label = st.selectbox("Linea da ispezionare", labels)
    selected_line = str(inventory.iloc[labels.index(selected_label)]["line_id"])
with right:
    st.metric("AI model", MODEL_DEFAULT)

if not ai_is_configured():
    st.warning("AI non configurata: aggiungere OPENAI_API_KEY nei Secrets di Streamlit. La chiave non deve essere inserita nel repository.")

st.subheader("📷 Nuova ispezione")
photo = st.file_uploader(
    "Carica una foto della cima",
    type=["jpg", "jpeg", "png", "webp", "gif"],
    key="ai_line_photo",
    help="Preferire immagini ravvicinate, ben illuminate e con la zona danneggiata chiaramente visibile.",
)

if photo:
    st.image(photo, caption=f"Photo — {selected_line}", use_container_width=True)
    if st.button("🔍 Analizza con AI", type="primary", use_container_width=True, disabled=not ai_is_configured()):
        try:
            with st.spinner("Analisi visiva in corso…"):
                result = inspect_image(photo.getvalue(), photo.name, selected_line)
                save_inspection(result, photo.getvalue())
            st.session_state["last_ai_inspection"] = result
            st.success("Analisi completata e salvata come PENDING OPERATOR CONFIRMATION.")
        except Exception as exc:
            st.error(f"AI inspection failed: {exc}")

result = st.session_state.get("last_ai_inspection")
if result and str(result.get("line_id")) == selected_line:
    st.divider()
    st.subheader("🧠 AI assessment")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Image quality", result.get("image_quality", "N/A"))
    q2.metric("Visual severity", result.get("overall_severity", "N/A"))
    conf = result.get("confidence")
    q3.metric("Confidence", f"{float(conf) * 100:.0f}%" if conf is not None else "N/A")
    q4.metric("Retake", "YES" if result.get("retake_requested") else "NO")

    if result.get("retake_requested"):
        st.warning("L'AI ritiene che una nuova foto possa essere necessaria. Seguire le indicazioni sotto e non usare questa valutazione come decisione operativa.")
    if result.get("summary"):
        st.markdown(f"**Sintesi:** {result['summary']}")

    findings = result.get("findings", [])
    if findings:
        st.markdown("#### Findings")
        rows = []
        for item in findings:
            rows.append({
                "Damage type": item.get("damage_type", "unknown"),
                "Severity": item.get("severity", "UNDETERMINED"),
                "Confidence": f"{float(item['confidence']) * 100:.0f}%" if item.get("confidence") is not None else "N/A",
                "Observation": item.get("observation", ""),
                "Location": item.get("location", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Nessun danno visibile classificato dall'AI.")

    st.warning("⚠️ Operator confirmation required. La conferma archivia l'osservazione ma NON modifica automaticamente wear %, status o criteri di sostituzione della cima.")
    note = st.text_area("Nota dell'operatore", key=f"ai_note_{result['inspection_id']}")
    if st.button("✅ Conferma osservazione AI", use_container_width=True):
        confirm_inspection(result["inspection_id"], note)
        result["operator_status"] = "OPERATOR_CONFIRMED"
        st.session_state["last_ai_inspection"] = result
        st.success("Osservazione confermata e registrata.")

st.divider()
st.subheader("📚 AI inspection history")
history = list_inspections(selected_line)
if not history:
    st.info("Nessuna ispezione AI registrata per questa linea.")
else:
    for item in history:
        status = item.get("operator_status", "PENDING_OPERATOR_CONFIRMATION")
        title = f"{item['timestamp_utc']} · {item['line_id']} · {item['overall_severity']} · {status}"
        with st.expander(title):
            c1, c2, c3 = st.columns(3)
            c1.metric("Image quality", item.get("image_quality", "N/A"))
            c2.metric("Confidence", f"{float(item['confidence']) * 100:.0f}%" if item.get("confidence") is not None else "N/A")
            c3.metric("Retake", "YES" if item.get("retake_requested") else "NO")
            st.write(item.get("ai_summary", ""))
            try:
                st.dataframe(pd.DataFrame(json.loads(item.get("findings_json", "[]"))), use_container_width=True, hide_index=True)
            except Exception:
                pass
            image = get_inspection_image(item["inspection_id"])
            if image:
                st.download_button(
                    "⬇️ Foto originale",
                    data=image,
                    file_name=f"inspection_{item['inspection_id']}.jpg",
                    mime="image/jpeg",
                    key=f"download_{item['inspection_id']}",
                )
            if item.get("operator_note"):
                st.caption(f"Operator note: {item['operator_note']}")

st.caption("Engineering boundary: AI detection ≠ engineering assessment. Any later mapping from visual damage to wear/acceptance/replacement must use validated manufacturer, MEG4/class/SMS criteria and an auditable human review.")
