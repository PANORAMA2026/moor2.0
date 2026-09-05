"""Source-controlled station equipment import helpers."""
from core.mooring_geometry import upsert_component
from core.mooring_station_catalog import AFT_EQUIPMENT, DRAWING_ID as AFT_DRAWING_ID
from core.mooring_fwd_catalog import FWD_EQUIPMENT, DRAWING_ID as FWD_DRAWING_ID


def _seed(station_name, entries, drawing_id):
    count = 0
    for entry in entries:
        qty = int(entry.get("quantity", 1))
        base = str(entry["piece_number"]).replace("/", "-").replace("*", "X")
        for idx in range(1, qty + 1):
            component_id = f"{base}-{idx:02d}" if qty > 1 else base
            upsert_component(
                station_name=station_name,
                component_id=component_id,
                component_type=entry["type"],
                source_item=entry.get("item"),
                source_piece_number=entry.get("piece_number"),
                source_drawing=drawing_id,
                notes=entry.get("description", ""),
            )
            count += 1
    return count


def seed_fwd(station_name="Prua (Forward Station)"):
    return _seed(station_name, FWD_EQUIPMENT, FWD_DRAWING_ID)


def seed_aft(station_name="Poppa (Aft Station)"):
    return _seed(station_name, AFT_EQUIPMENT, AFT_DRAWING_ID)
