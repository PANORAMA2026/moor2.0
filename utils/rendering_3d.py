"""
utils/rendering_3d.py
Generazione grafici e rendering 3D interattivo con Plotly per layout banchina e tensioni.
"""

import plotly.graph_objects as go

def plot_3d_mooring_system(ship_loa: float, ship_beam: float, lines_data: list, bollards_data: list) -> go.Figure:
    """
    Genera il rendering 3D della nave, banchina, bitte e linee d'ormeggio con codice colore per carico % MBL.
    """
    fig = go.Figure()

    # 1. Disegno dello scafo semplificato (Box)
    x_hull = [ship_loa/2, ship_loa/2, -ship_loa/2, -ship_loa/2, ship_loa/2]
    y_hull = [ship_beam/2, -ship_beam/2, -ship_beam/2, ship_beam/2, ship_beam/2]
    fig.add_trace(go.Scatter3d(
        x=x_hull, y=y_hull, z=[0]*5,
        mode='lines',
        line=dict(color='navy', width=5),
        name='Scafo Nave'
    ))

    # 2. Render delle Bitte in banchina
    if bollards_data:
        bx = [b['x'] for b in bollards_data]
        by = [b['y'] for b in bollards_data]
        bz = [b.get('z', 0) for b in bollards_data]
        fig.add_trace(go.Scatter3d(
            x=bx, y=by, z=bz,
            mode='markers',
            marker=dict(size=8, color='black', symbol='diamond'),
            name='Bitte Banchina'
        ))

    # 3. Render Cavi con colore in base alla tensione % MBL
    for line in lines_data:
        pct = line.get('pct_mbl', 0.0)
        color = 'green' if pct < 50 else ('orange' if pct < 55 else 'red')
        
        fig.add_trace(go.Scatter3d(
            x=[line['x_chock'], line['x_bollard']],
            y=[line['y_chock'], line['y_bollard']],
            z=[line.get('z_chock', 2.0), line.get('z_bollard', 0.0)],
            mode='lines+text',
            line=dict(color=color, width=4),
            name=f"Linea {line.get('id', '')}"
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title='X (m) [Longitudinale]',
            yaxis_title='Y (m) [Trasversale]',
            zaxis_title='Z (m) [Quota]'
        ),
        margin=dict(l=0, r=0, b=0, t=30)
    )
    return fig
