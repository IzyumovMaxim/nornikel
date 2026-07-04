"""Сборка графа знаний из корпуса и извлечённых сущностей.

- строит типизированный NetworkX-граф по онтологии;
- дедуплицирует материалы/процессы/оборудование/людей;
- считает эмбеддинги узлов (Yandex) для семантического поиска;
- выявляет противоречия: один материал+процесс с противоположными выводами.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import yandex  # noqa: E402
from ingest.extract import extract_doc  # noqa: E402
from domain.ontology import NUMERIC_PARAMS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _norm(name: str) -> str:
    return name.strip().lower()


def build(use_llm: bool = True, embed: bool = True, cached_only: bool = False) -> nx.MultiDiGraph:
    from ingest.extract import CACHE_DIR  # noqa: PLC0415
    corpus = json.loads((DATA / "corpus.json").read_text(encoding="utf-8"))
    if cached_only:
        corpus = [d for d in corpus if (CACHE_DIR / f"{d['id']}.json").exists()]
        print(f"cached-only: включаю {len(corpus)} уже извлечённых документов")
    G = nx.MultiDiGraph()

    # (материал, процесс) -> список выводов для поиска противоречий
    signatures: dict[tuple, list] = {}

    def add_node(nid, ntype, label, **attrs):
        if not G.has_node(nid):
            G.add_node(nid, type=ntype, label=label, **attrs)
        return nid

    def _slist(ext, key):
        """Список строк из извлечения, устойчиво к null/строке/мусору."""
        v = ext.get(key)
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()] \
            if isinstance(v, list) else []

    for doc in corpus:
        ext = extract_doc(doc, use_llm=use_llm)
        if not isinstance(ext, dict):
            continue

        pub = add_node(doc["id"], "Publication", doc["title"],
                       origin=doc["origin"], year=doc["year"], text=doc["text"])
        exp_id = f"EXP:{doc['id']}"
        raw_params = ext.get("parameters") or {}
        params = {k: (raw_params.get(k) if isinstance(raw_params, dict) and
                      isinstance(raw_params.get(k), (int, float)) else None)
                  for k in NUMERIC_PARAMS}
        add_node(exp_id, "Experiment", f"Эксперимент {doc['id']}",
                 origin=doc["origin"], year=doc["year"], **params)
        G.add_edge(pub, exp_id, key="DESCRIBES", type="DESCRIBES")

        for m in _slist(ext, "team"):
            pid = add_node(f"PER:{_norm(m)}", "Person", m)
            G.add_edge(pub, pid, key="AUTHORED_BY", type="AUTHORED_BY")

        for m in _slist(ext, "materials"):
            mid = add_node(f"MAT:{_norm(m)}", "Material", m)
            G.add_edge(exp_id, mid, key="USES_MATERIAL", type="USES_MATERIAL")
        for p in _slist(ext, "products"):
            mid = add_node(f"MAT:{_norm(p)}", "Material", p)
            G.add_edge(exp_id, mid, key="PRODUCES", type="PRODUCES")

        proc = ext.get("process") or ""
        proc = proc.strip() if isinstance(proc, str) else ""
        if proc:
            prid = add_node(f"PROC:{_norm(proc)}", "Process", proc)
            G.add_edge(exp_id, prid, key="APPLIES_PROCESS", type="APPLIES_PROCESS")
        for e in _slist(ext, "equipment"):
            eid = add_node(f"EQP:{_norm(e)}", "Equipment", e)
            G.add_edge(exp_id, eid, key="USES_EQUIPMENT", type="USES_EQUIPMENT")

        concl = ext.get("conclusion") or {}
        if not isinstance(concl, dict):
            concl = {}
        ctext = concl.get("text") or ""
        ctext = ctext.strip() if isinstance(ctext, str) else ""
        csent = concl.get("sentiment") if concl.get("sentiment") in ("positive", "negative") else "positive"
        cid = f"CONCL:{doc['id']}"
        add_node(cid, "Conclusion", ctext[:120] or "(вывод)",
                 text=ctext, sentiment=csent, origin=doc["origin"], process=proc)
        G.add_edge(exp_id, cid, key="CONCLUDES", type="CONCLUDES")

        # регистрируем сигнатуры для противоречий
        for m in _slist(ext, "materials"):
            signatures.setdefault((_norm(m), _norm(proc)), []).append(
                (cid, csent, params.get("recovery"))
            )

    # --- противоречия: один материал+процесс, противоположные выводы ---
    n_contra = 0
    for (mat, proc), items in signatures.items():
        if not proc:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                cid_a, sent_a, rec_a = items[i]
                cid_b, sent_b, rec_b = items[j]
                rec_gap = (abs(rec_a - rec_b) if rec_a is not None and rec_b is not None else 0)
                if sent_a != sent_b or rec_gap > 15:
                    G.add_edge(cid_a, cid_b, key=f"CONTRADICTS:{cid_b}",
                               type="CONTRADICTS", material=mat, process=proc,
                               recovery_gap=rec_gap)
                    n_contra += 1

    # --- эмбеддинги: только эксперименты (по ним идёт поиск) ---
    if embed and yandex.available():
        exp_ids = [n for n, d in G.nodes(data=True) if d["type"] == "Experiment"]
        for nid in exp_ids:
            G.nodes[nid]["_emb"] = _exp_text(G, nid)
        _compute_embeddings(G, exp_ids)

    print(f"Граф: {G.number_of_nodes()} узлов, {G.number_of_edges()} рёбер, "
          f"противоречий: {n_contra}")
    return G


def _exp_text(G, exp_id) -> str:
    """Богатый текст эксперимента для семантического поиска: заголовок публикации,
    процесс, материалы, продукты, вывод — а не только числа."""
    mats, prods, proc, title, concl = [], [], None, None, None
    for _, tgt, k in G.out_edges(exp_id, keys=True):
        kt = G[exp_id][tgt][k]["type"]
        lab = G.nodes[tgt]["label"]
        if kt == "USES_MATERIAL":
            mats.append(lab)
        elif kt == "PRODUCES":
            prods.append(lab)
        elif kt == "APPLIES_PROCESS":
            proc = lab
        elif kt == "CONCLUDES":
            concl = G.nodes[tgt].get("text", "")
    for src, _, k in G.in_edges(exp_id, keys=True):
        if G[src][exp_id][k]["type"] == "DESCRIBES":
            title = G.nodes[src]["label"]
    parts = [title or "",
             f"процесс: {proc}" if proc else "",
             "материалы: " + ", ".join(mats) if mats else "",
             "продукты: " + ", ".join(prods) if prods else "",
             concl or ""]
    return ". ".join(p for p in parts if p)[:900] or G.nodes[exp_id]["label"]


def _compute_embeddings(G, ids):
    kept, vecs, fails = [], [], 0
    for i, nid in enumerate(ids, 1):
        txt = G.nodes[nid].get("_emb", G.nodes[nid]["label"])
        try:
            vecs.append(yandex.embed(txt, kind="doc"))
            kept.append(nid)
        except Exception:  # noqa: BLE001 — единичный сбой не должен ронять всю сборку
            fails += 1
        if i % 100 == 0:
            print(f"  эмбеддинги: {i}/{len(ids)} (пропущено {fails})")
    mat = np.vstack(vecs)
    np.savez(DATA / "embeddings.npz", ids=np.array(kept), vectors=mat)
    for nid in ids:
        G.nodes[nid].pop("_emb", None)
    print(f"  сохранено эмбеддингов: {len(kept)} (пропущено {fails})")


def save(G):
    data = nx.node_link_data(G)  # ключ рёбер: "links" (networkx 3.3)
    (DATA / "graph.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сохранено -> {DATA / 'graph.json'}")


def main():
    use_llm = "--no-llm" not in sys.argv
    embed = "--no-embed" not in sys.argv
    cached_only = "--cached-only" in sys.argv
    G = build(use_llm=use_llm, embed=embed, cached_only=cached_only)
    save(G)


if __name__ == "__main__":
    main()
