#!/bin/bash
# start.sh — Corre el worker (scraping) y el dashboard (Streamlit) juntos
# en el MISMO contenedor/servicio de Railway, para que compartan el mismo
# disco local sin depender de volumes compartidos entre servicios distintos
# (Railway generalmente monta un volume a un solo servicio a la vez).
set -e

echo "Iniciando worker en segundo plano..."
python main.py &
WORKER_PID=$!

echo "Iniciando dashboard (Streamlit)..."
streamlit run dashboard.py --server.port="${PORT:-8501}" --server.address=0.0.0.0 &
DASH_PID=$!

# Si cualquiera de los dos procesos muere, tumba el contenedor entero
# para que Railway lo reinicie limpio (evita quedar "medio vivo").
wait -n "$WORKER_PID" "$DASH_PID"
EXIT_CODE=$?
echo "Un proceso terminó (código $EXIT_CODE), cerrando el contenedor."
exit $EXIT_CODE
