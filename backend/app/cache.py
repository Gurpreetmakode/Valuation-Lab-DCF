"""
Small shared cache layer for valuation data.

Default behavior is an in-process memory cache, which is enough for local
usage and for one long-running backend process. For deployment/serverless,
configure Upstash Redis REST variables so cached ticker data is shared across
users, refreshes, cold starts, and function instances:

    UPSTASH_REDIS_REST_URL=https://...
    UPSTASH_REDIS_REST_TOKEN=...

All cached data expires after APP_CACHE_TTL_SECONDS / CACHE_TTL_SECONDS,
defaulting to 6 hours.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Optional

import requests

DEFAULT_TTL_SECONDS = 6 * 60 * 60
CACHE_TTL_SECONDS = int(
    os.environ.get("APP_CACHE_TTL_SECONDS")
    or os.environ.get("CACHE_TTL_SECONDS")
    or os.environ.get("FMP_CACHE_TTL_SECONDS")
    or DEFAULT_TTL_SECONDS
)

_UPSTASH_URL = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or ""
_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}


def redis_configured() -> bool:
    return bool(_UPSTASH_URL and _UPSTASH_TOKEN)


def ttl_seconds() -> int:
    return CACHE_TTL_SECONDS


def _memory_get(key: str) -> Optional[Any]:
    cached = _MEMORY_CACHE.get(key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at > time.time():
        return value
    _MEMORY_CACHE.pop(key, None)
    return None


def _memory_set(key: str, value: Any, ttl: int) -> None:
    if ttl <= 0:
        return
    _MEMORY_CACHE[key] = (time.time() + ttl, value)


def _redis_request(command: list[Any]) -> Optional[Any]:
    if not redis_configured():
        return None
    try:
        response = requests.post(
            _UPSTASH_URL,
            headers={"Authorization": f"Bearer {_UPSTASH_TOKEN}"},
            json=command,
            timeout=8,
        )
        response.raise_for_status()
        return response.json().get("result")
    except Exception:
        # Cache failure must never break valuation. Fall back to memory/miss.
        return None


def get_json(key: str) -> Optional[Any]:
    """Return cached JSON-like data, or None on miss/expiry/error."""
    memory_value = _memory_get(key)
    if memory_value is not None:
        return memory_value

    result = _redis_request(["GET", key])
    if result is None:
        return None

    try:
        if isinstance(result, str):
            value = json.loads(result)
        else:
            value = result
        _memory_set(key, value, CACHE_TTL_SECONDS)
        return value
    except Exception:
        return None


def set_json(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Cache JSON-serializable data. Falls back to memory if Redis is absent."""
    resolved_ttl = CACHE_TTL_SECONDS if ttl is None else int(ttl)
    if resolved_ttl <= 0:
        return

    _memory_set(key, value, resolved_ttl)

    if redis_configured():
        try:
            payload = json.dumps(value, separators=(",", ":"), default=str)
            _redis_request(["SET", key, payload, "EX", resolved_ttl])
        except Exception:
            pass


def make_key(namespace: str, *parts: Any) -> str:
    """Create a cache-safe key without leaking API keys or long query strings."""
    raw = "|".join(str(part) for part in parts)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"valuation-app:{namespace}:{encoded}"


def clear_memory_cache() -> None:
    _MEMORY_CACHE.clear()


def stats() -> dict[str, Any]:
    return {
        "ttl_seconds": CACHE_TTL_SECONDS,
        "memory_entries": len(_MEMORY_CACHE),
        "redis_configured": redis_configured(),
    }
