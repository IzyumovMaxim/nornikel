"""Массовое извлечение сущностей по всему corpus.json (многопоточно, с кэшем).

Возобновляемо: уже извлечённые документы (есть в data/extract_cache) пропускаются.
Запуск:  python scripts/extract_all.py [--workers 4]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.extract import CACHE_DIR, extract_doc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    workers = 4
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])

    corpus = json.loads((ROOT / "data" / "corpus.json").read_text(encoding="utf-8"))
    todo = [d for d in corpus if not (CACHE_DIR / f"{d['id']}.json").exists()]
    done0 = len(corpus) - len(todo)
    print(f"Всего: {len(corpus)}, уже готово: {done0}, к извлечению: {len(todo)}, потоков: {workers}")

    t0 = time.time()
    done = 0
    counts = {"yandexgpt": 0, "heuristic": 0}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(extract_doc, d, True, False): d for d in todo}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                res = fut.result()
                counts[res.get("_extractor", "heuristic")] += 1
            except Exception as e:  # noqa: BLE001
                print(f"  [fail] {d['id']}: {str(e)[:70]}")
            done += 1
            if done % 25 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1e-9)
                eta = (len(todo) - done) / max(rate, 1e-9)
                print(f"  {done}/{len(todo)}  ({rate:.1f}/с, ETA {eta/60:.1f} мин)  {counts}")
    print(f"Готово за {(time.time()-t0)/60:.1f} мин. Экстрактор: {counts}")


if __name__ == "__main__":
    main()
