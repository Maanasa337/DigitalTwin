"""Second stage of the hybrid router: a local LLM with tool calling (FR-NL-02).

The model is given the tool schemas from `intents.yaml` and nothing else. It returns a tool name and
arguments; it never returns prose and it never executes anything — the caller re-parses the slots
and runs the tier protocol exactly as it does for a rule match. With no endpoint configured this
returns None and an unmatched utterance falls through to the help prompt, which is the safe default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from twinvoice_nlu.schema import Catalogue, load_catalogue

log = logging.getLogger(__name__)

LLM_CONFIDENCE = 0.75

SYSTEM_PROMPT = """You map a plant operator's utterance to exactly one tool call.
Rules, all mandatory:
- Choose one tool from the provided list. Never invent a tool or an argument name.
- Fill an argument only if the utterance states it. Never guess an asset, a date or a number.
- The utterance may be English, Hindi or Hindi-English code-mixed. Keep argument values verbatim
  from the utterance; do not translate them.
- If no tool fits, call `help`.
Reply with the tool call only."""


@dataclass(frozen=True)
class LlmMatch:
    intent: str
    slots: dict[str, str]
    confidence: float
    raw: dict[str, Any]


def _tool_call(body: dict[str, Any]) -> dict[str, Any] | None:
    """Accept either a real tool_calls response or a JSON object in the content, as Ollama varies."""
    message = body.get("message") or {}
    calls = message.get("tool_calls") or []
    if calls:
        function = calls[0].get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return {"name": function.get("name"), "arguments": arguments or {}}
    content = (message.get("content") or "").strip()
    if not content:
        return None
    parsed = json.loads(content)
    name = parsed.get("name") or parsed.get("intent") or parsed.get("tool")
    arguments = parsed.get("arguments") or parsed.get("parameters") or parsed.get("slots") or {}
    return {"name": name, "arguments": arguments} if name else None


def route(
    text: str,
    *,
    endpoint: str | None,
    model: str = "qwen3",
    catalogue: Catalogue | None = None,
    timeout_s: float = 6.0,
) -> LlmMatch | None:
    if not endpoint:
        return None
    cat = catalogue or load_catalogue()
    try:
        import httpx

        response = httpx.post(
            endpoint,
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "tools": cat.tools(),
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
        call = _tool_call(response.json())
    except Exception:
        # An unreachable or confused LLM must degrade to "I did not understand", never to a guess.
        log.warning("llm router failed, falling back to unknown intent", exc_info=True)
        return None

    if call is None or cat.get(call["name"]) is None:
        return None
    arguments = call["arguments"]
    if not isinstance(arguments, dict):
        return None
    slots = {k: str(v) for k, v in arguments.items() if v not in (None, "")}
    return LlmMatch(intent=call["name"], slots=slots, confidence=LLM_CONFIDENCE, raw=call)
