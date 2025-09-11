from __future__ import annotations
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from openai import AsyncOpenAI
from openai import APIError

class LLMClient:
    """Async OpenAI client with simple on-disk caching and concurrency."""

    def __init__(self, cache_dir: Path):
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # Expose model for metrics callers
        self.model = settings.LLM_MODEL
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sem = asyncio.Semaphore(settings.LLM_CONCURRENCY)

    # ---- cache helpers ----
    def _cache_key(self, model: str, messages: List[Dict[str, Any]], schema: Optional[Dict[str, Any]]) -> str:
        m = hashlib.sha256()
        m.update(model.encode())
        m.update(json.dumps(messages, sort_keys=True).encode())
        if schema:
            m.update(json.dumps(schema, sort_keys=True).encode())
        return m.hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    async def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        if not settings.LLM_CACHE:
            return None
        p = self._cache_path(key)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    async def _write_cache(self, key: str, value: Dict[str, Any]) -> None:
        if not settings.LLM_CACHE:
            return
        p = self._cache_path(key)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- calls ----
    async def acomplete_json(self, messages: List[Dict[str, Any]], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Return structured JSON by running in JSON mode."""
        model = settings.LLM_MODEL
        ck = self._cache_key(model, messages, schema)
        cached = await self._read_cache(ck)
        if cached is not None:
            return cached

        async with self._sem:
            try:
                res = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=model,
                        temperature=settings.LLM_TEMPERATURE,
                        max_tokens=settings.LLM_MAX_TOKENS,
                        response_format={"type": "json_object"},
                        messages=messages,
                    ),
                    timeout=30.0
                )
                text = res.choices[0].message.content
                try:
                    payload = json.loads(text)
                except Exception:
                    payload = {"_raw": text}
            except Exception as e:
                # Fallback: some models require the word 'json' or disallow response_format.
                # Retry without response_format if we hit a validation error.
                msg = str(e)
                if "must contain the word 'json'" in msg or "response_format" in msg or "invalid_request_error" in msg:
                    res = await asyncio.wait_for(
                        self.client.chat.completions.create(
                            model=model,
                            temperature=settings.LLM_TEMPERATURE,
                            max_tokens=settings.LLM_MAX_TOKENS,
                            messages=messages,
                        ),
                        timeout=30.0
                    )
                    text = res.choices[0].message.content
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = {"_raw": text}
                else:
                    raise

        await self._write_cache(ck, payload)
        return payload
