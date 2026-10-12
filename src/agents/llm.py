"""Groq LLM helper. Optional: degrades honestly when unavailable.

The deterministic validator is always authoritative. This module is only
used to draft hypotheses/recommendations text; it can never change a
calculated PASS/FAIL/REVIEW status.
"""
from __future__ import annotations

from typing import List


class LLMUnavailable(Exception):
    pass


def groq_complete(api_key: str, model: str, system: str, user: str,
                  timeout_s: int = 30, max_tokens: int = 500) -> str:
    """Call Groq chat completions. Raises LLMUnavailable on any failure."""
    if not api_key:
        raise LLMUnavailable("GROQ_API_KEY is empty.")
    try:
        from groq import Groq
    except Exception as e:
        raise LLMUnavailable(f"groq package not installed ({e}).") from e
    try:
        client = Groq(api_key=api_key, timeout=timeout_s)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise LLMUnavailable("Groq returned empty content.")
        return text
    except LLMUnavailable:
        raise
    except Exception as e:
        raise LLMUnavailable(f"Groq call failed: {e}") from e


SYSTEM_PROMPT = (
    "You are a manufacturing quality assistant. You receive DETERMINISTIC validation "
    "facts (already computed, authoritative) and SOP excerpts. Draft possible "
    "explanations and next steps. Rules: "
    "(1) Prefix each explanation line with 'HYPOTHESIS: '. "
    "(2) Prefix each next-step line with 'RECOMMENDED NEXT STEP (requires human approval): '. "
    "(3) Never contradict the given facts. Never invent measurements, batch IDs, "
    "or citations. Never state a final disposition — a human decides."
)


def split_draft(text: str) -> tuple[List[str], List[str]]:
    """Split an LLM draft into (hypotheses, recommendations) by line prefix."""
    hyps: List[str] = []
    recs: List[str] = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*0123456789. ").strip()
        if not s:
            continue
        ul = s.upper()
        if ul.startswith("HYPOTHESIS"):
            hyps.append(s if s.upper().startswith("HYPOTHESIS:") else f"HYPOTHESIS: {s}")
        elif ul.startswith("RECOMMENDED"):
            recs.append(s)
        else:
            hyps.append(f"HYPOTHESIS: {s}")
    return hyps, recs
