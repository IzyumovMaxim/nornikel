"""Тонкий клиент Yandex Cloud Foundation Models: YandexGPT + embeddings.

Ключи берутся из .env (YC_API_KEY, YC_FOLDER_ID). Эмбеддинги кэшируются на диск,
чтобы демо не зависело от сети и не тратило квоту при перезапусках.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("YC_API_KEY", "")
FOLDER_ID = os.environ.get("YC_FOLDER_ID", "")

_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
_EMBED_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

_HEADERS = {
    "Authorization": f"Api-Key {API_KEY}",
    "Content-Type": "application/json",
    "x-folder-id": FOLDER_ID,
}

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "embed_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def available() -> bool:
    return bool(API_KEY and FOLDER_ID)


def complete(prompt: str, *, system: str = "", temperature: float = 0.2,
             max_tokens: int = 2000, model: str = "yandexgpt/latest",
             retries: int = 5) -> str:
    """Один вызов YandexGPT, возвращает текст ответа."""
    messages = []
    if system:
        messages.append({"role": "system", "text": system})
    messages.append({"role": "user", "text": prompt})
    payload = {
        "modelUri": f"gpt://{FOLDER_ID}/{model}",
        "completionOptions": {"stream": False, "temperature": temperature,
                              "maxTokens": max_tokens},
        "messages": messages,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(_COMPLETION_URL, headers=_HEADERS,
                              data=json.dumps(payload), timeout=60)
            if r.status_code in (401, 403):  # доступ отозван/квота — ретраи бесполезны
                raise PermissionError(f"Yandex {r.status_code} permission denied")
            if r.status_code == 429:  # rate limit
                last_err = RuntimeError("429 rate limit")
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()["result"]["alternatives"][0]["message"]["text"]
        except PermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"YandexGPT completion failed: {last_err}")


def complete_json(prompt: str, **kwargs) -> dict | list:
    """Как complete(), но парсит JSON из ответа (снимает ```json ограждения)."""
    text = complete(prompt, **kwargs).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=0)
    return json.loads(text[start:])


def _embed_one(text: str, model: str) -> np.ndarray:
    payload = {"modelUri": f"emb://{FOLDER_ID}/{model}", "text": text}
    r = requests.post(_EMBED_URL, headers=_HEADERS,
                      data=json.dumps(payload), timeout=60)
    if r.status_code in (401, 403):
        raise PermissionError(f"Yandex {r.status_code} permission denied")
    r.raise_for_status()
    return np.array(r.json()["embedding"], dtype=np.float32)


def embed(text: str, *, kind: str = "doc") -> np.ndarray:
    """Эмбеддинг текста. kind='doc' для документов, 'query' для запросов.

    Yandex рекомендует асимметричные модели text-search-doc / text-search-query.
    Результат кэшируется по хэшу текста.
    """
    model = "text-search-doc/latest" if kind == "doc" else "text-search-query/latest"
    key = hashlib.sha1(f"{model}:{text}".encode()).hexdigest()
    cache_file = _CACHE_DIR / f"{key}.npy"
    if cache_file.exists():
        return np.load(cache_file)
    for attempt in range(8):
        try:
            vec = _embed_one(text, model)
            np.save(cache_file, vec)
            time.sleep(0.05)  # мягкий троттлинг
            return vec
        except Exception:  # noqa: BLE001
            time.sleep(min(1.5 * (attempt + 1), 12))  # бэкофф под rate-лимит
    raise RuntimeError("Yandex embedding failed after retries")
