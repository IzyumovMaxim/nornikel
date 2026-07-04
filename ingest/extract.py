"""Извлечение сущностей и связей из текста отчёта.

Основной путь — YandexGPT со structured output по доменной онтологии.
Фолбэк — эвристический парсер (регекспы по числам + доменный лексикон), чтобы
пайплайн работал даже без сети. Результат по каждому документу кэшируется.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import yandex  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "extract_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM = (
    "Ты — система извлечения знаний для R&D графа горно-металлургической отрасли. "
    "Извлекаешь сущности и связи строго в формате JSON, без комментариев."
)

PROMPT_TMPL = """Из текста научно-технического отчёта извлеки сущности и верни СТРОГО JSON такого вида:
{{
  "materials": ["входные материалы/вещества (список нормализованных названий)"],
  "products": ["целевые продукты"],
  "process": "основной технологический процесс (одна строка)",
  "equipment": ["оборудование/установки"],
  "team": ["исследователи или подразделения"],
  "parameters": {{"temperature": число_или_null, "recovery": число_или_null,
                  "ph": число_или_null, "grade": число_или_null,
                  "pressure": число_или_null, "duration": число_или_null}},
  "conclusion": {{"text": "краткий вывод", "sentiment": "positive|negative"}}
}}
sentiment = positive, если процесс рекомендован/успешен; negative, если есть потери/не рекомендован.
Числа — только значения без единиц. Если параметра нет — null.

ТЕКСТ ОТЧЁТА:
\"\"\"{text}\"\"\"

JSON:"""

_NUM_PATTERNS = {
    "temperature": r"температур[аеы]\s+([\d.]+)",
    "recovery":    r"извлечени[ея]\s+([\d.]+)",
    "ph":          r"pH\s+([\d.]+)",
    "grade":       r"содержани[ея][^,]*?([\d.]+)\s*%",
    "pressure":    r"давлени[ея]\s+([\d.]+)",
    "duration":    r"длительность\s+([\d.]+)",
}
_NEG_WORDS = ["не обеспеч", "потерь", "не рекомендуется", "нестабильн", "доработк"]


def heuristic_extract(text: str) -> dict:
    """Резервный парсер: числа регекспами, полярность по ключевым словам."""
    from scripts.generate_corpus import (EQUIPMENT, MATERIALS, PROCESSES,
                                          PRODUCTS, TEAMS)
    low = text.lower()
    params = {}
    for key, pat in _NUM_PATTERNS.items():
        m = re.search(pat, low)
        params[key] = float(m.group(1)) if m else None
    process = next((p for p in PROCESSES if p.lower() in low), "")
    sentiment = "negative" if any(w in low for w in _NEG_WORDS) else "positive"
    concl = text.split("Вывод:", 1)[-1].strip() if "Вывод:" in text else ""
    return {
        "materials": [m for m in MATERIALS if m.lower() in low],
        "products": [p for p in PRODUCTS if p.lower() in low],
        "process": process,
        "equipment": [e for e in EQUIPMENT if e.lower() in low],
        "team": [t for t in TEAMS if t.lower() in low],
        "parameters": params,
        "conclusion": {"text": concl, "sentiment": sentiment},
    }


def extract_doc(doc: dict, use_llm: bool = True, cache_on_fallback: bool = True) -> dict:
    cache = CACHE_DIR / f"{doc['id']}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    result = None
    if use_llm and yandex.available():
        try:
            result = yandex.complete_json(
                PROMPT_TMPL.format(text=doc["text"][:6000]),
                system=SYSTEM, temperature=0.0, max_tokens=1500,
            )
            result["_extractor"] = "yandexgpt"
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] LLM extract failed for {doc['id']}: {e}")
    if result is None:
        result = heuristic_extract(doc["text"])
        result["_extractor"] = "heuristic"
        # эвристика на реальных данных бесполезна — не кэшируем, чтобы повторить LLM позже
        if not cache_on_fallback:
            return result

    cache.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    corpus = json.loads((ROOT / "data" / "corpus.json").read_text(encoding="utf-8"))
    use_llm = "--no-llm" not in sys.argv
    counts = {"yandexgpt": 0, "heuristic": 0}
    for i, doc in enumerate(corpus, 1):
        res = extract_doc(doc, use_llm=use_llm)
        counts[res.get("_extractor", "heuristic")] += 1
        print(f"[{i}/{len(corpus)}] {doc['id']} — {res.get('_extractor')} "
              f"({len(res.get('materials', []))} материалов, процесс: {res.get('process', '')[:30]})")
    print(f"\nГотово. Экстрактор: {counts}")


if __name__ == "__main__":
    main()
