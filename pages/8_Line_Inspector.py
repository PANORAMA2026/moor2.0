"""Single-line digital record: live calculation + certificate + exposure history."""
from __future__ import annotations

import json
import sqlite3
import pandas as pd
import streamlit as st

from config.constants import DB_FILE_PATH
from database.certificate_repository import get_certificate_pdf, load_certificate_records

st.set_page_config(page_title="Line Inspector — OpenMooring", layout="wide")

st.title("🪢 Line Inspector")
st.caption("Una linea, un record: configurazione → certificato → tensione calcolata → esposizione storica.")

inventory = st.session_state.get("lines_inventory", pd.DataFrame())
results = st.session_state.get("latest_mooring_results", pd.DataFrame())
cert_records = pd.DataFrame(load_certificate_records())

if inventory is None or inventory.empty:
    st.warning("Line inventory non disponibile.")
    st.stop()

id_col = "line_id" if "line_id" in inventory.columns else None
name_col = "line_name" if "line_name" in inventory.columns else None
if id_col is None:
    st.error("Line inventory senza line_id.")
    st.stop()

inventory = inventory.copy()
inventory[id_col] = inventory[id_col].astype(str)
labels = inventory.apply(
    lambda r: f"{r[id_col]} — {r[name_col]}" if name_col and str(r[name_col]).strip() else str(r[id_col]),
    axis=1,
).tolist()
choice = st.selectbox("Seleziona linea", labels)
selected_id = str(inventory.iloc[labels.index(choice)][id_col])
line = inventory[inventory[id_col] == selected_id].iloc[0]

live = pd.DataFrame()
if isinstance(results, pd.DataFrame) and not results.empty and "line_id" in results.columns:
    live = results[results["line_id"].astype(str) == selected_id].copy()

cert_id = str(line.get("cert_id", "")).strip()
cert = cert_records[cert_records["cert_id"].astype(str) == cert_id].iloc[0].to_dict() if cert_id and not cert_records.empty and "cert_id" in cert_records.columns and (cert_records["cert_id"].astype(str) == cert_id).any() else None

c1, c2, c3, c4 = st.columns(4)
if not live.empty and pd.notna(live.iloc[0].get("Tension_tons")):
    c1.metric("CURRENT TENSION", f"{float(live.iloc[0]['Tension_tons']):.2f} t")
    c2.metric("UTILIZATION", f"{float(live.iloc[0].get('Util_Percent', float('nan'))):.1f}%")
    c3.metric("MBL", f"{float(live.iloc[0].get('mbl_tons', line.get('mbl_tons', 0))):.2f} t")
    c4.metric("SOLVER", str(live.iloc[0].get("Solver_Status", "N/A")))
else:
    c1.metric("CURRENT TENSION", "N/A")
    c2.metric("UTILIZATION", "N/A")
    c3.metric("MBL", f"{float(line.get('mbl_tons', 0) or 0):.2f} t" if pd.notna(line.get('mbl_tons', 0)) else "N/A")
    c4.metric("SOLVER", "No current result")

st.markdown("### 🔗 Mooring connection")
route = [line.get(k, "") for k in ["winch_id", "fairlead_id", "bollard_id"]]
st.info(f"**Winch:** {route[0] or 'N/A'}   →   **Fairlead:** {route[1] or 'N/A'}   →   **Bollard:** {route[2] or 'N/A'}")

left, right = st.columns(2)
with left:
    st.markdown("### 📜 Certificate")
    if cert:
        fields = {
            "Certificate ID": cert.get("cert_id"),
            "Manufacturer": cert.get("manufacturer"),
            "Material / Grade": cert.get("material_grade"),
            "Diameter": f"{cert.get('diameter_mm')} mm",
            "Length": f"{cert.get('length_m')} m",
            "Ship Design MBL": f"{cert.get('ship_design_mbl_t')} t" if cert.get("ship_design_mbl_t") else "N/A",
            "LDBF": f"{cert.get('ldbf_t')} t" if cert.get("ldbf_t") else "N/A",
            "Review": cert.get("review_status"),
        }
        st.dataframe(pd.DataFrame(list(fields.items()), columns=["Field", "Value"]), use_container_width=True, hide_index=True)
        document = get_certificate_pdf(cert_id)
        if document and document.get("source_pdf_blob"):
            st.caption(f"Original PDF · SHA-256 {document.get('source_pdf_sha256', '')}")
            st.download_button(
                "⬇️ Apri PDF certificato",
                data=document["source_pdf_blob"],
                file_name=document.get("source_pdf_filename") or f"{cert_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    else:
        st.warning(f"Nessun certificato revisionato collegato a {selected_id}.")

with right:
    st.markdown("### 📈 Exposure history")
    conn = sqlite3.connect(DB_FILE_PATH)
    history = pd.read_sql_query(
        """SELECT timestamp_utc, tension_n, mbl_n, utilization_pct, duration_s, source, valid, diagnostic
           FROM session_line_exposure WHERE line_id = ? ORDER BY timestamp_utc DESC""",
        conn, params=(selected_id,),
    )
    conn.close()
    if history.empty:
        st.info("Nessuna esposizione storica registrata per questa linea.")
    else:
        history["tension_t"] = history["tension_n"] / 9806.65
        history["mbl_t"] = history["mbl_n"] / 9806.65
        history["duration_min"] = history["duration_s"] / 60.0
        total_h = history["duration_s"].sum() / 3600.0
        max_util = history["utilization_pct"].max()
        a, b = st.columns(2)
        a.metric("EXPOSURE", f"{total_h:.2f} h")
        b.metric("MAX UTILIZATION", f"{max_util:.1f}%" if pd.notna(max_util) else "N/A")
        st.dataframe(
            history[["timestamp_utc", "tension_t", "utilization_pct", "duration_min", "source"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Le esposizioni SOLVER_FORECAST sono calcolate da equilibrio statico e non rappresentano un carico misurato.")

st.divider()
st.markdown("### 🔎 Engineering data")
engineering = {k: line.get(k) for k in ["line_id", "line_name", "line_type", "station_id", "winch_id", "cert_id", "material", "diameter_mm", "length_m", "mbl_tons", "tail_length_m", "tail_mbl_tons"] if k in line.index}
st.json(engineering)
