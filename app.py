"""R&D Граф знаний горно-металлургической отрасли — интерфейс исследователя.

Запуск:  streamlit run app.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query.engine import ROLES, get_graph  # noqa: E402
from domain.ontology import NODE_TYPES, NUMERIC_PARAMS  # noqa: E402

st.set_page_config(page_title="R&D Граф знаний · Норникель",
                   page_icon="⛏️", layout="wide")


@st.cache_resource(show_spinner="Загрузка графа знаний…")
def load_kg():
    return get_graph()


kg = load_kg()

# ---------------- боковая панель ----------------
st.sidebar.title("⛏️ R&D Граф знаний")
st.sidebar.caption("Единая карта знаний горно-металлургической отрасли")

role = st.sidebar.selectbox("Роль (RBAC)", list(ROLES.keys()), index=1)
perm = ROLES[role]
allowed_types = perm["types"]
st.sidebar.caption(f"Доступно типов сущностей: {len(allowed_types)}")

origin = st.sidebar.selectbox("Происхождение практики",
                              ["Любое", "Отечественная", "Зарубежная"])
origin_f = None if origin == "Любое" else origin
top_k = st.sidebar.slider("Сколько записей учитывать", 3, 15, 8)

# числовые фильтры
st.sidebar.subheader("Числовые фильтры")
exp_nodes = [d for _, d in kg.G.nodes(data=True) if d["type"] == "Experiment"]
ranges = {}
for param, (name, unit) in NUMERIC_PARAMS.items():
    vals = [d[param] for d in exp_nodes if d.get(param) is not None]
    if not vals:
        continue
    lo, hi = float(min(vals)), float(max(vals))
    if lo == hi:
        continue
    with st.sidebar.expander(f"{name}{' ,' + unit if unit else ''}"):
        on = st.checkbox("Применить фильтр", key=f"chk_{param}")
        rng = st.slider(name, lo, hi, (lo, hi), key=f"sld_{param}")
        if on:
            ranges[param] = rng

# ---------------- основная область ----------------
st.title("Поиск по графу знаний R&D")
st.caption("Задайте вопрос на естественном языке — система найдёт релевантные "
           "эксперименты, построит цепочки и синтезирует ответ со ссылками на отчёты.")

examples = [
    "Флотация пентландита с высоким извлечением",
    "Автоклавное выщелачивание медно-никелевой руды",
    "Отечественные практики конвертирования штейна",
]
col = st.columns(len(examples))
for i, ex in enumerate(examples):
    if col[i].button(ex, use_container_width=True):
        st.session_state["q"] = ex

query = st.text_input("Запрос", key="q",
                      placeholder="например: извлечение никеля флотацией выше 80%")
go = st.button("🔍 Найти", type="primary")

if go and query.strip():
    with st.spinner("Семантический поиск и обход графа…"):
        hits = kg.search_experiments(query, top_k=top_k, ranges=ranges, origin=origin_f)
        contexts = [kg.experiment_context(nid) for nid, _ in hits]

    if not hits:
        st.warning("Ничего не найдено под заданные фильтры. Ослабьте числовые ограничения.")
    else:
        tabs = st.tabs(["📝 Ответ", "🕸️ Граф знаний", "⚠️ Противоречия", "📊 Найденные записи"])

        # --- ответ ---
        with tabs[0]:
            with st.spinner("Синтез ответа (YandexGPT)…"):
                st.markdown(kg.answer(query, contexts))

        # --- граф ---
        with tabs[1]:
            sub = kg.subgraph_for([nid for nid, _ in hits], allowed_types)
            net = Network(height="620px", width="100%", directed=True,
                          bgcolor="#ffffff", font_color="#222")
            net.barnes_hut(spring_length=140)
            for nid, d in sub.nodes(data=True):
                meta = NODE_TYPES.get(d["type"], {"color": "#999"})
                net.add_node(nid, label=d["label"][:34], color=meta["color"],
                             title=f"{d['type']}: {d['label']}", shape="dot", size=18)
            for u, v, ed in sub.edges(data=True):
                col_e = "#d62728" if ed.get("type") == "CONTRADICTS" else "#bbb"
                net.add_edge(u, v, title=ed.get("type"), label="", color=col_e,
                             width=3 if ed.get("type") == "CONTRADICTS" else 1)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
                net.save_graph(f.name)
                html = Path(f.name).read_text(encoding="utf-8")
            components.html(html, height=640)
            legend = "  ".join(f"● {NODE_TYPES[t]['label']}"
                               for t in allowed_types if t in NODE_TYPES)
            st.caption("Типы узлов: " + legend + "  · красное ребро — противоречие")

        # --- противоречия ---
        with tabs[2]:
            if not perm["see_contradictions"]:
                st.info("Просмотр противоречий недоступен для текущей роли.")
            else:
                # процессы/материалы из найденных экспериментов -> релевантные противоречия
                q_proc = {(c.get("process") or "").lower() for c in contexts}
                q_mat = {m.lower() for c in contexts for m in c["materials"]}
                all_c = kg.contradictions()
                rows = [r for r in all_c
                        if r["process"] in q_proc or r["material"] in q_mat] or all_c
                if not rows:
                    st.success("Явных противоречий по запросу не обнаружено.")
                else:
                    st.caption(f"Обнаружено противоречий в графе: {len(rows)}")
                    for r in rows:
                        with st.container(border=True):
                            st.markdown(
                                f"**{r['material']} · {r['process']}** — "
                                f"расхождение по извлечению: {r['recovery_gap']:.0f} п.п.")
                            c1, c2 = st.columns(2)
                            c1.markdown(f"🟩 **[{r['a_id']}]**\n\n{r['a']}")
                            c2.markdown(f"🟥 **[{r['b_id']}]**\n\n{r['b']}")

        # --- таблица ---
        with tabs[3]:
            table = []
            for (nid, score), c in zip(hits, contexts):
                table.append({
                    "Отчёт": (c.get("publication") or "").replace("EXP:", ""),
                    "Релевантность": round(score, 3),
                    "Процесс": c.get("process"),
                    "Материалы": ", ".join(c["materials"])[:40],
                    "Извлечение,%": c["params"].get("recovery"),
                    "Темп.,°C": c["params"].get("temperature"),
                    "Происхождение": c.get("origin"),
                    "Вывод": (c.get("conclusion") or {}).get("sentiment"),
                })
            st.dataframe(table, use_container_width=True, hide_index=True)

st.sidebar.divider()
st.sidebar.caption(f"Узлов: {kg.G.number_of_nodes()} · рёбер: {kg.G.number_of_edges()}")
