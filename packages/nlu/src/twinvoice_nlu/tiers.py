"""Risk tiers and the read-back confirmation protocol (FR-VN-07).

    T0 Query      execute immediately
    T1 Simulate   execute immediately; the answer is marked hypothetical
    T2 Schedule   read back every parameter, wait for the exact word "confirm", validate, execute
    T3 Actuate    T2 plus a second factor (PIN), and refused outright unless TV_ALLOW_T3 is set

The read-back names every parameter that will be written, because the failure this protocol exists
to prevent is not a misheard verb — it is a correctly heard verb applied to the wrong machine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from twinvoice_nlu.rules import normalise
from twinvoice_nlu.schema import Catalogue, load_catalogue

TIERS = ("T0", "T1", "T2", "T3")
CONFIRM_WINDOW_S = 10


def needs_confirmation(tier: str) -> bool:
    return tier in ("T2", "T3")


def needs_second_factor(tier: str) -> bool:
    return tier == "T3"


def is_confirm(text: str, catalogue: Catalogue | None = None) -> bool:
    cat = catalogue or load_catalogue()
    return normalise(text) in {normalise(p) for p in cat.control_phrases("confirm")}


def is_cancel(text: str, catalogue: Catalogue | None = None) -> bool:
    cat = catalogue or load_catalogue()
    return normalise(text) in {normalise(p) for p in cat.control_phrases("cancel")}


# ── Read-back ─────────────────────────────────────────────────────────

_READBACK = {
    "create_work_order": {
        "en": "Creating work order: {task} on {asset}{when}{technician}.",
        "hi": "Work order bana rahe hain: {asset} par {task}{when}{technician}.",
    },
    "acknowledge_alarm": {
        "en": "Acknowledging the {severity} alarm on {asset}.",
        "hi": "{asset} ka {severity} alarm acknowledge kar rahe hain.",
    },
    "generate_report": {
        "en": "Generating the {type} report for {scope}{period}, as {format}.",
        "hi": "{scope} ki {type} report {period} banayi ja rahi hai, {format} mein.",
    },
    "set_simulation_scenario": {
        "en": "Injecting {scenario} into {asset}. This changes the live simulation.",
        "hi": "{asset} mein {scenario} inject kar rahe hain. Yeh live simulation badal dega.",
    },
    "give_feedback": {
        "en": "Recording that you {verdict} with this explanation{reason}.",
        "hi": "Aapki raay darj kar rahe hain: {verdict}{reason}.",
    },
}

_TAIL = {
    "en": " Say confirm or cancel.",
    "hi": " Confirm ya cancel boliye.",
}


def _phrase(value: Any, prefix_en: str, prefix_hi: str, lang: str) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, datetime):
        value = value.strftime("%A %d %B %H:%M")
    return f"{prefix_hi if lang == 'hi' else prefix_en}{value}"


def readback(intent: str, slots: dict[str, Any], lang: str = "en", *, fmt: str = "pdf") -> str:
    """Compose the sentence the operator must agree to. Unknown intents get a generic read-back."""
    template = _READBACK.get(intent, {}).get(lang) or _READBACK.get(intent, {}).get("en")
    if template is None:
        body = ", ".join(f"{k} {v}" for k, v in slots.items() if v not in (None, ""))
        return f"{intent.replace('_', ' ')}: {body}.{_TAIL.get(lang, _TAIL['en'])}"

    filled = template.format(
        task=slots.get("task", "maintenance"),
        asset=slots.get("asset_label") or slots.get("asset") or slots.get("scope") or "the asset",
        when=_phrase(slots.get("when"), ", ", ", ", lang),
        technician=_phrase(slots.get("technician_label") or slots.get("technician"), ", assigned to ", ", ", lang),
        severity=slots.get("severity", "open"),
        type=str(slots.get("type", "")).replace("_", " ") or "machine health",
        scope=slots.get("scope_label") or slots.get("scope") or "the plant",
        period=_phrase(slots.get("period"), " for this ", " ", lang),
        format=fmt.upper(),
        scenario=slots.get("scenario", "a fault"),
        verdict=slots.get("verdict", "disagree"),
        reason=_phrase(slots.get("reason"), ": ", ": ", lang),
    )
    return filled + _TAIL.get(lang, _TAIL["en"])
