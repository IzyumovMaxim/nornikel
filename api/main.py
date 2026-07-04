"""FastAPI-бэкенд R&D графа знаний.

Эндпоинты:
  GET  /api/meta      — типы узлов, диапазоны числовых параметров, роли, примеры
  GET  /api/graph     — полный граф (для глобального вида), с учётом роли
  GET  /api/suggest   — автодополнение по сущностям
  POST /api/search    — семантический поиск + ответ + подграф + противоречия

Запуск:  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from query.engine import ROLES, get_graph  # noqa: E402
from domain.ontology import NODE_TYPES, NUMERIC_PARAMS  # noqa: E402

app = FastAPI(title="R&D Knowledge Graph API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

kg = get_graph()

# каталог с исходными документами (для отдачи оригиналов по ссылке)
SRC_BASE = os.environ.get(
    "NORNIKEL_SRC", "/Users/maximizyumov/Downloads/Задача 2. Научный клубок")

EXAMPLES = [
    "Обогащение медно-никелевого сырья флотацией",
    "Напряжённо-деформированное состояние массива горных пород",
    "Извлечение платиновых металлов (МПГ)",
    "Прогнозирование удароопасности месторождений",
]


def _allowed(role: str) -> set:
    return ROLES.get(role, ROLES["Исследователь"])["types"]


@app.get("/api/meta")
def meta():
    exp = [d for _, d in kg.G.nodes(data=True) if d["type"] == "Experiment"]
    ranges = {}
    for k, (name, unit) in NUMERIC_PARAMS.items():
        vals = [d[k] for d in exp if d.get(k) is not None]
        if vals:
            ranges[k] = {"name": name, "unit": unit,
                         "min": float(min(vals)), "max": float(max(vals))}
    roles = {r: {"types": sorted(v["types"]),
                 "see_contradictions": v["see_contradictions"]}
             for r, v in ROLES.items()}
    # диапазон годов и материалы-фасеты — по новому корпусу
    years = sorted({m.get("year") for m in kg.chunks.doc_meta.values()} - {None})
    facets = kg.gz.facets(top=40)
    return {
        "nodeTypes": {k: {"label": v["label"], "color": v["color"]}
                      for k, v in NODE_TYPES.items()},
        "numericParams": ranges,
        "roles": roles,
        "examples": EXAMPLES,
        "yearRange": [years[0], years[-1]] if years else None,
        "facetMaterials": facets["Material"],
        "stats": {"nodes": kg.G.number_of_nodes(), "edges": kg.G.number_of_edges(),
                  "contradictions": len(kg.contradictions())},
    }


@app.get("/api/graph")
def graph(role: str = "Исследователь"):
    return kg.graph_payload(allowed_types=_allowed(role), limit=350)


@app.get("/api/suggest")
def suggest(q: str = ""):
    return {"suggestions": kg.suggest(q), "examples": EXAMPLES}


class SearchReq(BaseModel):
    query: str
    role: str = "Исследователь"
    origin: str | None = None
    ranges: dict[str, list[float]] = {}
    top_k: int = 8
    fast: bool = False        # быстрый режим: без expand/rerank (1 LLM-вызов)
    year_from: int | None = None
    year_to: int | None = None
    material: str | None = None


from collections import OrderedDict  # noqa: E402
from query import constraints as _cons  # noqa: E402

_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_MAX = 128


@app.post("/api/search")
def search(req: SearchReq):
    origin = req.origin if req.origin in ("Отечественная", "Зарубежная") else None

    key = (req.query.strip().lower(), origin, req.top_k, req.fast,
           req.year_from, req.year_to, req.material)
    if key in _CACHE:
        cached = dict(_CACHE[key])
        cached["meta"] = {**cached.get("meta", {}), "cached": True}
        _CACHE.move_to_end(key)
        return cached

    # быстрый режим: только BM25 + синтез; точный: expand → BM25 → LLM-реранк
    hits = kg.search_chunks(req.query, top_k=6 if req.fast else max(req.top_k, 8),
                            top_n=60, per_doc=3, origin=origin,
                            expand=not req.fast, use_rerank=not req.fast,
                            year_from=req.year_from, year_to=req.year_to,
                            material=req.material)

    answer = kg.answer_from_chunks(req.query, hits, brief=req.fast) if hits else \
        "По запросу ничего не найдено — переформулируйте вопрос."

    # таблица источников: документ + категория + фрагмент, в порядке реранка
    table = []
    for rank, h in enumerate(hits, 1):
        path = h.get("path", "")
        table.append({
            "report": h["doc_id"],
            "rank": rank,
            "title": h.get("title", ""),
            "filename": os.path.basename(path) if path else "",
            "category": h.get("category"),
            "origin": h.get("origin"),
            "year": h.get("year"),
            "path": path,
            "url": f"/api/doc/{h['doc_id']}",
            "snippet": " ".join(h["text"].split())[:240],
            "facts": _cons.extract_facts(h["text"]),   # извлечённые числовые факты
        })

    # подграф документ↔сущность по НОВОМУ корпусу (газеттир по извлечённым чанкам)
    payload = kg.result_graph(hits) if hits else {"nodes": [], "links": []}

    meta = kg.result_meta(req.query, hits)
    meta["mode"] = "fast" if req.fast else "accurate"
    meta["cached"] = False

    resp = {"answer": answer, "graph": payload, "table": table,
            "contradictions": [], "focus": [], "meta": meta}
    if hits:
        _CACHE[key] = resp
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return resp


@app.get("/api/doc/{doc_id}")
def get_doc(doc_id: str):
    """Отдаёт оригинальный файл документа по его ID (для ссылки-источника)."""
    meta = kg.chunks.doc_meta.get(doc_id)
    if not meta or not meta.get("path"):
        raise HTTPException(status_code=404, detail="Документ не найден")
    abs_path = os.path.join(SRC_BASE, meta["path"])
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Файл недоступен")
    return FileResponse(abs_path, filename=os.path.basename(abs_path))
