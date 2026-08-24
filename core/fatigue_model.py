"""
core/fatigue_model.py
Modello di calcolo dell'usura residua e degrado del cavo basato sul carico % MBL accumulate.
"""

def update_line_health(current_health: float, hours: float, avg_pct_mbl: float) -> float:
    """
    Calcola l'indice di salute residua (%) in base alle ore di lavoro e alla sollecitazione subita.
    """
    # Fattore di penalità per carichi elevati (> 50% MBL)
    penalty_factor = 1.0
    if avg_pct_mbl > 55.0:
        penalty_factor = 3.5
    elif avg_pct_mbl > 45.0:
        penalty_factor = 1.8
        
    degradation = (hours * 0.005) * penalty_factor
    new_health = max(0.0, current_health - degradation)
    return round(new_health, 2)
