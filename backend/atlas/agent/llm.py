"""Model factory. Groq by default (fast, free tier); models are configurable via env."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from ..config import get_settings


@lru_cache(maxsize=8)
def get_llm(role: str = "reasoning", temperature: float = 0.1) -> BaseChatModel:
    from langchain_groq import ChatGroq

    s = get_settings()
    if s.groq_api_key is None or not s.groq_api_key.get_secret_value():
        raise RuntimeError("GROQ_API_KEY is not set. Add it to .env (free key: https://console.groq.com/keys).")
    model = {"reasoning": s.llm_reasoning_model, "fast": s.llm_fast_model}[role]
    return ChatGroq(
        model=model,
        api_key=s.groq_api_key,
        temperature=temperature,
        max_retries=3,
        timeout=60,
    )
