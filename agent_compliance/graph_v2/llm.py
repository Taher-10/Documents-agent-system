from __future__ import annotations

import os

from langchain_groq import ChatGroq

_llm: ChatGroq | None = None


def get_llm() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is required for M2.5 react mapper. "
            "Set it in the environment before invoking graph_v2 workflow."
        )

    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            api_key=api_key,
        )
    return _llm
