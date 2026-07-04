"""Полный ingest корпуса БЕЗ обрезки текста (в отличие от ingest_real.py).

ingest_real.py хранил только первые 9000 символов и 20 страниц PDF — из-за чего
техническое содержание больших отчётов/журналов терялось. Здесь текст берётся
целиком (все страницы, весь документ), для последующего чанк-ретривера.

Переиспользует парсеры из ingest_real (PDF=PyMuPDF, docx, .doc=textutil, pptx, xls).
.rar пропускаются (нет распаковщика). Результат — data/corpus_full.json.

Запуск:  python scripts/build_corpus_full.py ["/path/to/Источники информации/.."]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import ingest_real as ir  # noqa: E402

# снимаем постраничный лимит PDF — берём документ целиком
ir.MAX_PDF_PAGES = 10 ** 9

MIN_CHARS = 200                          # короче — вероятно скан/пустышка
DEFAULT_BASE = "/Users/maximizyumov/Downloads/Задача 2. Научный клубок"


def parse_any(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    fn = ir.PARSERS.get(ext)
    if not fn:
        return ""
    return fn(path)


def main():
    argv = sys.argv[1:]
    limit = None
    if "--limit" in argv:
        li = argv.index("--limit")
        limit = int(argv[li + 1])
        argv = argv[:li] + argv[li + 2:]
    positional = [a for a in argv if not a.startswith("--")]
    base = positional[0] if positional else DEFAULT_BASE
    if not os.path.isdir(base):
        print(f"Нет папки: {base}")
        sys.exit(1)

    docs = []
    n_ok = n_skip = n_err = 0
    t0 = time.time()

    with tempfile.TemporaryDirectory() as workdir:
        files = list(ir.iter_files(base, workdir))
        print(f"Файлов к разбору: {len(files)}")
        for i, (path, cat) in enumerate(sorted(files, key=lambda x: x[0]), 1):
            try:
                text = parse_any(path)
            except Exception as e:  # noqa: BLE001
                n_err += 1
                if n_err <= 20:
                    print(f"  ERR {os.path.basename(path)[:50]}: {e}")
                continue
            if not text or len(text) < MIN_CHARS:
                n_skip += 1
                continue
            n_ok += 1
            docs.append({
                "id": f"D-{n_ok:04d}",
                "title": ir.make_title(text, path),
                "origin": ir.detect_origin(text),
                "year": ir.detect_year(text),
                "category": cat,
                "path": os.path.relpath(path, base),
                "text": text,                      # ПОЛНЫЙ текст, без обрезки
            })
            if i % 100 == 0:
                mb = sum(len(d["text"]) for d in docs) / 1e6
                print(f"  {i}/{len(files)} · документов {n_ok} · {mb:.1f}M символов · "
                      f"{time.time()-t0:.0f}s")
            if limit and n_ok >= limit:
                break

    out = ROOT / "data" / "corpus_full.json"
    out.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    total = sum(len(d["text"]) for d in docs)
    print(f"\nГотово за {time.time()-t0:.0f}s: {n_ok} документов, "
          f"{total/1e6:.1f}M символов (пропущено {n_skip}, ошибок {n_err})")
    print("Категории:", dict(Counter(d["category"] for d in docs)))
    print("Происхождение:", dict(Counter(d["origin"] for d in docs)))
    print(f"-> {out} ({out.stat().st_size/1e6:.0f} MB)")


if __name__ == "__main__":
    main()
