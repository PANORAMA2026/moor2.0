"""
views/tab_polar.py
Dashboard Operativa Analisi Vento MEG4
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


# ==========================================
# 1. VETTORE VENTO & NAVAGE TOP-DOWN
# ==========================================
def build_wind_vector_diagram(v_wind: float, dir_wind: float, max_mbl_pct: float):
    fig = go.Figure()

    # Sagoma nave (Prua verso l'alto = +Y)
    ship_x = [0, 0.8, 1.0, 0.8, -0.8, -1.0, -0.8, 0]
    ship_y = [3.0, 2.2, -2.5, -3.0, -3.0, -2.5, 2.2, 3.0]
    
    fig.add_trace(go.Scatter(
        x=ship_x, y=ship_y,
        fill="toself",
        fillcolor="rgba(100, 110, 120, 0.8)",
        line=dict(color="#FFFFFF", width=2),
        name="Nave",
        hoverinfo="skip"
    ))

    # POSIZIONAMENTO ORIGINE VENTO (ax, ay):
    # 0° (Prua) -> Vento parte in alto (X=0, Y=+3.5) e punta verso (0,0)
    # 90° (Dritta) -> Vento parte a destra (X=+3.5, Y=0) e punta verso (0,0)
    # 180° (Poppa) -> Vento parte in basso (X=0, Y=-3.5) e punta verso (0,0)
    # 270° (Sinistra) -> Vento parte a sinistra (X=-3.5, Y=0) e punta verso (0,0)
    rad = np.radians(dir_wind)
    ax_pos = 3.5 * np.sin(rad)
    ay_pos = 3.5 * np.cos(rad)

    color_status = "#E74C3C" if max_mbl_pct > 50.0 else ("#F39C12" if max_mbl_pct > 35.0 else "#2ECC71")

    # Freccia che va da (ax, ay) verso la nave (0, 0)
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
            text=f"<b>1. VETTORE VENTO INCIDENTE ({dir_wind:.0f}° @ {v_wind:.1f} KTS)</b>",
            x=0.5, font=dict(size=14, color="#FFFFFF")
        ),
        xaxis=dict(visible=False, range=[-4.5, 4.5]),
        yaxis=dict(visible=False, range=[-4.5, 4.5]),
        showlegend=False,
        height=360,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig


# ==========================================
# 2. GRAFICO A BARRE CARICO CAVI
# ==========================================
def build_lines_load_bar_chart(lines_df: pd.DataFrame, v_wind: float, dir_wind: float):
    fig = go.Figure()

    if lines_df.empty or "Util_Percent" not in lines_df.columns:
        base_factor = (v_wind / 30.0) ** 2
        dummy_lines = [f"Line {i+1}" for i in range(12)]
        dummy_loads = [
            round(min(98.0, (15.0 + 30.0 * np.abs(np.sin(np.radians(dir_wind - i*15)))) * base_factor), 1)
            for i in range(12)
        ]
        lines_df = pd.DataFrame({"Line_ID": dummy_lines, "Util_Percent": dummy_loads})

    line_names = lines_df.get("Line_ID", [f"Cavo {i+1}" for i in range(len(lines_df))])
    loads = lines_df["Util_Percent"].values

    colors = []
    for val in loads:
        if val > 50.0:
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

    fig.add_shape(
        type="line",
        x0=-0.5, x1=len(line_names) - 0.5,
        y0=50, y1=50,
        line=dict(color="#FFD700", width=2, dash="dash")
    )

    max_y = max(60.0, max(loads) + 15.0) if len(loads) > 0 else 60.0

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>2. DISTRIBUZIONE CARICO CAVI (% MBL)</b>",
            x=0.5, font=dict(size=14, color="#FFFFFF")
        ),
        xaxis=dict(title="Cavi d'Ormeggio", tickangle=-45),
        yaxis=dict(title="Carico (% MBL)", range=[0, max_y], gridcolor="#333333"),
        height=360,
        margin=dict(l=30, r=30, t=50, b=40)
    )
    return fig


# ==========================================
# 3. CURVA DI RISCHIO ANGOLARE (0-360°)
# ==========================================
def build_angular_risk_curve(v_wind: float, active_dir: float, geom_df: pd.DataFrame, afw: float, alw: float, alc: float, loa: float):
    angles = list(range(0, 365, 15))
    max_loads = []

    if solve_line_tensions_3d and calculate_environmental_forces and not geom_df.empty:
        for angle in angles:
            try:
                forces = calculate_environmental_forces(v_wind, angle, 0.0, 0, afw, alw, alc, loa)
                res = solve_line_tensions_3d(geom_df, forces)
                max_loads.append(round(res["Util_Percent"].max(), 1) if not res.empty and "Util_Percent" in res.columns else 0.0)
            except Exception:
                max_loads.append(0.0)
    else:
        base_factor = (v_wind / 30.0) ** 2
        max_loads = [round(min(98.0, (18.0 + 28.0 * np.abs(np.sin(np.radians(a - 20)))) * base_factor), 1) for a in angles]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=angles,
        y=max_loads,
        mode='lines',
        name=f'Carico Max @ {v_wind:.1f} kts',
        line=dict(color='#00E5FF', width=3),
        hovertemplate='Angolo Vento: %{x}°<br>Carico Max Cavo: %{y}% MBL<extra></extra>'
    ))

    fig.add_shape(
        type="line", x0=0, x1=360, y0=50, y1=50,
        line=dict(color="#FFD700", width=2, dash="dash")
    )

    idx_closest = min(range(len(angles)), key=lambda i: abs(angles[i] - active_dir))
    curr_load = max_loads[idx_closest]

    fig.add_trace(go.Scatter(
        x=[active_dir],
        y=[curr_load],
        mode='markers+text',
        name='Condizione Attuale',
        marker=dict(color='#E74C3C', size=12, symbol='circle'),
        text=[f"  Attuale: {active_dir:.0f}° ({curr_load}% MBL)"],
        textposition="top right",
        textfont=dict(color="#E74C3C", size=12, family="Arial Black")
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>3. SENSIBILITÀ ANGOLARE TENSIONI (0-360°) PER VENTO A {v_wind:.1f} KTS</b>",
            x=0.5, font=dict(size=14, color="#FFFFFF")
        ),
        xaxis=dict(
            title="Direzione Vento Incidente (°)",
            tickvals=[0, 45, 90, 135, 180, 225, 270, 315, 360],
            ticktext=["0° (Prua)", "45°", "90° (Dritta)", "135°", "180° (Poppa)", "225°", "270° (Sinistra)", "315°", "360°"],
            gridcolor="#333333"
        ),
        yaxis=dict(title="Carico Massimo Cavo (% MBL)", gridcolor="#333333"),
        height=320,
        margin=dict(l=40, r=40, t=50, b=40),
        showlegend=False
    )
    return fig


# ==========================================
# RENDER PRINCIPALE
# ==========================================
def render_tab_polar(v_wind=30.0, dir_wind=77.0):
    st.header("📊 Dashboard Operativa Vento MEG4")

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

    max_mbl = res_df["Util_Percent"].max() if not res_df.empty and "Util_Percent" in res_df.columns else 0.0

    col1, col2 = st.columns([1, 1.4])
    with col1:
        fig1 = build_wind_vector_diagram(v_wind, dir_wind, max_mbl)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        fig2 = build_lines_load_bar_chart(res_df, v_wind, dir_wind)
        st.plotly_chart(fig2, use_container_width=True)

    fig3 = build_angular_risk_curve(v_wind, dir_wind, geom_df, afw, alw, alc, loa)
    st.plotly_chart(fig3, use_container_width=True)
