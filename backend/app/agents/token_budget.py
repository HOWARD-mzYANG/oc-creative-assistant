"""Token counting helpers that do not block app startup when offline."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _get_encoder() -> Any | None:
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _estimated_token_cost(char: str) -> float:
    if char.isspace():
        return 0.15
    if ord(char) > 127:
        return 1.0
    return 0.28


def _estimate_tokens(text: str) -> int:
    return max(1, int(sum(_estimated_token_cost(char) for char in text)))


def count_tokens(text: str) -> int:
    """Count tokens with tiktoken when available, otherwise use a safe estimate."""
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    return _estimate_tokens(text)


def truncate_tokens(text: str, cap: int) -> str:
    """Truncate text by token budget without requiring tiktoken at import time."""
    stripped = text.strip()
    if cap <= 0 or not stripped:
        return ""

    encoder = _get_encoder()
    if encoder is not None:
        try:
            tokens = encoder.encode(stripped)
            if len(tokens) <= cap:
                return stripped
            return encoder.decode(tokens[:cap]) + "..."
        except Exception:
            pass

    total = 0.0
    chars: list[str] = []
    for char in stripped:
        total += _estimated_token_cost(char)
        if total > cap:
            return "".join(chars).rstrip() + "..."
        chars.append(char)
    return stripped
