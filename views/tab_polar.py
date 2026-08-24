with tab_polar:
    st.subheader("Inviluppo Polare dei Limiti Operativi del Vento (0-360°)")

    if st.button("Esegui Simulazione Polare") and not geom_df.empty:
        with st.spinner("Calcolo dinamico in corso..."):
            angles, max_winds = calculate_wind_operability_envelope(
                geom_df,
                ship_dict["AFW"],
                ship_dict["ALW"],
                ship_dict["ALC"],
                ship_dict["LOA"],
                v_curr=v_curr,
                dir_curr=dir_curr,
            )

            fig_polar = go.Figure()
            fig_polar.add_trace(
                go.Scatterpolar(
                    r=max_winds,
                    theta=angles,
                    fill="toself",
                    fillcolor="rgba(0, 128, 0, 0.25)",
                    line=dict(color="green", width=2),
                )
            )

            max_r = (
                max(max_winds) + 10 if max_winds and len(max_winds) > 0 else 80
            )

            fig_polar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True, range=[0, max_r], ticksuffix=" kts"
                    ),
                    angularaxis=dict(direction="clockwise", rotation=90),
                ),
                margin=dict(l=40, r=40, t=20, b=20),
            )
            st.plotly_chart(fig_polar, use_container_width=True)
