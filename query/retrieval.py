"""Чанк-ретривер по полному тексту корпуса: inverted index → BM25.

Первый этап двухстадийного поиска. Текст каждого документа режется на
перекрывающиеся чанки, по ним строится BM25 (разреженный inverted index на
scipy). При запросе BM25 отдаёт top-N кандидатов, которые дальше переранжирует
LLM-реранкер (см. query/rerank.py). Плотный индекс целиком не строим — корпус
~сотни тысяч чанков, пре-эмбеддинг всего через Yandex нецелесообразен.

Индекс кэшируется на диск (data/bm25_index.pkl) по отпечатку корпуса, чтобы не
пересобирать при каждом старте.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INDEX_FILE = DATA / "bm25_index.pkl"

# токен: кириллица/латиница/цифры, длина ≥2 (ловим «so2», «дм3», «200»)
_TOKEN_RE = r"(?u)\b[а-яёa-z0-9]{2,}\b"

CHUNK_SIZE = 1200     # символов в чанке (крупнее → больше контекста для LLM)
CHUNK_STRIDE = 1000   # шаг (перекрытие 200)
BM25_K1 = 1.5
BM25_B = 0.75


def _corpus_path() -> Path:
    full = DATA / "corpus_full.json"
    return full if full.exists() else DATA / "corpus.json"


def _fingerprint(p: Path) -> str:
    st = p.stat()
    return f"{p.name}:{st.st_size}:{int(st.st_mtime)}:{CHUNK_SIZE}:{CHUNK_STRIDE}"


def _chunk_text(text: str):
    text = text or ""
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []
    out, i, n = [], 0, len(text)
    while i < n:
        piece = text[i:i + CHUNK_SIZE]
        if piece.strip():
            out.append(piece)
        if i + CHUNK_SIZE >= n:
            break
        i += CHUNK_STRIDE
    return out


class ChunkIndex:
    """BM25 по чанкам полного текста корпуса."""

    def __init__(self):
        path = _corpus_path()
        fp = _fingerprint(path)
        if not self._load_cache(fp):
            self._build(path, fp)

    # ---------- построение / кэш ----------
    def _load_cache(self, fp: str) -> bool:
        if not INDEX_FILE.exists():
            return False
        try:
            with open(INDEX_FILE, "rb") as f:
                d = pickle.load(f)
            if d.get("fingerprint") != fp:
                return False
        except Exception:  # noqa: BLE001 — битый кэш → пересобрать
            return False
        self.chunk_doc = d["chunk_doc"]
        self.chunk_text = d["chunk_text"]
        self.doc_meta = d["doc_meta"]
        self.tf = d["tf"]
        self.idf = d["idf"]
        self.doc_len = d["doc_len"]
        self.avgdl = d["avgdl"]
        self.vec = CountVectorizer(lowercase=True, token_pattern=_TOKEN_RE,
                                   vocabulary=d["vocabulary"])
        self.chunk_doc_arr = np.array(self.chunk_doc)
        return True

    def _build(self, path: Path, fp: str):
        import json
        corpus = json.loads(path.read_text(encoding="utf-8"))
        self.chunk_doc, self.chunk_text, self.doc_meta = [], [], {}
        for d in corpus:
            did = d["id"]
            self.doc_meta[did] = {
                "title": d.get("title", ""), "origin": d.get("origin"),
                "year": d.get("year"), "category": d.get("category"),
                "path": d.get("path", ""),
            }
            for chunk in _chunk_text(d.get("text", "")):
                self.chunk_doc.append(did)
                self.chunk_text.append(chunk)
        self.chunk_doc_arr = np.array(self.chunk_doc)

        self.vec = CountVectorizer(lowercase=True, token_pattern=_TOKEN_RE)
        tf = self.vec.fit_transform(self.chunk_text).tocsr()
        self.tf = tf
        n = tf.shape[0]
        df = np.asarray((tf > 0).sum(axis=0)).ravel()
        self.idf = np.log(1.0 + (n - df + 0.5) / (df + 0.5))
        self.doc_len = np.asarray(tf.sum(axis=1)).ravel().astype(np.float64)
        self.avgdl = float(self.doc_len.mean()) if n else 0.0

        try:
            with open(INDEX_FILE, "wb") as f:
                pickle.dump({
                    "fingerprint": fp, "chunk_doc": self.chunk_doc,
                    "chunk_text": self.chunk_text, "doc_meta": self.doc_meta,
                    "tf": self.tf, "idf": self.idf, "doc_len": self.doc_len,
                    "avgdl": self.avgdl, "vocabulary": self.vec.vocabulary_,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:  # noqa: BLE001 — кэш необязателен
            pass

    # ---------- BM25 ----------
    def _bm25_scores(self, query: str) -> np.ndarray:
        q = self.vec.transform([query])
        term_ids = q.indices
        n = self.tf.shape[0]
        if term_ids.size == 0:
            return np.zeros(n, dtype=np.float64)
        tf_q = self.tf[:, term_ids].tocsc()
        idf_q = self.idf[term_ids]
        denom_len = BM25_K1 * (1.0 - BM25_B + BM25_B * self.doc_len / (self.avgdl + 1e-9))
        scores = np.zeros(n, dtype=np.float64)
        coo = tf_q.tocoo()
        contrib = (idf_q[coo.col] * (coo.data * (BM25_K1 + 1.0))
                   / (coo.data + denom_len[coo.row]))
        np.add.at(scores, coo.row, contrib)
        return scores

    def search(self, query: str, *, top_n: int = 60, per_doc: int = 3,
               origin: str | None = None) -> list[dict]:
        """Top-N чанков по BM25 (первый этап). per_doc ограничивает чанки на документ."""
        bm25 = self._bm25_scores(query)
        if not bm25.any():
            return []
        order = np.argsort(-bm25)
        out, seen = [], {}
        for i in order:
            if bm25[i] <= 0:
                break
            did = self.chunk_doc[i]
            meta = self.doc_meta.get(did, {})
            if origin and meta.get("origin") != origin:
                continue
            if seen.get(did, 0) >= per_doc:
                continue
            seen[did] = seen.get(did, 0) + 1
            out.append({
                "doc_id": did, "text": self.chunk_text[i].strip(),
                "bm25": float(bm25[i]), "title": meta.get("title", ""),
                "origin": meta.get("origin"), "year": meta.get("year"),
                "category": meta.get("category"), "path": meta.get("path", ""),
            })
            if len(out) >= top_n:
                break
        return out


_INSTANCE: ChunkIndex | None = None


def get_index() -> ChunkIndex:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ChunkIndex()
    return _INSTANCE
