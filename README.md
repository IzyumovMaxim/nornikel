# R&D Граф знаний горно-металлургической отрасли

MVP для Nornickel AI Hackathon (Задача 2). Единая карта знаний, связывающая
публикации/отчёты, эксперименты, материалы, процессы, оборудование, экспертов и
выводы. Естественно-языковой поиск, обход графа, поиск противоречий, синтез
структурированного ответа со ссылками на отчёты и ролевой доступ (RBAC).

## Стек

| Слой | Технология |
|---|---|
| Извлечение сущностей (NLP) | **YandexGPT** (structured output) + эвристический фолбэк |
| Семантический поиск | **Yandex Embeddings** (text-search-doc / query), косинус |
| Граф и обходы | **NetworkX** (движок) + выгрузка в **Neo4j** |
| Числовые/атрибутивные фильтры | параметры экспериментов (t, извлечение, pH, …) |
| Синтез ответа | **YandexGPT** (RAG поверх подграфа) |
| API | **FastAPI** |
| Интерфейс | **React + Vite**, force-directed граф в стиле Obsidian |

## Быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ключи Yandex Cloud в .env: YC_API_KEY, YC_FOLDER_ID

python scripts/generate_corpus.py      # синтетический корпус (или подложи реальный)
python ingest/build_graph.py           # extraction + граф + эмбеддинги

# фронтенд (один раз): cd web && npm install
bash scripts/run_dev.sh                # поднимает FastAPI :8000 + Vite :5173
# открой http://localhost:5173
```

Устаревший Streamlit-прототип оставлен как `app.py` (`streamlit run app.py`);
основной интерфейс — React (`web/`).

Реальный датасет с Яндекс.Диска подключается заменой `data/corpus.json`
(поля: `id`, `title`, `origin`, `year`, `text`).

### Опционально: Neo4j (настоящая графовая БД)

```bash
docker compose up -d
python scripts/load_neo4j.py           # http://localhost:7474  (neo4j / hackathon2024)
```

## Как это отвечает требованиям задачи

- **Импорт и нормализация** — `ingest/extract.py` приводит разнородный текст к схеме онтологии.
- **Извлечение сущностей и связей (NLP)** — YandexGPT по онтологии, фолбэк-парсер.
- **Граф знаний** — типизированный граф (`domain/ontology.py`): 7 типов узлов, 9 типов связей.
- **Семантический поиск + числовые диапазоны** — эмбеддинги + фильтры по параметрам.
- **Визуализация цепочек и пробелов** — интерактивный подграф (pyvis) с подсветкой связей.
- **Поиск противоречий** — один материал+процесс с противоположными выводами → ребро `CONTRADICTS`.
- **Структурированные ответы (обзор литературы)** — синтез YandexGPT со ссылками `[R-XXXX]`.
- **Отечественные vs зарубежные практики** — атрибут `origin` + фильтр + разделение в ответе.
- **Ролевой доступ (RBAC)** — роли Гость / Исследователь / Рук. R&D (`query/engine.py`).

## Архитектура (масштабирование)

MVP работает на NetworkX in-memory. Для целевых ~1 млн сущностей и отклика 3–5 с:
граф и векторы переносятся в Neo4j (+ native vector index) с индексами по числовым
параметрам; extraction распараллеливается по документам; эмбеддинги — асимметричные
модели Yandex. Онтология и слой запросов не меняются.

## Структура

```
domain/ontology.py      типы узлов/связей, числовые параметры
scripts/yandex.py       клиент Yandex Cloud (completion + embeddings, кэш)
scripts/generate_corpus.py   синтетический корпус
ingest/extract.py       извлечение сущностей (YandexGPT / эвристика)
ingest/build_graph.py   сборка графа, эмбеддинги, противоречия
query/engine.py         поиск, обходы, RBAC, синтез ответа, сериализация графа
api/main.py             FastAPI: /api/meta, /api/graph, /api/suggest, /api/search
web/                    React + Vite фронтенд (граф в стиле Obsidian)
  src/GraphCanvas.jsx   force-directed граф (свечение, подсветка, противоречия)
  src/SearchBar.jsx     поиск с автодополнением
  src/Panels.jsx        роли, фильтры, панель результата, легенда
app.py                  устаревший Streamlit-прототип
scripts/run_dev.sh      запуск бэкенда + фронтенда
scripts/load_neo4j.py   выгрузка в Neo4j
```
