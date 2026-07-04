"""Извлечение числовых ограничений из запроса эксперта (ТЗ: «сульфаты <200 мг/л»).

Best-effort регулярками: находит (оператор, значение, единица) и опциональный
термин слева. Используется для мягкого буста чанков, где встречается число той же
единицы, удовлетворяющее ограничению, и для явной передачи требований в синтез.
"""
from __future__ import annotations

import re

# нормализация единиц к каноническому виду
_UNIT_ALIASES = {
    "мг/л": "мг/л", "мг/дм3": "мг/л", "мг/дм³": "мг/л", "г/л": "г/л",
    "°c": "°C", "c": "°C", "с": "°C", "%": "%", "т/сут": "т/сут",
    "м3/ч": "м3/ч", "ph": "pH", "мкм": "мкм",
}
_UNIT_RE = r"(мг/дм³|мг/дм3|мг/л|г/л|°c|%|т/сут|м3/ч|ph|мкм)"
_OP_WORDS = {
    "не более": "<=", "не менее": ">=", "менее": "<", "более": ">",
    "до": "<=", "от": ">=", "ниже": "<", "выше": ">", "≤": "<=", "≥": ">=",
    "<=": "<=", ">=": ">=", "<": "<", ">": ">",
}
_NUM = r"(\d+(?:[.,]\d+)?)"


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def parse_constraints(query: str) -> list[dict]:
    """Возвращает список {term, op, value, value2, unit} из запроса."""
    q = query.lower()
    out: list[dict] = []

    # диапазон: «200-300 мг/л», «от 200 до 300 мг/л»
    for m in re.finditer(_NUM + r"\s*[-–]\s*" + _NUM + r"\s*" + _UNIT_RE, q):
        out.append({"term": None, "op": "range", "value": _to_float(m.group(1)),
                    "value2": _to_float(m.group(2)),
                    "unit": _UNIT_ALIASES.get(m.group(3), m.group(3))})

    # оператор + число + единица: «не более 200 мг/л», «<300 мг/дм3», «до 1000 мг/дм3»
    op_pat = "|".join(re.escape(k) for k in sorted(_OP_WORDS, key=len, reverse=True))
    for m in re.finditer(r"(" + op_pat + r")\s*" + _NUM + r"\s*" + _UNIT_RE, q):
        out.append({"term": None, "op": _OP_WORDS[m.group(1)],
                    "value": _to_float(m.group(2)), "value2": None,
                    "unit": _UNIT_ALIASES.get(m.group(3), m.group(3))})
    return out


def chunk_matches(text: str, constraints: list[dict]) -> int:
    """Сколько ограничений подтверждается числом нужной единицы в тексте чанка."""
    if not constraints:
        return 0
    t = text.lower()
    hits = 0
    for c in constraints:
        unit = c["unit"].lower().replace("³", "3")
        # числа рядом с этой единицей
        for m in re.finditer(_NUM + r"\s*" + re.escape(unit), t):
            v = _to_float(m.group(1))
            ok = ((c["op"] == "range" and c["value"] <= v <= c["value2"]) or
                  (c["op"] == "<" and v < c["value"]) or
                  (c["op"] == "<=" and v <= c["value"]) or
                  (c["op"] == ">" and v > c["value"]) or
                  (c["op"] == ">=" and v >= c["value"]))
            if ok:
                hits += 1
                break
    return hits


def extract_facts(text: str, *, limit: int = 6) -> list[str]:
    """Извлекает числовые факты «значение единица» из текста (для верификации)."""
    t = " ".join(text.split())
    out, seen = [], set()
    for m in re.finditer(_NUM + r"\s*[-–]?\s*" + _NUM + r"?\s*" + _UNIT_RE, t):
        v1, v2, unit = m.group(1), m.group(2), m.group(3)
        unit = _UNIT_ALIASES.get(unit.lower(), unit)
        fact = f"{v1}–{v2} {unit}" if v2 else f"{v1} {unit}"
        if fact not in seen:
            seen.add(fact)
            out.append(fact)
        if len(out) >= limit:
            break
    return out


def describe(constraints: list[dict]) -> str:
    """Человекочитаемое описание ограничений для промпта синтеза."""
    parts = []
    for c in constraints:
        if c["op"] == "range":
            parts.append(f"{c['value']:g}–{c['value2']:g} {c['unit']}")
        else:
            parts.append(f"{c['op']} {c['value']:g} {c['unit']}")
    return "; ".join(parts)
