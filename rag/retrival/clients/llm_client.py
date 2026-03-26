"""
llm_client.py
=============
Provider-switchable async LLM client for HyDE generation.

Supported providers
-------------------
- ``ollama``  — local Ollama server (default, good for dev)
- ``openai``  — OpenAI API (gpt-4o-mini by default, good for prod)

Configuration — all via environment variables
---------------------------------------------
    LLM_PROVIDER   = "ollama" | "openai"        (default: "ollama")
    OLLAMA_HOST    = "http://localhost:11434"    (default)
    OLLAMA_MODEL   = "llama3.2:3b"              (default)
    OPENAI_API_KEY = "sk-..."                   (required for openai)
    OPENAI_MODEL   = "gpt-4o-mini"             (default)

Public API
----------
    chat_complete(prompt, max_tokens=150) -> str   raises on failure
"""

import asyncio
import os
from typing import Any

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


async def chat_complete(prompt: str, max_tokens: int = 150) -> str:
    """
    Single-turn chat completion. Returns the model's response text.

    Raises on any failure — callers are responsible for retry/timeout logic.
    Provider is selected by the LLM_PROVIDER env var at import time.
    """
    if LLM_PROVIDER == "openai":
        return await _openai_complete(prompt, max_tokens)
    return await _ollama_complete(prompt, max_tokens)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _ollama_request(prompt: str, max_tokens: int) -> str:
    """Synchronous Ollama /api/chat call — run via asyncio.to_thread."""
    import requests  # noqa: PLC0415  (deferred; not everyone has this path)

    url = f"{OLLAMA_HOST}/api/chat"
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.1,
            "stop": ["\n\n", "Alternatively", "Here is", "Option "],
        },
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data["message"]["content"].strip()


async def _ollama_complete(prompt: str, max_tokens: int) -> str:
    return await asyncio.to_thread(_ollama_request, prompt, max_tokens)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

async def _openai_complete(prompt: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    content = response.choices[0].message.content
    return (content or "").strip()
