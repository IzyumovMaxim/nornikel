"""Движок запросов над графом знаний.

- семантический поиск по эмбеддингам Yandex + числовые/атрибутивные фильтры;
- извлечение контекста эксперимента и подграфа для визуализации;
- список противоречий;
- синтез структурированного ответа (YandexGPT) с ссылками на отчёты;
- ролевой доступ (RBAC).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import yandex  # noqa: E402
from domain.ontology import NODE_TYPES, NUMERIC_PARAMS  # noqa: E402
from query.retrieval import get_index  # noqa: E402
from query import rerank  # noqa: E402
from query import constraints as cons_mod  # noqa: E402
from query.entities import get_gazetteer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# --- RBAC: какие типы узлов и функции доступны роли ---
ROLES = {
    "Гость":         {"types": {"Publication", "Experiment", "Material", "Process",
                                "Equipment"},
                      "see_contradictions": False, "see_experts": False},
    "Исследователь": {"types": {"Publication", "Experiment", "Material", "Process",
                                "Equipment", "Conclusion"},
                      "see_contradictions": True, "see_experts": False},
    "Рук. R&D":      {"types": {"Publication", "Experiment", "Material", "Process",
                                "Equipment", "Person", "Conclusion"},
                      "see_contradictions": True, "see_experts": True},
}


class KnowledgeGraph:
    def __init__(self):
        data = json.loads((DATA / "graph.json").read_text(encoding="utf-8"))
        self.G: nx.MultiDiGraph = nx.node_link_graph(
            data, multigraph=True, directed=True)
        emb = np.load(DATA / "embeddings.npz", allow_pickle=True)
        self.ids = list(emb["ids"])
        vecs = emb["vectors"].astype(np.float32)
        self.vectors = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
        self.idx = {nid: i for i, nid in enumerate(self.ids)}
        self.chunks = get_index()  # чанк-ретривер по сырому тексту (BM25)
        self.gz = get_gazetteer()  # газеттир сущностей для подграфа и фасетов

    # ---------- поиск ----------
    def _passes_numeric(self, exp_id: str, ranges: dict) -> bool:
        d = self.G.nodes[exp_id]
        for param, (lo, hi) in ranges.items():
            v = d.get(param)
            if v is None:
                return False
            if v < lo or v > hi:
                return False
        return True

    def search_experiments(self, query: str, *, top_k: int = 8,
                           ranges: dict | None = None, origin: str | None = None):
        """Семантический поиск экспериментов + числовые/атрибутивные фильтры."""
        q = yandex.embed(query, kind="query")
        q = q / (np.linalg.norm(q) + 1e-9)
        sims = self.vectors @ q
        order = np.argsort(-sims)
        ranges = ranges or {}
        out = []
        for i in order:
            nid = self.ids[i]
            if self.G.nodes[nid].get("type") != "Experiment":
                continue
            if origin and self.G.nodes[nid].get("origin") != origin:
                continue
            if not self._passes_numeric(nid, ranges):
                continue
            out.append((nid, float(sims[i])))
            if len(out) >= top_k:
                break
        return out

    def search_chunks(self, query: str, *, top_k: int = 8, top_n: int = 60,
                      per_doc: int = 3, origin: str | None = None,
                      expand: bool = True, use_rerank: bool = True,
                      year_from: int | None = None, year_to: int | None = None,
                      material: str | None = None):
        """Поиск: [expand] → BM25 (top_n) → фильтры/буст → [LLM-реранк] → top_k.

        expand/use_rerank отключаемы для «быстрого режима» (1 LLM-вызов вместо 3).
        Фасеты (год, материал) и числовые ограничения фильтруют/буста́т мягко —
        с фолбэком на нефильтрованную выдачу, чтобы не обнулить результат.
        """
        cons = cons_mod.parse_constraints(query)
        q = rerank.expand_query(query) if expand else query
        if material:                       # фасет-материал усиливает запрос к BM25
            q = f"{q} {material}"
        candidates = self.chunks.search(q, top_n=top_n, per_doc=per_doc, origin=origin)

        # фасет по году (мягко: если всё отсеялось — не фильтруем)
        if year_from or year_to:
            def _in_year(h):
                y = h.get("year")
                return y is not None and (not year_from or y >= year_from) \
                    and (not year_to or y <= year_to)
            filtered = [h for h in candidates if _in_year(h)]
            if filtered:
                candidates = filtered

        if cons:
            candidates.sort(
                key=lambda h: cons_mod.chunk_matches(h["text"], cons), reverse=True)
        if use_rerank:
            return rerank.llm_rerank(query, candidates, top_k=top_k)
        return candidates[:top_k]

    def result_graph(self, hits: list[dict]) -> dict:
        """Подграф документ↔сущность по извлечённым чанкам (новый корпус)."""
        # объединяем чанки по документу
        by_doc: dict[str, dict] = {}
        for h in hits:
            d = by_doc.setdefault(h["doc_id"], {
                "doc_id": h["doc_id"], "title": h.get("title"),
                "origin": h.get("origin"), "year": h.get("year"), "text": ""})
            d["text"] += " " + h["text"]
        return self.gz.build_subgraph(list(by_doc.values()))

    def result_meta(self, query: str, hits: list[dict]) -> dict:
        """Метаданные ответа: источники, происхождение, уверенность, ограничения."""
        docs = {h["doc_id"] for h in hits}
        origins = {}
        for did in docs:
            o = self.chunks.doc_meta.get(did, {}).get("origin")
            origins[o] = origins.get(o, 0) + 1
        n = len(docs)
        confidence = "высокая" if n >= 4 else "средняя" if n >= 2 else "низкая"
        cons = cons_mod.parse_constraints(query)
        years = sorted({self.chunks.doc_meta.get(d, {}).get("year")
                        for d in docs} - {None})
        return {
            "sources": n, "chunks": len(hits), "origins": origins,
            "confidence": confidence,
            "constraints": cons_mod.describe(cons) if cons else None,
            "years": [years[0], years[-1]] if years else None,   # актуализация
            "freshest": years[-1] if years else None,
        }

    # ---------- контекст ----------
    def experiment_context(self, exp_id: str) -> dict:
        G = self.G
        ctx = {"id": exp_id, "params": {}, "materials": [], "products": [],
               "process": None, "equipment": [], "team": [], "publication": None,
               "conclusion": None}
        d = G.nodes[exp_id]
        ctx["params"] = {k: d.get(k) for k in NUMERIC_PARAMS if d.get(k) is not None}
        ctx["origin"] = d.get("origin")
        ctx["year"] = d.get("year")
        for _, tgt, k in G.out_edges(exp_id, keys=True):
            et = G.nodes[tgt]["type"]
            kt = G[exp_id][tgt][k]["type"]
            if kt == "USES_MATERIAL":
                ctx["materials"].append(G.nodes[tgt]["label"])
            elif kt == "PRODUCES":
                ctx["products"].append(G.nodes[tgt]["label"])
            elif kt == "APPLIES_PROCESS":
                ctx["process"] = G.nodes[tgt]["label"]
            elif kt == "USES_EQUIPMENT":
                ctx["equipment"].append(G.nodes[tgt]["label"])
            elif kt == "CONCLUDES":
                ctx["conclusion"] = {"text": G.nodes[tgt].get("text", ""),
                                     "sentiment": G.nodes[tgt].get("sentiment")}
        for src, _, k in G.in_edges(exp_id, keys=True):
            if G[src][exp_id][k]["type"] == "DESCRIBES":
                ctx["publication"] = src
                for _, p, kk in G.out_edges(src, keys=True):
                    if G[src][p][kk]["type"] == "AUTHORED_BY":
                        ctx["team"].append(G.nodes[p]["label"])
        return ctx

    # ---------- подграф для визуализации ----------
    def subgraph_for(self, exp_ids: list[str], allowed_types: set) -> nx.MultiDiGraph:
        keep = set()
        for exp_id in exp_ids:
            keep.add(exp_id)
            keep.update(self.G.successors(exp_id))
            keep.update(self.G.predecessors(exp_id))
            for pub in self.G.predecessors(exp_id):
                keep.update(self.G.successors(pub))  # авторы публикации
            for concl in [t for t in self.G.successors(exp_id)
                          if self.G.nodes[t]["type"] == "Conclusion"]:
                keep.update(self.G.successors(concl))    # противоречащие выводы
                keep.update(self.G.predecessors(concl))
        keep = {n for n in keep if self.G.nodes[n]["type"] in allowed_types
                or self.G.nodes[n]["type"] == "Experiment"}
        return self.G.subgraph(keep).copy()

    # ---------- противоречия ----------
    def contradictions(self) -> list[dict]:
        rows = []
        seen = set()
        for u, v, k, d in self.G.edges(keys=True, data=True):
            if d.get("type") != "CONTRADICTS":
                continue
            pair = frozenset((u, v))
            if pair in seen:
                continue
            seen.add(pair)
            rows.append({
                "material": d.get("material"), "process": d.get("process"),
                "recovery_gap": d.get("recovery_gap"),
                "a": self.G.nodes[u].get("text", "")[:140],
                "b": self.G.nodes[v].get("text", "")[:140],
                "a_id": u.replace("CONCL:", ""), "b_id": v.replace("CONCL:", ""),
            })
        return rows

    # ---------- синтез ответа ----------
    def answer(self, query: str, contexts: list[dict]) -> str:
        if not yandex.available():
            return "LLM недоступен: ответ не синтезирован (проверьте YC_API_KEY)."
        blocks = []
        for c in contexts:
            pub = (c.get("publication") or "").replace("EXP:", "")
            params = ", ".join(f"{NUMERIC_PARAMS[k][0]} {v}{NUMERIC_PARAMS[k][1]}"
                               for k, v in c["params"].items())
            blocks.append(
                f"[{pub}] процесс: {c.get('process')}; материалы: {', '.join(c['materials'])}; "
                f"продукты: {', '.join(c['products'])}; параметры: {params}; "
                f"происхождение: {c.get('origin')}; "
                f"вывод: {c.get('conclusion', {}).get('text', '')}")
        context = "\n".join(blocks)
        prompt = (
            f"Вопрос исследователя: {query}\n\n"
            f"Ниже — релевантные записи из графа знаний (в квадратных скобках — ID отчёта):\n"
            f"{context}\n\n"
            "Составь краткий структурированный ответ (обзор литературы) по вопросу. "
            "Оформи в Markdown: короткие абзацы, при необходимости маркированные списки "
            "и выделение **жирным** ключевых чисел. Не используй заголовки уровня #. "
            "Обязательно ссылайся на отчёты в формате [R-XXXX]. "
            "Если данные противоречат друг другу — явно укажи это. "
            "Раздели отечественную и зарубежную практику, если это уместно. "
            "Не выдумывай факты вне приведённых записей.")
        return yandex.complete(prompt, temperature=0.3, max_tokens=1200)

    def answer_from_chunks(self, query: str, chunks: list[dict],
                           brief: bool = False) -> str:
        """Синтез обзора из реальных абзацев отчётов.

        brief=True (быстрый режим): только связный обзор, меньше токенов (~3-4с).
        brief=False: полный ответ — обзор + консенсус/разногласия + пробелы +
        рекомендации, с учётом числовых требований и разделением отеч./зарубеж.
        """
        if not chunks:
            return ("По запросу не найдено релевантных фрагментов в отчётах. "
                    "Переформулируйте запрос или уточните термины.")
        if not yandex.available():
            return "\n\n".join(
                f"**[{c['doc_id']}]** {c['text'][:400]}…" for c in chunks[:6])
        blocks = []
        for c in chunks:
            snippet = " ".join(c["text"].split())[:700]
            blocks.append(f"[{c['doc_id']}] (origin: {c.get('origin')}, "
                          f"year: {c.get('year')}): {snippet}")
        context = "\n\n".join(blocks)
        cons = cons_mod.parse_constraints(query)
        cons_line = (f"\nЧисловые требования запроса: {cons_mod.describe(cons)}. "
                     "Явно отметь, какие источники им удовлетворяют.\n" if cons else "")

        if brief:
            prompt = (
                f"Вопрос эксперта: {query}\n{cons_line}\n"
                f"Фрагменты отчётов R&D (в скобках — ID):\n{context}\n\n"
                "Дай краткий связный ответ строго по фрагментам, Markdown, без "
                "заголовков. После каждого утверждения — ссылка [D-XXXX]. "
                "Ключевые числа выделяй жирным. Не выдумывай.")
            return yandex.complete(prompt, temperature=0.3, max_tokens=800)

        prompt = (
            f"Вопрос эксперта: {query}\n{cons_line}\n"
            f"Ниже — релевантные фрагменты из отчётов R&D (в квадратных скобках — "
            f"ID отчёта):\n{context}\n\n"
            "Составь ответ строго по приведённым фрагментам, в Markdown, без "
            "заголовков уровня #. После каждого утверждения — ссылка [D-XXXX]. "
            "Структура ответа:\n"
            "1) **Обзор** — суть по вопросу, ключевые числа/условия выделяй жирным, "
            "раздели отечественную и зарубежную практику, если уместно.\n"
            "2) **Консенсус и разногласия** — в чём источники согласны, где "
            "противоречат (если противоречий нет — так и напиши).\n"
            "3) **Пробелы** — чего в найденных источниках не хватает для полного "
            "ответа; какие комбинации материал/режим/условие не освещены; что "
            "описано только в отечественной или только в зарубежной практике.\n"
            "4) **Рекомендации** — смежные темы и потенциально применимые решения "
            "из приведённых фрагментов.\n"
            "Не выдумывай факты вне фрагментов.")
        return yandex.complete(prompt, temperature=0.3, max_tokens=1800)

    # ---------- сериализация для фронтенда ----------
    def _node_payload(self, nid: str) -> dict:
        d = self.G.nodes[nid]
        p = {"id": nid, "label": d.get("label", ""), "type": d["type"],
             "color": NODE_TYPES.get(d["type"], {}).get("color", "#888")}
        for k in ("origin", "year", "sentiment"):
            if d.get(k) is not None:
                p[k] = d[k]
        for k in NUMERIC_PARAMS:
            if d.get(k) is not None:
                p[k] = d[k]
        # степень узла для размера вершины в графе
        p["deg"] = self.G.degree(nid)
        return p

    def graph_payload(self, node_ids=None, allowed_types: set | None = None,
                      limit: int | None = None) -> dict:
        H = self.G if node_ids is None else self.G.subgraph(node_ids)
        at = allowed_types or set(NODE_TYPES)
        cand = [nid for nid, d in H.nodes(data=True) if d["type"] in at]
        # для «всего графа» на больших корпусах — топ по степени, чтобы не грузить браузер
        if limit and len(cand) > limit:
            cand = sorted(cand, key=lambda n: self.G.degree(n), reverse=True)[:limit]
        nodes, keep = [], set(cand)
        for nid in cand:
            nodes.append(self._node_payload(nid))
        links = []
        for u, v, d in H.edges(data=True):
            if u in keep and v in keep:
                links.append({"source": u, "target": v, "type": d.get("type"),
                              "contradiction": d.get("type") == "CONTRADICTS"})
        return {"nodes": nodes, "links": links}

    def suggest(self, prefix: str, limit: int = 8) -> list[dict]:
        p = prefix.lower().strip()
        if not p:
            return []
        seen, out = set(), []
        for _, d in self.G.nodes(data=True):
            if d["type"] in ("Material", "Process", "Equipment", "Person"):
                lab = d["label"]
                if p in lab.lower() and lab.lower() not in seen:
                    seen.add(lab.lower())
                    out.append({"text": lab, "type": d["type"]})
        # процессы/материалы вперёд, по позиции вхождения
        out.sort(key=lambda o: (o["text"].lower().find(p), len(o["text"])))
        return out[:limit]


_INSTANCE = None


def get_graph() -> KnowledgeGraph:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = KnowledgeGraph()
    return _INSTANCE
