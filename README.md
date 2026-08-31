# signal-filter-bot

Filtra señales reales de apuesta desde el canal público de Telegram
`@Apuestas_Deportivas_Futbo`, descarta la publicidad/promos, las reenvía a
tu propio canal, y trackea ganancias/pérdidas en un dashboard.

## Cómo funciona

1. `scraper.py` lee `https://t.me/s/Apuestas_Deportivas_Futbo` (preview
   público, sin login) cada `POLL_INTERVAL_SECONDS`.
2. `filters.py` decide si cada mensaje es un cupón real de apuesta
   (contiene Cuota/Apuesta/Posibles ganancias) o ruido (promos, VIP, videos).
3. Las señales reales se guardan en SQLite (`db.py`) y se reenvían a tu
   canal vía `notifier.py` (Bot API, con tu propio bot de @BotFather).
4. Cuando el canal publica su resumen diario ("Resultado de hoy: 1.64 ✅..."),
   `filters.py` lo parsea y `db.py` marca las señales pendientes como
   ganada/perdida, calculando tu propio profit y ROI (no el % inflado que
   ellos publican).
5. `dashboard.py` (Streamlit) muestra winrate, ROI y la curva de
   ganancia/pérdida acumulada.

## Setup local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # llena TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
export $(cat .env | xargs)   # o usa python-dotenv si prefieres
python main.py                # corre el worker
streamlit run dashboard.py    # corre el dashboard (en otra terminal)
```

## Crear tu bot destino

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el token
   en `TELEGRAM_BOT_TOKEN`.
2. Crea tu canal privado donde quieres recibir las señales filtradas.
3. Agrega tu bot como admin de ese canal.
4. `TELEGRAM_CHAT_ID` = el `@username` del canal (si es público) o el ID
   numérico (si es privado — se obtiene reenviando un mensaje del canal a
   [@userinfobot](https://t.me/userinfobot) o similar).

## Deploy en Railway

1. Push del repo a GitHub.
2. En Railway: "New Project" → "Deploy from GitHub repo".
3. Railway detecta el `Procfile` y crea dos procesos: `worker` y `dashboard`.
   - Activa el proceso `worker` como servicio background.
   - Activa `dashboard` como servicio web (Railway le asigna dominio público).
4. Configura las variables de entorno del `.env.example` en el panel de Railway.
5. Monta un **volume** en `/app/data` y pon `DB_DIR=/app/data`, para que la
   base SQLite no se borre en cada redeploy.

## Notas

- El stake usado para calcular profit/ROI es una "unidad" fija
  (`DEFAULT_STAKE_UNIDADES`), no dinero real — así el ROI es comparable
  sin importar cuánto apuestes tú en la práctica.
- El resumen diario del canal reporta "%" de ganancia que probablemente
  se calcula distinto (parece ROI sobre banca total, no por señal), por
  eso este proyecto calcula su propio profit/ROI de forma transparente.
- Si el canal cambia el formato de sus mensajes, hay que ajustar las regex
  en `filters.py`.
