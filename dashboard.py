"""
dashboard.py — Dashboard en Streamlit para visualizar el historial de
señales de AMBOS canales (Apuestas Deportivas + INSIDER), winrate, y
ganancia/pérdida acumulada (en "unidades" de stake, no dinero real).

Correr localmente con:
    streamlit run dashboard.py

Si lo despliegas en Railway aparte del worker, corre como servicio web
(usa el puerto que Railway inyecta en $PORT).
"""
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import plotly.express as px

import db  # canal "Apuestas Deportivas" (estructurado)

st.set_page_config(page_title="Señales — Ganancias/Pérdidas", layout="wide")
st.title("📊 Tracking de señales filtradas")

INSIDER_DB_PATH = os.path.join(os.environ.get("DB_DIR", "."), "signals.db")
TUCSON_TZ = ZoneInfo("America/Phoenix")  # Arizona no usa horario de verano, igual que Tucson


def to_tucson(iso_str: str) -> str:
    """Convierte un ISO string en UTC a hora de Tucson, formato corto."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(TUCSON_TZ).strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return iso_str


def format_date_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(to_tucson)
    return df


def display_table(df: pd.DataFrame, date_cols: list[str]):
    """Muestra la tabla con fechas en hora de Tucson y el índice empezando en 1."""
    df = format_date_columns(df, date_cols)
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    st.dataframe(df, use_container_width=True)


def get_insider_summary_and_signals():
    """Lee la tabla insider_signals directo (sin importar el paquete insider/,
    para no arrastrar dependencias como telethon en el servicio del dashboard)."""
    conn = sqlite3.connect(INSIDER_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM insider_signals ORDER BY fecha_publicacion DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []  # la tabla aún no existe si el worker de INSIDER no ha corrido
    conn.close()
    signals = [dict(r) for r in rows]

    resueltas = [s for s in signals if s["estado"] in ("ganada", "perdida")]
    ganadas = [s for s in resueltas if s["estado"] == "ganada"]
    total_apostado = sum(s["stake_unidades"] for s in resueltas)
    profit_total = sum(s["profit_unidades"] or 0 for s in resueltas)
    roi = (profit_total / total_apostado * 100) if total_apostado else 0.0
    winrate = (len(ganadas) / len(resueltas) * 100) if resueltas else 0.0

    summary = {
        "total_picks": len(signals),
        "pendientes": len(signals) - len(resueltas),
        "winrate_pct": round(winrate, 2),
        "profit_unidades": round(profit_total, 2),
        "roi_pct": round(roi, 2),
    }
    return summary, signals


def delete_insider_signal(signal_id: int):
    conn = sqlite3.connect(INSIDER_DB_PATH)
    conn.execute("DELETE FROM insider_signals WHERE id = ?", (signal_id,))
    conn.commit()
    conn.close()


def render_apuestas_deportivas():
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
        "no dinero real. Así el ROI es comparable sin importar cuánto apuestes tú. "
        "Fechas mostradas en hora de Tucson."
    )

    df = pd.DataFrame([s for s in signals if s["cuota"]])

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
            "id", "fecha_publicacion", "equipo_local", "equipo_visitante", "mercado",
            "cuota", "stake_unidades", "estado", "profit_unidades", "fecha_resolucion",
        ]
        tabla = df[display_cols].sort_values("fecha_publicacion", ascending=False)
        display_table(tabla.drop(columns=["id"]), ["fecha_publicacion", "fecha_resolucion"])

        st.subheader("⚙️ Resolver o eliminar manualmente")
        candidatos = [s for s in signals if s["cuota"]]
        label_map = {
            s["id"]: f"#{s['id']} — {s['equipo_local']} vs {s['equipo_visitante']} (cuota {s['cuota']}, {s['estado']})"
            for s in candidatos
        }
        ids_disponibles = [s["id"] for s in candidatos]
        selected_id = st.selectbox(
            "Señal",
            ids_disponibles,
            format_func=lambda i: label_map[i],
            key="manual_action_select",
        )

        st.caption(
            "Resolver: úsalo cuando el canal publique un resultado que el matching "
            "automático no logró emparejar."
        )
        col_a, col_b = st.columns(2)
        if col_a.button("✅ Marcar ganada", use_container_width=True):
            db.resolve_by_id(selected_id, "ganada")
            st.success(f"Señal #{selected_id} marcada como ganada.")
            st.rerun()
        if col_b.button("❌ Marcar perdida", use_container_width=True):
            db.resolve_by_id(selected_id, "perdida")
            st.success(f"Señal #{selected_id} marcada como perdida.")
            st.rerun()

        st.caption("Eliminar: para picks basura, duplicados, o mal parseados.")
        if st.button("🗑️ Eliminar esta señal", use_container_width=True):
            db.delete_signal(selected_id)
            st.success(f"Señal #{selected_id} eliminada.")
            st.rerun()
    else:
        st.info("Aún no hay señales registradas. El worker las irá llenando conforme corra.")


def render_insider():
    summary, signals = get_insider_summary_and_signals()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Picks totales", summary["total_picks"])
    col2.metric("Pendientes", summary["pendientes"])
    col3.metric("Winrate", f'{summary["winrate_pct"]}%')
    col4.metric("ROI", f'{summary["roi_pct"]}%')

    st.caption(
        "⚠️ Este canal no publica cupones estructurados: los picks vienen "
        "como capturas de pantalla (extraídas con OCR) o texto libre, y los "
        "resultados se resuelven por orden de llegada (FIFO), no por match "
        "exacto con cada pick. Trátalo como una aproximación, no como dato exacto — "
        "revisa la columna 'confianza' de cada fila. Fechas en hora de Tucson."
    )

    df = pd.DataFrame([s for s in signals if s["cuota"]])

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

        st.subheader("Detalle de picks")
        display_cols = [
            "id", "fecha_publicacion", "partidos", "cuota", "fuente", "confianza",
            "stake_unidades", "estado", "profit_unidades", "fecha_resolucion",
        ]
        tabla = df[display_cols].sort_values("fecha_publicacion", ascending=False)
        display_table(tabla.drop(columns=["id"]), ["fecha_publicacion", "fecha_resolucion"])

        st.subheader("🗑️ Eliminar un pick")
        candidatos = [s for s in signals if s["cuota"]]
        label_map = {s["id"]: f"#{s['id']} — {s['partidos']} (cuota {s['cuota']})" for s in candidatos}
        ids_disponibles = [s["id"] for s in candidatos]
        selected_id = st.selectbox(
            "Pick",
            ids_disponibles,
            format_func=lambda i: label_map[i],
            key="insider_delete_select",
        )
        if st.button("🗑️ Eliminar este pick", use_container_width=True):
            delete_insider_signal(selected_id)
            st.success(f"Pick #{selected_id} eliminado.")
            st.rerun()
    else:
        st.info("Aún no hay picks registrados de INSIDER.")


tab1, tab2 = st.tabs(["⚽ Apuestas Deportivas", "🔮 INSIDER"])
with tab1:
    render_apuestas_deportivas()
with tab2:
    render_insider()
