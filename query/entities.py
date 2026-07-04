"""Газеттир-тегирование сущностей для привязки графа к новому корпусу.

Полная LLM-экстракция по 2000+ полным документам дорогая. Вместо этого берём
словарь материалов/процессов/оборудования из старого графа (`data/graph.json`) и
матчим его по тексту извлечённых чанков (их ~8 на запрос — быстро). Результат:
подграф документ↔сущность на НОВОМ корпусе + частотные сущности как фасеты фильтра.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

_TYPES = ("Material", "Process", "Equipment")
# шум из старого графа (бизнес-фразы, котировки, названия проектов)
_NOISE = re.compile(
    r"prices|market|bulletin|forecast|monthly|turnover|trends|project|"
    r"consumption|production and|ltd|inc\.|resources|\bby product\b", re.I)
_COLOR = {"Material": "#54A24B", "Process": "#B279A2",
          "Equipment": "#E45756", "Publication": "#6b7a90"}
_STOP = {"none", "null", "none specified", "not specified", "n/a", "нет данных",
         "не указано", "прочее", "other", "various"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


class Gazetteer:
    def __init__(self):
        self.terms: dict[str, tuple[str, str]] = {}   # norm -> (label, type)
        self.freq: Counter = Counter()
        self._load()

    def _load(self):
        g = json.loads((DATA / "graph.json").read_text(encoding="utf-8"))
        deg = Counter()
        for e in g.get("links", g.get("edges", [])):
            deg[e.get("source")] += 1
            deg[e.get("target")] += 1
        for n in g["nodes"]:
            t = n.get("type")
            if t not in _TYPES:
                continue
            lab = (n.get("label") or "").strip()
            if not (4 <= len(lab) <= 32) or lab.isdigit() or _NOISE.search(lab):
                continue
            nk = _norm(lab)
            if nk in _STOP:
                continue
            if nk and nk not in self.terms:
                self.terms[nk] = (lab, t)
                self.freq[nk] = deg.get(n.get("id"), 0)
        # для матчинга — по убыванию длины (сначала специфичные)
        self._ordered = sorted(self.terms.keys(), key=len, reverse=True)

    def tag(self, text: str, *, max_terms: int = 8) -> list[tuple[str, str]]:
        """Сущности, найденные в тексте (по границам слов)."""
        low = text.lower()
        found = []
        for nk in self._ordered:
            if nk in low and re.search(r"(?<!\w)" + re.escape(nk) + r"(?!\w)", low):
                found.append(self.terms[nk])
                if len(found) >= max_terms:
                    break
        return found

    def build_subgraph(self, docs: list[dict], *, per_doc: int = 6) -> dict:
        """Подграф документ↔сущность по извлечённым чанкам (nodes/links)."""
        nodes: dict[str, dict] = {}
        links = []
        for d in docs:
            did = d["doc_id"]
            pub_id = f"PUB:{did}"
            if pub_id not in nodes:
                nodes[pub_id] = {"id": pub_id, "label": d.get("title") or did,
                                 "type": "Publication", "color": _COLOR["Publication"],
                                 "deg": 0, "origin": d.get("origin"),
                                 "year": d.get("year")}
            for lab, typ in self.tag(d.get("text", ""), max_terms=per_doc):
                eid = f"{typ}:{_norm(lab)}"
                if eid not in nodes:
                    nodes[eid] = {"id": eid, "label": lab, "type": typ,
                                  "color": _COLOR.get(typ, "#888"), "deg": 0}
                links.append({"source": pub_id, "target": eid, "type": "MENTIONS"})
                nodes[eid]["deg"] += 1
                nodes[pub_id]["deg"] += 1
        return {"nodes": list(nodes.values()), "links": links}

    def facets(self, *, top: int = 40) -> dict:
        """Частотные материалы/процессы для фасетного фильтра."""
        out = {"Material": [], "Process": []}
        for nk, _f in self.freq.most_common():
            lab, typ = self.terms[nk]
            if typ in out and len(out[typ]) < top:
                out[typ].append(lab)
        return out


_INSTANCE: Gazetteer | None = None


def get_gazetteer() -> Gazetteer:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Gazetteer()
    return _INSTANCE
