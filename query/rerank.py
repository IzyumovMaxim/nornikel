"""Второй этап поиска: расширение запроса + LLM-реранжирование (YandexGPT).

BM25 находит по точным словам, но у эксперта в запросе может не быть терминов из
отчёта («обессоливание» vs «обратный осмос»). Поэтому:

  1. expand_query — YandexGPT добавляет к запросу синонимы/смежные термины
     → выше recall на первом (BM25) этапе;
  2. llm_rerank — YandexGPT листвайз-переранжирует top-N кандидатов от BM25 по
     смысловой релевантности (замена cross-encoder, которого нет локально).

Оба шага мягко деградируют: при недоступности LLM возвращается исходный порядок.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import yandex  # noqa: E402


def expand_query(query: str) -> str:
    """Возвращает запрос, дополненный ключевыми терминами/синонимами."""
    if not yandex.available():
        return query
    prompt = (
        "Ты — помощник по поиску в технической базе знаний горно-металлургической "
        "отрасли. Для поискового запроса эксперта верни JSON-массив из 6-12 "
        "ключевых терминов и синонимов (рус/англ), которые помогут найти "
        "релевантные отчёты. Включай конкретные технологии, методы, вещества, "
        "оборудование по теме. Только JSON-массив строк, без пояснений.\n\n"
        f"Запрос: {query}")
    try:
        terms = yandex.complete_json(prompt, temperature=0.2, max_tokens=300)
        if isinstance(terms, list):
            extra = " ".join(str(t) for t in terms if isinstance(t, (str, int, float)))
            return f"{query} {extra}".strip()
    except Exception:  # noqa: BLE001 — без расширения работаем на исходном запросе
        pass
    return query


def llm_rerank(query: str, candidates: list[dict], *, top_k: int = 8,
               pool: int = 30, snippet_chars: int = 420) -> list[dict]:
    """Листвайз-реранжирование кандидатов BM25 через YandexGPT.

    Берёт до `pool` кандидатов, просит модель отранжировать по релевантности и
    отбросить нерелевантные. Возвращает top_k. При сбое — исходный порядок.
    """
    if not candidates:
        return []
    pooled = candidates[:pool]
    if not yandex.available() or len(pooled) <= 1:
        return pooled[:top_k]

    listing = []
    for i, c in enumerate(pooled):
        snip = " ".join(c["text"].split())[:snippet_chars]
        listing.append(f"[{i}] {snip}")
    prompt = (
        f"Вопрос эксперта: {query}\n\n"
        f"Ниже пронумерованные фрагменты отчётов. Отранжируй их по релевантности "
        f"вопросу — от самого релевантного к наименее. Исключи фрагменты, не "
        f"относящиеся к вопросу. Верни JSON-массив номеров (int) в порядке "
        f"релевантности, например [3,0,7]. Только JSON.\n\n"
        + "\n".join(listing))
    try:
        ranking = yandex.complete_json(prompt, temperature=0.0, max_tokens=400)
        idxs = [int(x) for x in ranking
                if isinstance(x, (int, float)) and 0 <= int(x) < len(pooled)]
        seen, ordered = set(), []
        for j in idxs:
            if j not in seen:
                seen.add(j)
                ordered.append(pooled[j])
        if ordered:
            return ordered[:top_k]
    except Exception:  # noqa: BLE001 — сбой ранжирования → исходный порядок BM25
        pass
    return pooled[:top_k]
