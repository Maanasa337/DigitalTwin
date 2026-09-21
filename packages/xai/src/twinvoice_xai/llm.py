"""LLM paraphrase of a narration (FR-XAI-07).

The LLM never sees the model or the raw telemetry — only the finished explanation JSON — and its
output is never shown until `audit.audit_narration` passes it. With no endpoint configured this
returns None and the caller keeps the template text, which is the intended default.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You rewrite machine-maintenance explanations for a plant operator.
Rules, all mandatory:
- Use ONLY the features, values and units present in the JSON. Never introduce another sensor or cause.
- Keep every number within 5% of the JSON value, and keep its unit.
- Keep each feature's direction: a feature 'raising' the estimate must not be described as lowering it.
- Recommend only the action given in reason_card.action. Never suggest a different repair.
- Two or three sentences, plain language, no jargon, no preamble.
Reply with the rewritten text only."""


@dataclass(frozen=True)
class LlmNarration:
    text: str
    model: str
    prompt_hash: str


def prompt_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]


def paraphrase(
    explanation: dict[str, Any],
    template_text: str,
    *,
    endpoint: str | None,
    model: str = "qwen3",
    lang: str = "en",
    timeout_s: float = 8.0,
) -> LlmNarration | None:
    """Ask the configured LLM to rewrite `template_text`. Any failure returns None: the template stands."""
    if not endpoint:
        return None

    payload = {
        "explanation": explanation,
        "template_text": template_text,
        "lang": lang,
    }
    try:
        import httpx

        response = httpx.post(
            endpoint,
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
        text = (response.json().get("message") or {}).get("content", "").strip()
    except Exception:
        # Narration is a presentation nicety; a flaky LLM must never fail the explanation request.
        log.warning("llm paraphrase failed, falling back to template", exc_info=True)
        return None

    if not text:
        return None
    return LlmNarration(text=text, model=model, prompt_hash=prompt_hash(payload))
