#!/usr/bin/env bash
# Запуск бэкенда (FastAPI) и фронтенда (Vite) одной командой.
# Использование:  bash scripts/run_dev.sh
set -e
cd "$(dirname "$0")/.."

echo "→ Бэкенд:  http://localhost:8000"
.venv/bin/uvicorn api.main:app --port 8000 &
BACK=$!

echo "→ Фронтенд: http://localhost:5173"
( cd web && npm run dev ) &
FRONT=$!

trap "kill $BACK $FRONT 2>/dev/null" EXIT
echo "Открой http://localhost:5173 · Ctrl+C для остановки"
wait
