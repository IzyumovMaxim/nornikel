#!/usr/bin/env bash
# Автономная ночная обработка всего корпуса:
#  1) извлечение по всем документам (несколько проходов — добираем стрегглеров)
#  2) сборка полного графа + эмбеддинги
#  3) перезапуск бэкенда на полном графе
# Возобновляемо: кэш на диске, повторный запуск продолжает с места.
set -u
cd /Users/maximizyumov/nornikel
PY=.venv/bin/python
FILTER='MuPDF|Cannot parse|UserWarning|warn\(|too many sub-functions'
LOG() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

rm -f data/OVERNIGHT_DONE
TOTAL=$($PY -c "import json;print(len(json.load(open('data/corpus.json'))))")
LOG "=== СТАРТ. Всего документов: $TOTAL ==="

prev=-1
for pass in 1 2 3 4 5 6; do
  cnt=$(ls data/extract_cache/D-*.json 2>/dev/null | wc -l | tr -d ' ')
  LOG "Проход $pass — извлечено $cnt/$TOTAL"
  if [ "$cnt" -ge "$TOTAL" ]; then LOG "Все документы извлечены"; break; fi
  if [ "$cnt" -eq "$prev" ] && [ "$pass" -gt 1 ]; then
    LOG "Прогресс остановился на $cnt (оставшиеся не парсятся/падают) — завершаю извлечение"; break
  fi
  prev=$cnt
  $PY scripts/extract_all.py --workers 2 2>&1 | grep -vE "$FILTER" || true
  sleep 15
done

FINAL=$(ls data/extract_cache/D-*.json 2>/dev/null | wc -l | tr -d ' ')
LOG "=== Извлечено итого: $FINAL/$TOTAL. Собираю полный граф + эмбеддинги… ==="
$PY ingest/build_graph.py --cached-only 2>&1 | grep -vE "$FILTER" || true

LOG "Граф собран. Перезапускаю бэкенд…"
pkill -f "uvicorn api.main" 2>/dev/null || true
sleep 2
nohup caffeinate -is $PY -m uvicorn api.main:app --port 8000 > /tmp/api.log 2>&1 &
sleep 4

NODES=$($PY -c "import json;print(len(json.load(open('data/graph.json'))['nodes']))" 2>/dev/null || echo '?')
LOG "=== ГОТОВО. Документов: $FINAL/$TOTAL, узлов в графе: $NODES. Бэкенд поднят. ==="
touch data/OVERNIGHT_DONE
