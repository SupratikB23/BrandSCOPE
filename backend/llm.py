"""
Model routing shared by all engines.

Gemini model names are retired over time (gemini-2.0-flash and gemini-2.5-flash
are both gone for new keys), so the chain lives in one place and can be
overridden without a code change:

    GEMINI_MODELS=gemini-3.5-flash,gemini-3.5-flash-lite   (comma-separated)
"""

import asyncio
import os
import re

DEFAULT_GEMINI_CHAIN = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]
GROQ_FALLBACK_MODEL = "groq/llama-3.3-70b-versatile"

TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")


def gemini_chain() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or list(DEFAULT_GEMINI_CHAIN)


GEMINI_MODEL = gemini_chain()[0]


def gemini_config(temperature: float = 0.75, max_output_tokens: int = 8192, model: str = ""):
    """
    GenerateContentConfig with thinking kept small — thinking tokens count
    against max_output_tokens and would otherwise truncate long articles.
    """
    from google.genai import types as genai_types

    kwargs = dict(temperature=temperature, top_p=0.9, max_output_tokens=max_output_tokens)
    if model.startswith("gemini-2.5"):
        kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
    elif model.startswith("gemini-"):
        kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="low")
    return genai_types.GenerateContentConfig(**kwargs)


def strip_json_fences(raw: str) -> str:
    raw = (raw or "").strip()
    return re.sub(r"^```[a-z]*\n?", "", raw, flags=re.M).rstrip("`").strip()


async def gemini_generate(prompt: str, api_key: str, temperature: float = 0.4) -> tuple[str, str]:
    """
    Try each Gemini model in the chain; transient errors (503 / 429) get one
    retry on the same model first. Returns (text, model_used).
    Raises RuntimeError with the last error when every model fails.
    """
    from google import genai

    client = genai.Client(api_key=api_key)
    last_err: Exception | None = None
    for model in gemini_chain():
        for attempt in range(2):
            try:
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=gemini_config(temperature=temperature, model=model),
                )
                text = (resp.text or "").strip()
                if text:
                    return text, model
                last_err = RuntimeError(f"{model} returned empty text")
                break
            except Exception as e:
                last_err = e
                print(f"[llm] {model} failed: {str(e)[:120]}")
                if attempt == 0 and any(m in str(e) for m in TRANSIENT_MARKERS):
                    await asyncio.sleep(8)
                    continue
                break
    raise RuntimeError(f"All Gemini models failed: {last_err}")
