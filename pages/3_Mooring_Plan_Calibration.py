import streamlit as st

from core.mooring_geometry import get_calibration, init_mooring_geometry_db, save_affine_calibration

st.set_page_config(page_title="Mooring Plan Calibration", layout="wide")
init_mooring_geometry_db()

st.title("📐 Mooring Plan → Ship Coordinate Calibration")
st.caption("Tre punti noti del drawing vengono usati per costruire una trasformazione affine. Nessuna coordinata viene inventata dal programma.")

station = st.selectbox("Station", ["Prua (Forward Station)", "Poppa (Aft Station)"])
st.markdown("### Control points")
st.write("Per ogni punto inserisci la posizione in pixel sul drawing e la corrispondente coordinata X/Y della nave.")

points = []
for i in range(1, 4):
    st.markdown(f"**Point {i}**")
    c1,c2,c3,c4 = st.columns(4)
    px = c1.number_input(f"Plan X {i} (px)", value=0.0, key=f"px{i}")
    py = c2.number_input(f"Plan Y {i} (px)", value=0.0, key=f"py{i}")
    sx = c3.number_input(f"Ship X {i} (m)", value=0.0, key=f"sx{i}")
    sy = c4.number_input(f"Ship Y {i} (m)", value=0.0, key=f"sy{i}")
    points.append(((px,py),(sx,sy)))

if st.button("💾 Save calibration", type="primary"):
    try:
        rms = save_affine_calibration(station, [p[0] for p in points], [p[1] for p in points])
        st.success(f"Calibration saved. RMS residual: {rms:.6f} m")
    except ValueError as exc:
        st.error(str(exc))

cal = get_calibration(station)
if cal:
    st.markdown("### Current calibration")
    st.write(f"Status: **{cal.get('status','UNSET')}**")
    st.write(f"Method: **{cal.get('method','N/D')}**")
    rms = cal.get('rms_error_m')
    st.write(f"RMS residual: **{rms:.6f} m**" if rms is not None else "RMS residual: **N/D**")
    st.caption("Il RMS misura solo la qualità matematica dell'interpolazione dei tre punti; non certifica l'accuratezza del drawing o delle coordinate sorgente.")
else:
    st.info("Nessuna calibrazione salvata per questa stazione.")
