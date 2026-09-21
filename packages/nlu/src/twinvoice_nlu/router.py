"""The hybrid router (FR-NL-02): rules first, LLM second, help last.

The stages are ordered by auditability, not by capability. A rule match can be traced to the exact
template that produced it, so it is preferred even when an LLM is available; the LLM only sees
utterances the grammar could not explain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from twinvoice_nlu import llm_router, rules
from twinvoice_nlu.schema import Catalogue, load_catalogue
from twinvoice_nlu.slots import infer_missing, parse_slots

LOW_CONFIDENCE = 0.6  # below this the assistant asks rather than acts (FR-VN-06)
HELP_INTENT = "help"


@dataclass(frozen=True)
class RouterResult:
    intent: str
    tier: str
    slots: dict[str, Any]
    raw_slots: dict[str, str]
    confidence: float
    router: str  # 'rules' | 'llm' | 'none'
    lang: str
    router_ms: int
    control: str | None = None
    template: str | None = None
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def understood(self) -> bool:
        return self.router != "none" and self.confidence >= LOW_CONFIDENCE


def route(
    text: str,
    *,
    now: datetime,
    lang: str = "en",
    endpoint: str | None = None,
    model: str = "qwen3",
    catalogue: Catalogue | None = None,
) -> RouterResult:
    cat = catalogue or load_catalogue()
    started = time.perf_counter()

    control = rules.control_word(text, cat)
    if control is not None:
        return _result(cat, HELP_INTENT, {}, 1.0, "rules", lang, started, now, control=control)

    hit = rules.match(text, cat)
    if hit is not None:
        return _result(
            cat,
            hit.intent,
            hit.slots,
            hit.confidence,
            "rules",
            hit.lang,
            started,
            now,
            template=hit.template,
            utterance=text,
        )

    guess = llm_router.route(text, endpoint=endpoint, model=model, catalogue=cat)
    if guess is not None:
        return _result(cat, guess.intent, guess.slots, guess.confidence, "llm", lang, started, now, utterance=text)

    return _result(cat, HELP_INTENT, {}, 0.0, "none", lang, started, now)


def _result(
    cat: Catalogue,
    intent_name: str,
    raw_slots: dict[str, str],
    confidence: float,
    router: str,
    lang: str,
    started: float,
    now: datetime,
    *,
    control: str | None = None,
    template: str | None = None,
    utterance: str = "",
) -> RouterResult:
    intent = cat.get(intent_name)
    assert intent is not None, f"unknown intent {intent_name}"
    filled = infer_missing(intent_name, utterance, raw_slots) if utterance else dict(raw_slots)
    slots = parse_slots(intent, filled, now)
    missing = tuple(s.name for s in intent.slots if s.required and s.name not in slots and not s.context)
    return RouterResult(
        intent=intent.name,
        tier=intent.tier,
        slots=slots,
        raw_slots=filled,
        confidence=confidence,
        router=router,
        lang=lang,
        router_ms=int((time.perf_counter() - started) * 1000),
        control=control,
        template=template,
        missing=missing,
    )
