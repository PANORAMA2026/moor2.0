"""
views/tab_mooring_engine.py
Pannello di controllo per il tracciamento automatico dell'ormeggio,
campionamento ogni 30 minuti, trigger per variazione vento >= 6 kts e storico cime.
"""

import streamlit as st
import pandas as pd
from core.auto_mooring_engine import process_automatic_mooring_logging
from database.db_manager import get_port_mooring_setups, get_line_history


def render_tab_mooring_engine():
    st.header("⚡ Monitoraggio Automazione Ormeggio & Storico Cime")

    auto_data = process_automatic_mooring_logging()

    if not auto_data or auto_data["status"] in ["IN_TRANSIT", "NO_SCHEDULE"]:
        st.info(
            "⚓ **Stato Attuale:** Nave in Navigazione. "
            "Il sistema avvierà automaticamente il tracciamento e il salvataggio dei dati "
            "non appena la nave entrerà nella finestra oraria d'arrivo in porto (ETA)."
        )

        st.markdown("---")
        st.subheader("📚 Storico Accumulato Inventario Cime di Bordo")
        df_history = get_line_history()
        if not df_history.empty:
            st.dataframe(df_history, use_container_width=True)
        else:
            st.caption("Nessun dato registrato nello storico dell'inventario.")
        return

    if auto_data["status"] == "WEATHER_UNAVAILABLE":
        st.warning(
            f"⚠️ **Meteo non disponibile per {auto_data['port']}.** "
            "Nessun valore meteo simulato verrà utilizzato e nessun campionamento automatico "
            "verrà registrato finché non sarà disponibile una sorgente valida o un override manuale."
        )

    st.success(f"🟢 **POSIZIONE RILEVATA IN AUTOMATICO:** {auto_data['port']}")

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Ore Totali in Porto", f"{auto_data['hours_in_port']:.2f} h")
    wind_display = "N/D" if auto_data.get("current_wind") is None else f"{auto_data['current_wind']:.1f} kts"
    col_m2.metric("Vento Attuale", wind_display, delta=auto_data["weather_src"])
    col_m3.metric("Ultimo Sync DB", auto_data["last_sync_time"])
    col_m4.metric("Stato Trigger", auto_data["last_trigger"])

    st.markdown("---")
    st.subheader("⚙️ Pannello Gestione Eccezioni (Opzionale)")
    st.caption(
        "Il sistema effettua il salvataggio automatico su DB ogni 30 minuti o al verificarsi "
        "di una variazione del vento >= 6 kts. Utilizza queste opzioni solo per variazioni manuali."
    )

    port_name = auto_data['port']
    available_setups = get_port_mooring_setups(port_name)
    col_opt1, col_opt2 = st.columns(2)

    with col_opt1:
        if available_setups:
            setup_list = list(available_setups.keys())
            current_override = st.session_state.get(f"override_setup_{port_name}", setup_list[0])
            new_setup = st.selectbox(
                "Mooring Setup Selezionato per questo ormeggio",
                setup_list,
                index=setup_list.index(current_override) if current_override in setup_list else 0,
            )
            if new_setup != current_override:
                st.session_state[f"override_setup_{port_name}"] = new_setup
                st.rerun()
        else:
            st.warning("Nessun setup di ormeggio personalizzato salvato per questo porto. Verrà usato il formato standard.")

    with col_opt2:
        use_manual_weather = st.checkbox("Forza Meteo Manuale", key=f"chk_w_{port_name}")
        if use_manual_weather:
            default_wind = float(auto_data["current_wind"] or 0.0)
            m_wind = st.number_input("Velocità Vento Manuale (kts)", min_value=0.0, value=default_wind)
            st.session_state[f"weather_override_{port_name}"] = {"wind_speed": m_wind}
        else:
            if f"weather_override_{port_name}" in st.session_state:
                del st.session_state[f"weather_override_{port_name}"]

    st.markdown("---")
    st.subheader("📊 Registrazione Ultimo Intervallo Salvato su DB")

    if not auto_data["summary"].empty:
        st.dataframe(auto_data["summary"], use_container_width=True)
    elif auto_data["status"] == "WEATHER_UNAVAILABLE":
        st.info("⏸️ Registrazione automatica sospesa in attesa di dati meteo validi.")
    else:
        st.info("⏱️ Sessione avviata. In attesa dello scatto del primo intervallo di 30 minuti o di una variazione del vento di 6 kts.")

    st.markdown("---")
    st.subheader("📚 Storico Generale Accumulato Cime (Tutti gli ormeggi)")
    df_full_history = get_line_history()
    if not df_full_history.empty:
        st.dataframe(df_full_history, use_container_width=True)
    else:
        st.caption("Nessun dato nello storico generale.")
