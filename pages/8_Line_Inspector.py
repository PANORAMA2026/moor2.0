"""Single-line digital record: calculation, topology, certificate, history and AI inspection."""
from __future__ import annotations
import json, sqlite3
import pandas as pd
import streamlit as st
from config.constants import DB_FILE_PATH
from database.certificate_repository import get_certificate_pdf, load_certificate_records
from core.auth import require_login, logout_button
from core.ai_inspection import ai_is_configured, inspect_image, save_inspection, list_inspections, get_inspection_image, confirm_inspection
from core.setup_store import list_setup_names, load_setup

st.set_page_config(page_title="Line Inspector — OpenMooring", layout="wide")
if not require_login(): st.stop()
logout_button()
st.title("🪢 Line Inspector")
st.caption("Una linea, un record: configurazione → certificato → tensione → esposizione → ispezione visiva AI.")

inventory=st.session_state.get("lines_inventory",pd.DataFrame()); results=st.session_state.get("latest_mooring_results",pd.DataFrame())
cert_records=pd.DataFrame(load_certificate_records())
if inventory is None or inventory.empty: st.warning("Line inventory non disponibile."); st.stop()
id_col="line_id" if "line_id" in inventory.columns else None
if id_col is None: st.error("Line inventory senza line_id."); st.stop()
name_col="line_name" if "line_name" in inventory.columns else None
inventory=inventory.copy(); inventory[id_col]=inventory[id_col].astype(str)
labels=inventory.apply(lambda r:f"{r[id_col]} — {r[name_col]}" if name_col and str(r[name_col]).strip() else str(r[id_col]),axis=1).tolist()
preselected=str(st.session_state.pop("selected_line_id", "")).strip()
default_index=labels.index(next((label for label in labels if label.split(" — ",1)[0]==preselected), labels[0])) if preselected else 0
choice=st.selectbox("Seleziona linea",labels,index=default_index); selected_id=str(inventory.iloc[labels.index(choice)][id_col]); line=inventory[inventory[id_col]==selected_id].iloc[0]
live=pd.DataFrame()
if isinstance(results,pd.DataFrame) and not results.empty and "line_id" in results.columns: live=results[results.line_id.astype(str)==selected_id].copy()

c1,c2,c3,c4=st.columns(4)
if not live.empty and pd.notna(live.iloc[0].get("Tension_tons")):
    c1.metric("CALCULATED TENSION",f"{float(live.iloc[0]['Tension_tons']):.2f} t"); c2.metric("UTILIZATION",f"{float(live.iloc[0].get('Util_Percent',float('nan'))):.1f}%"); c3.metric("MBL",f"{float(live.iloc[0].get('mbl_tons',line.get('mbl_tons',0))):.2f} t"); c4.metric("SOLVER",str(live.iloc[0].get("Solver_Status","N/A")))
else:
    c1.metric("CALCULATED TENSION","N/A"); c2.metric("UTILIZATION","N/A"); c3.metric("MBL",f"{float(line.get('mbl_tons',0) or 0):.2f} t" if pd.notna(line.get('mbl_tons',0)) else "N/A"); c4.metric("SOLVER","No current result")

st.markdown("### 🔗 Mooring connection")
setup_names=list_setup_names("Ensenada Pier #2")
setup_name=st.session_state.get("active_setup_name",setup_names[0] if setup_names else "Normal")
if setup_name not in setup_names: setup_name=setup_names[0] if setup_names else "Normal"
setup_df=load_setup("Ensenada Pier #2",setup_name)
route_row=setup_df[setup_df.line_id.astype(str)==selected_id] if not setup_df.empty and "line_id" in setup_df.columns else pd.DataFrame()
if not route_row.empty:
    r=route_row.iloc[0]; winch=str(r.get("winch_id") or "N/A"); slot=str(r.get("winch_slot") or ""); winch_display=f"{winch} / slot {slot}" if slot else winch
    st.info(f"**Setup:** {setup_name} · **Winch:** {winch_display} → **Fairlead:** {r.get('fairlead_id','N/A')} → **Bollard:** {r.get('bollard_id','N/A')} ({r.get('bollard_station','')})")
else: st.warning(f"Nessuna connessione della linea {selected_id} trovata nel setup {setup_name}.")

left,right=st.columns(2)
with left:
    st.markdown("### 📜 Certificate")
    cert_id=str(line.get("cert_id","")).strip(); cert=None
    if cert_id and not cert_records.empty and "cert_id" in cert_records.columns and (cert_records.cert_id.astype(str)==cert_id).any(): cert=cert_records[cert_records.cert_id.astype(str)==cert_id].iloc[0].to_dict()
    if cert:
        fields={"Certificate ID":cert.get("cert_id"),"Manufacturer":cert.get("manufacturer"),"Material / Grade":cert.get("material_grade"),"Diameter":f"{cert.get('diameter_mm')} mm","Length":f"{cert.get('length_m')} m","Minimum Breaking Load — MBL":f"{cert.get('mbl_t')} t" if cert.get('mbl_t') else "N/A","LDBF":f"{cert.get('ldbf_t')} t" if cert.get('ldbf_t') else "N/A","Review":cert.get("review_status")}
        st.dataframe(pd.DataFrame(list(fields.items()),columns=["Field","Value"]),use_container_width=True,hide_index=True)
        document=get_certificate_pdf(cert_id)
        if document and document.get("source_pdf_blob"):
            st.caption(f"Original PDF · SHA-256 {document.get('source_pdf_sha256','')}"); st.download_button("⬇️ Apri PDF certificato",data=document["source_pdf_blob"],file_name=document.get("source_pdf_filename") or f"{cert_id}.pdf",mime="application/pdf",use_container_width=True)
    else: st.warning(f"Nessun certificato revisionato collegato a {selected_id}.")
with right:
    st.markdown("### 📈 Exposure history")
    conn=sqlite3.connect(DB_FILE_PATH); history=pd.read_sql_query("SELECT timestamp_utc,tension_n,mbl_n,utilization_pct,duration_s,source,valid,diagnostic FROM session_line_exposure WHERE line_id=? ORDER BY timestamp_utc DESC",conn,params=(selected_id,)); conn.close()
    if history.empty: st.info("Nessuna esposizione storica registrata per questa linea.")
    else:
        history["tension_t"]=history.tension_n/9806.65; history["duration_min"]=history.duration_s/60; a,b=st.columns(2); a.metric("EXPOSURE",f"{history.duration_s.sum()/3600:.2f} h"); b.metric("MAX UTILIZATION",f"{history.utilization_pct.max():.1f}%" if pd.notna(history.utilization_pct.max()) else "N/A"); st.dataframe(history[["timestamp_utc","tension_t","utilization_pct","duration_min","source"]],use_container_width=True,hide_index=True); st.caption("SOLVER_FORECAST = equilibrio statico calcolato; non è un carico misurato.")

st.divider(); st.markdown("## 🤖 AI Visual Inspection")
st.caption("La funzione AI è integrata nel Line Inspector. Analizza solo ciò che è visibile nella foto; l'operatore deve confermare l'osservazione.")
if not ai_is_configured():
    st.warning("GEMINI_API_KEY non configurata nei Secrets di Streamlit.")
else:
    uploaded=st.file_uploader("📷 Carica una foto della linea selezionata",type=["jpg","jpeg","png","webp"],key=f"ai_photo_{selected_id}")
    if uploaded:
        image_bytes=uploaded.getvalue(); st.image(image_bytes,caption=f"Inspection photo — {selected_id}",use_container_width=True)
        if st.button("🔍 Analizza con Gemini",type="primary",use_container_width=True):
            with st.spinner("Analisi visiva in corso…"):
                try:
                    result=inspect_image(image_bytes,uploaded.name,selected_id); save_inspection(result,image_bytes); st.session_state["last_ai_inspection_id"]=result["inspection_id"]; st.session_state["last_ai_inspection_result"]=result
                except Exception as exc: st.error(f"AI inspection failed: {exc}")
    result=st.session_state.get("last_ai_inspection_result")
    if result and str(result.get("line_id"))==selected_id:
        st.markdown("#### Risultato AI — in attesa di conferma")
        a,b,c=st.columns(3); a.metric("Visual severity",result.get("overall_severity","UNDETERMINED")); b.metric("Image quality",result.get("image_quality","UNDETERMINED")); c.metric("Confidence",f"{float(result['confidence'])*100:.0f}%" if result.get("confidence") is not None else "N/A")
        if result.get("summary"): st.info(result["summary"])
        findings=result.get("findings",[])
        if findings: st.dataframe(pd.DataFrame(findings),use_container_width=True,hide_index=True)
        if result.get("retake_requested"): st.warning("L'AI richiede una nuova foto: la qualità/visibilità non è sufficiente.")
        note=st.text_area("Nota operatore / conferma",key=f"ai_note_{result['inspection_id']}")
        if st.button("✅ Conferma osservazione AI",key=f"confirm_{result['inspection_id']}"):
            confirm_inspection(result["inspection_id"],note); result["operator_status"]="OPERATOR_CONFIRMED"; st.session_state["last_ai_inspection_result"]=result; st.success("Osservazione confermata e archiviata nello storico della linea.")

st.divider(); st.markdown("### 🗂️ AI inspection history")
for item in list_inspections(selected_id):
    with st.expander(f"{item['timestamp_utc']} · {item['overall_severity']} · {item['operator_status']}"):
        st.write(item.get("ai_summary", "")); st.caption(f"Provider: {item.get('provider','Google Gemini')} · Model: {item.get('model','')}")
        try: st.dataframe(pd.DataFrame(json.loads(item.get("findings_json") or "[]")),use_container_width=True,hide_index=True)
        except Exception: pass
        img=get_inspection_image(item["inspection_id"])
        if img: st.download_button("⬇️ Foto ispezione originale",data=img,file_name=f"{selected_id}_{item['inspection_id']}.jpg",mime=item.get("image_mime") or "image/jpeg",key=f"download_{item['inspection_id']}")

st.divider(); st.markdown("### 🔎 Engineering data"); st.json({k:line.get(k) for k in ["line_id","line_name","line_type","station_id","cert_id","material","diameter_mm","length_m","mbl_tons","tail_length_m","tail_mbl_tons"] if k in line.index})
