"""
llm_client.py
=============
Provider-switchable async LLM client for HyDE generation.

Supported providers
-------------------
- ``ollama``  — local Ollama server (default, good for dev)
- ``openai``  — OpenAI API (gpt-4o-mini by default, good for prod)
- ``groq``    — Groq API (llama-3.3-70b-versatile by default, fast inference)

Configuration — all via environment variables
---------------------------------------------
    LLM_PROVIDER   = "ollama" | "openai" | "groq"  (default: "ollama")
    OLLAMA_HOST    = "http://localhost:11434"        (default)
    OLLAMA_MODEL   = "llama3.2:3b"                  (default)
    OPENAI_API_KEY = "sk-..."                        (required for openai)
    OPENAI_MODEL   = "gpt-4o-mini"                  (default)
    GROQ_API_KEY   = "gsk_..."                       (required for groq)
    GROQ_MODEL     = "llama-3.3-70b-versatile"       (default)

Public API
----------
    chat_complete(prompt, max_tokens=150) -> str   raises on failure
"""

import asyncio
import os
from typing import Any


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama")


def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


async def chat_complete(prompt: str, max_tokens: int = 150, timeout: int = 30) -> str:
    """
    Single-turn chat completion. Returns the model's response text.

    Raises on any failure — callers are responsible for retry/timeout logic.
    Provider is selected by the LLM_PROVIDER env var at import time.

    Args:
        timeout: HTTP request timeout in seconds (default 30). Increase for
                 large prompts that require more generation time.
    """
    provider = _provider()
    if provider == "openai":
        return await _openai_complete(prompt, max_tokens)
    if provider == "groq":
        return await _groq_complete(prompt, max_tokens, timeout)
    return await _ollama_complete(prompt, max_tokens, timeout)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _ollama_request(prompt: str, max_tokens: int, timeout: int = 30) -> str:
    """Synchronous Ollama /api/chat call — run via asyncio.to_thread."""
    import requests  # noqa: PLC0415  (deferred; not everyone has this path)

    url = f"{_ollama_host()}/api/chat"
    payload: dict[str, Any] = {
        "model": _ollama_model(),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.1,
            "stop": ["\n\n", "Alternatively", "Here is", "Option "],
        },
    }
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data["message"]["content"].strip()


async def _ollama_complete(prompt: str, max_tokens: int, timeout: int = 30) -> str:
    return await asyncio.to_thread(_ollama_request, prompt, max_tokens, timeout)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

async def _openai_complete(prompt: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model=_openai_model(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    content = response.choices[0].message.content
    return (content or "").strip()


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

async def _groq_complete(prompt: str, max_tokens: int, timeout: int = 30) -> str:
    from openai import AsyncOpenAI  # noqa: PLC0415  (reuse openai-compatible client)

    client = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=_groq_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        ),
        timeout=timeout,
    )
    content = response.choices[0].message.content
    return (content or "").strip()
