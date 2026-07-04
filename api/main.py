"""FastAPI-бэкенд R&D графа знаний.

Эндпоинты:
  GET  /api/meta      — типы узлов, диапазоны числовых параметров, роли, примеры
  GET  /api/graph     — полный граф (для глобального вида), с учётом роли
  GET  /api/suggest   — автодополнение по сущностям
  POST /api/search    — семантический поиск + ответ + подграф + противоречия

Запуск:  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from query.engine import ROLES, get_graph  # noqa: E402
from domain.ontology import NODE_TYPES, NUMERIC_PARAMS  # noqa: E402

app = FastAPI(title="R&D Knowledge Graph API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

kg = get_graph()

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
    return {
        "nodeTypes": {k: {"label": v["label"], "color": v["color"]}
                      for k, v in NODE_TYPES.items()},
        "numericParams": ranges,
        "roles": roles,
        "examples": EXAMPLES,
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


@app.post("/api/search")
def search(req: SearchReq):
    at = _allowed(req.role)
    ranges = {k: (v[0], v[1]) for k, v in req.ranges.items() if len(v) == 2}
    origin = req.origin if req.origin in ("Отечественная", "Зарубежная") else None
    hits = kg.search_experiments(req.query, top_k=req.top_k, ranges=ranges,
                                 origin=origin)
    contexts = [kg.experiment_context(nid) for nid, _ in hits]

    answer = kg.answer(req.query, contexts) if hits else \
        "По заданным фильтрам ничего не найдено — ослабьте числовые ограничения."

    ids = [nid for nid, _ in hits]
    sub = kg.subgraph_for(ids, at) if ids else kg.G.subgraph([])
    payload = kg.graph_payload(node_ids=list(sub.nodes()), allowed_types=at)

    # таблица найденного
    table = []
    for (nid, score), c in zip(hits, contexts):
        table.append({
            "report": (c.get("publication") or "").replace("EXP:", ""),
            "score": round(score, 3),
            "process": c.get("process"),
            "materials": c["materials"],
            "recovery": c["params"].get("recovery"),
            "temperature": c["params"].get("temperature"),
            "origin": c.get("origin"),
            "sentiment": (c.get("conclusion") or {}).get("sentiment"),
        })

    # релевантные противоречия
    contradictions = []
    if ROLES.get(req.role, {}).get("see_contradictions", True):
        q_proc = {(c.get("process") or "").lower() for c in contexts}
        q_mat = {m.lower() for c in contexts for m in c["materials"]}
        allc = kg.contradictions()
        contradictions = [r for r in allc
                          if r["process"] in q_proc or r["material"] in q_mat] or allc

    focus = [nid for nid, _ in hits]
    return {"answer": answer, "graph": payload, "table": table,
            "contradictions": contradictions, "focus": focus}
