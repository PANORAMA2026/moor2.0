"""Berth layout UI: fixed berth geometry + longitudinal ship offset."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config.constants import DEFAULT_SHIP
from core.berth_profiles import get_berth_profile, list_berth_profiles, bollard_points_as_dicts
from database.db_manager import load_port_bollards_from_db


def _profile_dataframe(selected_port: str):
    if selected_port in list_berth_profiles():
        profile = get_berth_profile(selected_port)
        return pd.DataFrame(bollard_points_as_dicts(selected_port)), float(profile["survey_water_level_m"])
    df = load_port_bollards_from_db(selected_port)
    if df.empty:
        return pd.DataFrame(), None
    return df.rename(columns={"X_Coordinata_m":"x_m","Y_Coordinata_m":"y_m","Z_Altezza_m":"z_m"}), None


def _figure(ship, bollards, offset):
    loa = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    beam = float(ship.get("Beam", DEFAULT_SHIP["Beam"]))
    fig = go.Figure()
    x0 = float(offset)
    fig.add_trace(go.Scatter(x=[x0-loa/2,x0+loa/2,x0+loa/2,x0-loa/2,x0-loa/2], y=[-beam/2,-beam/2,beam/2,beam/2,-beam/2], mode="lines", name="Ship model", line=dict(width=3)))
    if not bollards.empty and {"x_m","y_m"}.issubset(bollards.columns):
        fig.add_trace(go.Scatter(x=bollards.x_m, y=bollards.y_m, mode="markers+text", text=bollards.bollard_id, textposition="top center", marker=dict(size=10,symbol="square"), name="Fixed bollards"))
        yb=float(bollards.y_m.median()); xmin=min(float(bollards.x_m.min()),x0-loa/2)-20; xmax=max(float(bollards.x_m.max()),x0+loa/2)+20
        fig.add_trace(go.Scatter(x=[xmin,xmax],y=[yb,yb],mode="lines",name="Berth reference",line=dict(width=2,dash="dash")))
    fig.update_layout(height=560,margin=dict(l=10,r=10,t=25,b=10),xaxis_title="X — longitudinale (m)",yaxis_title="Y — trasversale (m)",yaxis=dict(scaleanchor="x",scaleratio=1),legend=dict(orientation="h"))
    return fig


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")
    for k,v in DEFAULT_SHIP.items(): ship_dict.setdefault(k,v)
    offset=float(st.session_state.get("offset_fugro_m",0.0))
    df, survey_level=_profile_dataframe(selected_port)
    real=selected_port in list_berth_profiles() and not df.empty
    if real:
        st.success("✅ Berth Profile reale attivo — bitte fisse sulla banchina")
        st.caption(f"Rilievo: livello acqua +{survey_level:.2f} m. La nave viene traslata esclusivamente lungo l'asse longitudinale.")
    else:
        st.info("ℹ️ Nessun Berth Profile di rilievo disponibile per questa banchina.")
    c1,c2,c3=st.columns(3)
    c1.metric("Nave",ship_dict.get("Name","N/A")); c2.metric("Longitudinal Offset",f"{offset:+.1f} m"); c3.metric("Bitte",str(len(df)))
    new_offset=st.number_input("Longitudinal Offset — + verso PRUA / − verso POPPA (m)",value=offset,step=0.5,format="%.1f",key="berth_longitudinal_offset")
    st.session_state["offset_fugro_m"]=float(new_offset)
    if not df.empty:
        st.subheader("📐 Coordinate delle bitte")
        cols=[c for c in ["bollard_id","measurement_station","side","x_m","y_m","z_m","survey_water_level_m"] if c in df.columns]
        st.dataframe(df[cols],use_container_width=True,hide_index=True)
        st.subheader("🗺️ Banchina fissa / nave mobile")
        st.plotly_chart(_figure(ship_dict,df,float(new_offset)),use_container_width=True)
        if real: st.caption("Le coordinate delle bitte non cambiano con l'offset. Cambia soltanto la posizione longitudinale del modello nave.")
    else: st.warning("Nessuna geometria di banchina disponibile per questo porto.")
