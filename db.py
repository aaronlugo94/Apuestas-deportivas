"""
db.py — Manejo de la base de datos SQLite para las señales filtradas.
"""
import sqlite3
import os
from datetime import datetime, timezone

DB_DIR = os.environ.get("DB_DIR", ".")
DB_PATH = os.path.join(DB_DIR, "signals.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_message_id TEXT UNIQUE,     -- id/hash del mensaje original en el canal, para no duplicar
    fecha_evento TEXT,              -- fecha/hora del evento deportivo (ej. "28.08 21:30")
    equipo_local TEXT,
    equipo_visitante TEXT,
    mercado TEXT,                   -- ej. "G1", "Hándicap 2 (1.75)"
    cuota REAL,                     -- ej. 1.843
    stake_unidades REAL DEFAULT 1,  -- stake fijo en "unidades" (no dinero real)
    estado TEXT DEFAULT 'pendiente',-- pendiente | ganada | perdida
    profit_unidades REAL,           -- se llena cuando se resuelve
    fecha_publicacion TEXT,         -- cuándo se capturó del canal (UTC ISO)
    fecha_resolucion TEXT           -- cuándo se marcó ganada/perdida (UTC ISO)
);
"""


def get_conn():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def signal_exists(raw_message_id: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM signals WHERE raw_message_id = ?", (raw_message_id,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_signal(raw_message_id, fecha_evento, equipo_local, equipo_visitante,
                   mercado, cuota, stake_unidades=1.0):
    conn = get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO signals
           (raw_message_id, fecha_evento, equipo_local, equipo_visitante,
            mercado, cuota, stake_unidades, fecha_publicacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (raw_message_id, fecha_evento, equipo_local, equipo_visitante,
         mercado, cuota, stake_unidades, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def resolve_pending_by_cuota(cuota: float, resultado: str, tolerance: float = 0.005):
    """
    Marca como ganada/perdida la señal pendiente cuya cuota coincida
    (con tolerancia, porque el resumen diario a veces redondea a 2 decimales).
    resultado: 'ganada' o 'perdida'
    Devuelve True si encontró y actualizó una fila.
    """
    conn = get_conn()
    row = conn.execute(
        """SELECT id, cuota, stake_unidades FROM signals
           WHERE estado = 'pendiente' AND ABS(cuota - ?) <= ?
           ORDER BY fecha_publicacion ASC LIMIT 1""",
        (cuota, tolerance),
    ).fetchone()
    if row is None:
        conn.close()
        return False

    stake = row["stake_unidades"]
    if resultado == "ganada":
        profit = stake * (row["cuota"] - 1)
    else:
        profit = -stake

    conn.execute(
        """UPDATE signals SET estado = ?, profit_unidades = ?, fecha_resolucion = ?
           WHERE id = ?""",
        (resultado, profit, datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    conn.commit()
    conn.close()
    return True


def get_all_signals():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM signals ORDER BY fecha_publicacion DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_summary():
    signals = get_all_signals()
    resueltas = [s for s in signals if s["estado"] in ("ganada", "perdida")]
    ganadas = [s for s in resueltas if s["estado"] == "ganada"]
    perdidas = [s for s in resueltas if s["estado"] == "perdida"]
    total_apostado = sum(s["stake_unidades"] for s in resueltas)
    profit_total = sum(s["profit_unidades"] or 0 for s in resueltas)
    roi = (profit_total / total_apostado * 100) if total_apostado else 0.0
    winrate = (len(ganadas) / len(resueltas) * 100) if resueltas else 0.0

    return {
        "total_senales": len(signals),
        "pendientes": len(signals) - len(resueltas),
        "resueltas": len(resueltas),
        "ganadas": len(ganadas),
        "perdidas": len(perdidas),
        "winrate_pct": round(winrate, 2),
        "profit_unidades": round(profit_total, 2),
        "total_apostado_unidades": round(total_apostado, 2),
        "roi_pct": round(roi, 2),
    }
