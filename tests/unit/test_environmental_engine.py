from datetime import datetime, timezone
from core.environmental_engine import VesselHydroGeometry, calculate_environmental_loads
from core.environmental_state import EnvironmentalState

class Wind:
    def coefficients(self, direction): return 1.0,0.0,0.0
class Current:
    def coefficients(self, direction): return 1.0,0.0,0.0

def test_wind_current_and_tidal_component():
    state=EnvironmentalState(timestamp_utc=datetime.now(timezone.utc),wind_speed_mps=10.0,wind_direction_from_deg_true=0.0,current_speed_mps=1.0,current_direction_to_deg_true=0.0,tidal_current_u_mps=0.3,tidal_current_v_mps=0.4,provider='TEST',source_kind='FORECAST')
    vessel=VesselHydroGeometry(100.0,200.0,50.0,500.0,300.0)
    result=calculate_environmental_loads(state,vessel,0.0,Wind(),Current())
    assert result.wind.fx_n>0 and result.current.fx_n>0
    assert result.total.fx_n==result.wind.fx_n+result.current.fx_n
    assert abs(result.tidal_current_speed_mps-0.5)<1e-9

def test_tidal_current_fallback():
    state=EnvironmentalState(timestamp_utc=datetime.now(timezone.utc),tidal_current_u_mps=0.0,tidal_current_v_mps=0.5,provider='TEST',source_kind='FORECAST')
    vessel=VesselHydroGeometry(100.0,200.0,50.0,500.0,300.0)
    result=calculate_environmental_loads(state,vessel,0.0,Wind(),Current())
    assert abs(result.current_speed_mps-0.5)<1e-9
    assert result.current.fx_n>0
