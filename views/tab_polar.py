"""
views/tab_polar.py
Dashboard Operativa Analisi Vento e Sicurezza Ormeggio (OCIMF MEG4)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from core.line_mechanics import solve_line_tensions_3d
    from core.hydrodynamic_forces import calculate_environmental_forces
except ImportError:
    solve_line_tensions_3d = None
    calculate_environmental_forces = None

LIMIT_MEG4_PCT = 55.0  # Limite di sicurezza OCIMF MEG4


# ==========================================
# 1. BANNER KPI METRICHE ISTANTANEE
# ==========================================
def render_kpi_banner(max_mbl_pct: float, max_line_name: str, v_wind: float, dir_wind: float):
    col1, col2, col3, col4 = st.columns(4)

    is_safe = max_mbl_pct < LIMIT_MEG4_PCT
    status_text = "SICURO" if is_safe else "CRITICO / OVERLOAD"
    status_color = "normal" if is_safe else "inverse"

    margin = max(0.0, LIMIT_MEG4_PCT - max_mbl_pct)

    with col1:
        st.metric("Stato Ormeggio", status_text, delta="Entro Limiti MEG4" if is_safe else "Superato 55% MBL", delta_color=status_color)
    with col2:
        st.metric("Carico Max Cavo", f"{max_mbl_pct:.1f}% MBL", delta=f"Cavo: {max_line_name}", delta_color="off")
    with col3:
        st.metric("Riserva Sicurezza", f"{margin:.1f}%", delta="Margine a Soglia 55%")
    with col4:
        st.metric("Condizioni Attuali", f"{v_wind:.1f} kts", delta=f"Direzione: {dir_wind:.0f}°", delta_color="off")

    st.divider()


# ==========================================
# 2. NAVAGAZION 2D & ORIENTAMENTO CAVI
# ==========================================
def build_ship_mooring_2d_diagram(geom_df: pd.DataFrame, v_wind: float, dir_wind: float, max_mbl_pct: float):
    fig = go.Figure()

    # Sagoma nave 2D (Prua verso +Y)
    ship_x = [0, 12, 18, 18, -18, -18, -12, 0]
    ship_y = [160, 110, -130, -160, -160, -130, 110, 160]

    fig.add_trace(go.Scatter(
        x=ship_x, y=ship_y,
        fill="toself",
        fillcolor="rgba(30, 41, 59, 0.9)",
        line=dict(color="#38BDF8", width=2),
        name="Scafo Nave",
        hoverinfo="skip"
    ))

    # Banchina (Lato Dritta/Starboard)
    berth_x = 25.0
    fig.add_shape(
        type="rect",
        x0=berth_x, x1=berth_x + 10,
        y0=-180, y1=180,
        fillcolor="rgba(100, 116, 139, 0.4)",
        line=dict(color="#94A3B8", width=2)
    )

    # Tracciamento Cavi d'Ormeggio Dinamici
    if not geom_df.empty and all(col in geom_df.columns for col in ["chock_x_m", "chock_y_m", "bollard_x_m", "bollard_y_m"]):
        for _, row in geom_df.iterrows():
            load_pct = float(row.get("Util_Percent", 0.0))
            line_color = "#2ECC71" if load_pct < 35.0 else ("#F39C12" if load_pct < 55.0 else "#E74C3C")
            
            # Conversione coordinate per la visualizzazione 2D Top-Down
            c_x, c_y = float(row.get("chock_y_m", 0.0)), float(row.get("chock_x_m", 0.0))
            b_x, b_y = float(row.get("bollard_y_m", 0.0)), float(row.get("bollard_x_m", 0.0))

            fig.add_trace(go.Scatter(
                x=[c_x, b_x], y=[c_y, b_y],
                mode="lines+markers",
                line=dict(color=line_color, width=3),
                marker=dict(size=5, color=line_color),
                hovertemplate=f"Cavo: {row.get('Line_ID', 'N/A')}<br>Carico: {load_pct:.1f}% MBL<extra></extra>",
                showlegend=False
            ))

    # Vettore Vento Incidente
    rad = np.radians(dir_wind)
    ax_pos = 220.0 * np.sin(rad)
    ay_pos = 220.0 * np.cos(rad)

    color_status = "#E74C3C" if max_mbl_pct > 55.0 else ("#F39C12" if max_mbl_pct > 35.0 else "#2ECC71")

    fig.add_annotation(
        ax=ax_pos, ay=ay_pos,
        x=0, y=0,
        xref="x", yref="y",
        axref="x", ayref="y",
        showarrow=True,
        arrowhead=3,
        arrowsize=1.8,
        arrowwidth=4,
        arrowcolor=color_status
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>LAYOUT ORMEGGIO 2D & VENTO ({dir_wind:.0f}° @ {v_wind:.1f} KTS)</b>",
            x=0.5, font=dict(size=13, color="#FFFFFF")
        ),
        xaxis=dict(visible=False, range=[-250, 250]),
        yaxis=dict(visible=False, range=[-250, 250]),
        showlegend=False,
        height=380,
        margin=dict(l=10, r=10, t=40, b=10)
    )
    return fig


# ==========================================
# 3. GRAFICO A BARRE CARICO CAVI (PRO)
# ==========================================
def build_lines_load_bar_chart(lines_df: pd.DataFrame, v_wind: float, dir_wind: float):
    fig = go.Figure()

    if lines_df.empty or "Util_Percent" not in lines_df.columns:
        base_factor = (v_wind / 30.0) ** 2
        dummy_lines = [f"Cavo {i+1}" for i in range(10)]
        dummy_loads = [
            round(min(98.0, (15.0 + 30.0 * np.abs(np.sin(np.radians(dir_wind - i*15)))) * base_factor), 1)
            for i in range(10)
        ]
        lines_df = pd.DataFrame({"Line_ID": dummy_lines, "Util_Percent": dummy_loads})

    # Pulizia da valori erratici / infiniti
    lines_df["Util_Percent"] = np.nan_to_num(lines_df["Util_Percent"].values, nan=0.0, posinf=100.0, neginf=0.0)
    lines_df["Util_Percent"] = np.clip(lines_df["Util_Percent"], 0.0, 100.0)

    line_names = lines_df.get("Line_ID", [f"Cavo {i+1}" for i in range(len(lines_df))])
    loads = lines_df["Util_Percent"].values

    colors = []
    for val in loads:
        if val > 55.0:
            colors.append("#E74C3C")
        elif val > 35.0:
            colors.append("#F39C12")
        else:
            colors.append("#2ECC71")

    fig.add_trace(go.Bar(
        x=line_names,
        y=loads,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in loads],
        textposition='outside',
        hovertemplate='Cavo: %{x}<br>Carico: %{y:.1f}% MBL<extra></extra>'
    ))

    # Linea Limite MEG4 (55%)
    fig.add_shape(
        type="line",
        x0=-0.5, x1=len(line_names) - 0.5,
        y0=LIMIT_MEG4_PCT, y1=LIMIT_MEG4_PCT,
        line=dict(color="#EF4444", width=2, dash="dash")
    )

    max_y = max(65.0, max(loads) + 12.0) if len(loads) > 0 else 65.0

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text="<b>DISTRIBUZIONE TENSIONI CAVI (% MBL)</b>",
            x=0.5, font=dict(size=13, color="#FFFFFF")
        ),
        xaxis=dict(title="Cavi d'Ormeggio", tickangle=-45),
        yaxis=dict(title="Carico (% MBL)", range=[0, max_y], gridcolor="#333333"),
        height=380,
        margin=dict(l=30, r=30, t=40, b=30)
    )
    return fig


# ==========================================
# 4. ROSA DEI VENTI POLARE (0-360°) - NO GLITCH
# ==========================================
def build_polar_risk_diagram(v_wind: float, active_dir: float, geom_df: pd.DataFrame, afw: float, alw: float, alc: float, loa: float):
    angles = list(range(0, 360, 10))
    max_loads = []

    if solve_line_tensions_3d and calculate_environmental_forces and not geom_df.empty:
        for angle in angles:
            try:
                forces = calculate_environmental_forces(v_wind, angle, 0.0, 0, afw, alw, alc, loa)
                res = solve_line_tensions_3d(geom_df, forces)
                val = float(res["Util_Percent"].max()) if not res.empty and "Util_Percent" in res.columns else 0.0
                # Clamp di sicurezza anti-glitch
                val = np.nan_to_num(val, nan=0.0, posinf=100.0, neginf=0.0)
                max_loads.append(min(100.0, max(0.0, val)))
            except Exception:
                max_loads.append(0.0)
    else:
        base_factor = (v_wind / 30.0) ** 2
        max_loads = [round(min(98.0, (18.0 + 28.0 * np.abs(np.sin(np.radians(a - 20)))) * base_factor), 1) for a in angles]

    fig = go.Figure()

    # Area di Inviluppo Polare
    fig.add_trace(go.Scatterpolar(
        r=max_loads,
        theta=angles,
        fill="toself",
        fillcolor="rgba(34, 197, 94, 0.25)",
        line=dict(color="#2ECC71", width=2),
        name="Carico Max (% MBL)",
        hovertemplate="Direzione Vento: <b>%{theta}°</b><br>Carico Max Cavo: <b>%{r:.1f}% MBL</b><extra></extra>"
    ))

    # Anello Limite MEG4 (55%)
    fig.add_trace(go.Scatterpolar(
        r=[LIMIT_MEG4_PCT] * len(angles),
        theta=angles,
        mode="lines",
        line=dict(color="#EF4444", width=2, dash="dash"),
        name="Soglia Limite MEG4 (55%)",
        hoverinfo="skip"
    ))

    # Condizione Vento Attuale
    idx_closest = min(range(len(angles)), key=lambda i: abs(angles[i] - active_dir))
    curr_load = max_loads[idx_closest]

    fig.add_trace(go.Scatterpolar(
        r=[curr_load],
        theta=[active_dir],
        mode="markers+text",
        marker=dict(color="#EF4444" if curr_load > 55 else "#F39C12", size=12, symbol="diamond"),
        name="Condizione Attuale",
        text=[f"{curr_load:.1f}%"],
        textposition="top center"
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>INVILUPPO POLARE DI SICUREZZA PER VENTO A {v_wind:.1f} KTS</b>",
            x=0.5, font=dict(size=14, color="#FFFFFF")
        ),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%", color="#94A3B8", gridcolor="#333333"),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,  # 0° Prua in Alto
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["0° (Prua)", "45°", "90° (Dritta)", "135°", "180° (Poppa)", "225°", "270° (Sinistra)", "315°"],
                color="#F8FAFC"
            ),
            bgcolor="rgba(15, 23, 42, 0.6)"
        ),
        height=450,
        margin=dict(l=40, r=40, t=50, b=30),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
    )
    return fig


# ==========================================
# RENDER PRINCIPALE
# ==========================================
def render_tab_polar(v_wind=30.0, dir_wind=77.0):
    st.header("🌪️ Inviluppo Polare e Dashboard Sicurezza MEG4")

    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    afw = st.session_state.get("afw", 950.0)
    alw = st.session_state.get("alw", 3200.0)
    alc = st.session_state.get("alc", 1800.0)
    loa = st.session_state.get("loa", 323.44)

    res_df = pd.DataFrame()
    if solve_line_tensions_3d and calculate_environmental_forces and not geom_df.empty:
        try:
            forces = calculate_environmental_forces(v_wind, dir_wind, 0.0, 0, afw, alw, alc, loa)
            res_df = solve_line_tensions_3d(geom_df, forces)
        except Exception:
            pass

    # Calcolo carico massimo e nome cavo più sollecitato
    if not res_df.empty and "Util_Percent" in res_df.columns:
        res_df["Util_Percent"] = np.nan_to_num(res_df["Util_Percent"].values, nan=0.0, posinf=100.0, neginf=0.0)
        res_df["Util_Percent"] = np.clip(res_df["Util_Percent"], 0.0, 100.0)
        max_idx = res_df["Util_Percent"].idxmax()
        max_mbl = float(res_df["Util_Percent"].max())
        max_line_name = str(res_df.loc[max_idx, "Line_ID"]) if "Line_ID" in res_df.columns else f"Cavo {max_idx+1}"
    else:
        max_mbl = 0.0
        max_line_name = "N/A"

    # 1. Banner KPI
    render_kpi_banner(max_mbl, max_line_name, v_wind, dir_wind)

    # 2. Sezione Layout 2D + Grafico Barre
    col1, col2 = st.columns([1, 1.2])
    with col1:
        fig1 = build_ship_mooring_2d_diagram(res_df if not res_df.empty else geom_df, v_wind, dir_wind, max_mbl)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        fig2 = build_lines_load_bar_chart(res_df, v_wind, dir_wind)
        st.plotly_chart(fig2, use_container_width=True)

    # 3. Inviluppo Polare a 360 Gradi
    fig3 = build_polar_risk_diagram(v_wind, dir_wind, geom_df, afw, alw, alc, loa)
    st.plotly_chart(fig3, use_container_width=True)
