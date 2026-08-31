"""
dashboard.py — Dashboard en Streamlit para visualizar el historial de señales,
winrate, y ganancia/pérdida acumulada (en "unidades" de stake, no dinero real,
ya que no sabemos cuánto apuesta cada quien por señal).

Correr localmente con:
    streamlit run dashboard.py

Si lo despliegas en Railway aparte del worker, corre como servicio web
(usa el puerto que Railway inyecta en $PORT).
"""
import streamlit as st
import pandas as pd
import plotly.express as px

import db

st.set_page_config(page_title="Señales — Ganancias/Pérdidas", layout="wide")

st.title("📊 Tracking de señales filtradas")

db.init_db()
summary = db.get_summary()
signals = db.get_all_signals()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Señales totales", summary["total_senales"])
col2.metric("Pendientes", summary["pendientes"])
col3.metric("Winrate", f'{summary["winrate_pct"]}%')
col4.metric("Profit (unidades)", summary["profit_unidades"])
col5.metric("ROI", f'{summary["roi_pct"]}%')

st.caption(
    "Nota: 'unidades' = stake fijo configurable (DEFAULT_STAKE_UNIDADES), "
    "no dinero real. Así el ROI es comparable sin importar cuánto apuestes tú."
)

df = pd.DataFrame([s for s in signals if s["cuota"]])  # excluye filas placeholder (resúmenes/no parseadas)

if not df.empty:
    df_resueltas = df[df["estado"].isin(["ganada", "perdida"])].copy()
    if not df_resueltas.empty:
        df_resueltas = df_resueltas.sort_values("fecha_publicacion")
        df_resueltas["profit_acumulado"] = df_resueltas["profit_unidades"].cumsum()

        st.subheader("Evolución de ganancia/pérdida acumulada")
        fig = px.line(
            df_resueltas,
            x="fecha_publicacion",
            y="profit_acumulado",
            markers=True,
            labels={"fecha_publicacion": "Fecha", "profit_acumulado": "Profit acumulado (unidades)"},
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalle de señales")
    display_cols = [
        "fecha_publicacion", "equipo_local", "equipo_visitante", "mercado",
        "cuota", "stake_unidades", "estado", "profit_unidades", "fecha_resolucion",
    ]
    st.dataframe(
        df[display_cols].sort_values("fecha_publicacion", ascending=False),
        use_container_width=True,
    )
else:
    st.info("Aún no hay señales registradas. El worker las irá llenando conforme corra.")
