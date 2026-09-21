"""Slot parsing: the raw span a template captured becomes a typed value a tool can use.

Everything here is pure and takes `now` explicitly. A voice command means "friday morning" in the
plant's timezone at the moment it was spoken, not in the worker's timezone whenever the task ran,
so the caller supplies both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from twinvoice_nlu.rules import normalise
from twinvoice_nlu.schema import Intent
from twinvoice_nlu.vocab import (
    KPI_TERMS,
    NUMBER_WORDS,
    PERIOD_TERMS,
    REPORT_TYPE_TERMS,
    SEVERITY_TERMS,
    TIME_OF_DAY,
    VERDICT_TERMS,
    VIEW_TERMS,
    WEEKDAYS,
)

# Words a caller says around a machine name that are never part of it.
_ASSET_NOISE = frozenset({"the", "a", "an", "machine", "asset", "ka", "ki", "ke", "wala", "wali", "pe", "par"})

# Ordered: the first parameter whose marker words appear wins, so "service it next week" is a
# maintenance question even though it also mentions running the machine.
WHAT_IF_PARAMETERS = (
    ("maintenance_at", frozenset({"service", "maintain", "maintenance", "wait", "repair"})),
    ("speed", frozenset({"speed", "rpm", "feed"})),
    ("load", frozenset({"load", "utilisation", "utilization", "duty"})),
)


@dataclass(frozen=True)
class Period:
    code: str
    start: datetime
    end: datetime


def parse_number(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = normalise(text).replace("percent", "").replace("%", "").strip()
    for token in cleaned.split():
        try:
            return float(token)
        except ValueError:
            if token in NUMBER_WORDS:
                return float(NUMBER_WORDS[token])
    return None


def parse_asset(text: str | None) -> str | None:
    """Strip filler and expand a spoken ordinal: "compressor two" stays two tokens for the matcher."""
    if not text:
        return None
    tokens = [t for t in normalise(text).split() if t not in _ASSET_NOISE]
    if not tokens:
        return None
    return " ".join(str(NUMBER_WORDS[t]) if t in NUMBER_WORDS else t for t in tokens)


def parse_period(text: str | None, now: datetime, default: str = "day") -> Period:
    bucket, offset = PERIOD_TERMS.get(normalise(text or ""), (default, 0))
    return _bucket_bounds(bucket, offset, now)


def _bucket_bounds(bucket: str, offset: int, now: datetime) -> Period:
    if bucket == "hour":
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=offset)
        return Period("hour", start, start + timedelta(hours=1))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "day":
        start = midnight + timedelta(days=offset)
        return Period("day", start, start + timedelta(days=1))
    if bucket == "week":
        start = midnight - timedelta(days=midnight.weekday()) + timedelta(weeks=offset)
        return Period("week", start, start + timedelta(weeks=1))
    if bucket == "month":
        first = midnight.replace(day=1)
        for _ in range(abs(offset)):
            first = (first - timedelta(days=1)).replace(day=1) if offset < 0 else _next_month(first)
        return Period("month", first, _next_month(first))
    # A shift has no fixed length here; the analytics layer snaps it to the plant's shift table.
    start = midnight + timedelta(hours=8 * offset)
    return Period("shift", start, start + timedelta(hours=8))


def _next_month(first: datetime) -> datetime:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def parse_datetime(text: str | None, now: datetime) -> datetime | None:
    """Resolve a spoken time to the next matching instant, never a past one (FR-VN-07 validation)."""
    if not text:
        return None
    tokens = normalise(text).split()
    hour = next((TIME_OF_DAY[t] for t in tokens if t in TIME_OF_DAY), 8)
    base = now.replace(hour=hour, minute=0, second=0, microsecond=0)

    if "tomorrow" in tokens or "kal" in tokens:
        return base + timedelta(days=1)
    if "today" in tokens or "aaj" in tokens:
        return base
    weekday = next((WEEKDAYS[t] for t in tokens if t in WEEKDAYS), None)
    if weekday is not None:
        ahead = (weekday - now.weekday()) % 7
        if ahead == 0 or "next" in tokens:
            ahead += 7 if base <= now or "next" in tokens else 0
        return base + timedelta(days=ahead)
    if "week" in tokens or "hafte" in tokens:
        return base + timedelta(weeks=1)
    if any(t in TIME_OF_DAY for t in tokens):
        return base if base > now else base + timedelta(days=1)
    return None


def _lookup(vocab: dict[str, str], text: str | None) -> str | None:
    return vocab.get(normalise(text or "")) if text else None


def infer_missing(intent_name: str, utterance: str, slots: dict[str, str]) -> dict[str, str]:
    """Fill slots a template implies but does not capture.

    "what if we reduce load to 80 percent" carries its parameter in the literal words, not in a
    capture group; the same is true of the verdict in "that explanation is wrong".
    """
    filled = dict(slots)
    text = normalise(utterance)
    if intent_name == "run_what_if" and "parameter" not in filled:
        # Whole tokens only: "at" is a substring of "what", which made every question about load.
        tokens = set(text.split())
        for parameter, markers in WHAT_IF_PARAMETERS:
            if tokens & markers:
                filled["parameter"] = parameter
                break
        else:
            filled["parameter"] = "load"
    if intent_name == "give_feedback" and "verdict" not in filled:
        filled["verdict"] = next((v for term, v in VERDICT_TERMS.items() if term in text), "disagree")
    if (
        intent_name == "navigate_dashboard"
        and not {"view", "asset"} & filled.keys()
        and ("back" in text or "wapas" in text)
    ):
        filled["view"] = "back"
    return filled


def parse_slots(intent: Intent, raw: dict[str, str], now: datetime) -> dict[str, Any]:
    """Raw captures -> typed values, one entry per slot the utterance actually carried."""
    parsed: dict[str, Any] = {}
    for slot in intent.slots:
        value = raw.get(slot.name)
        if value is None:
            continue
        match slot.type:
            case "asset" | "alarm":
                parsed[slot.name] = parse_asset(value)
            case "number":
                parsed[slot.name] = parse_number(value)
            case "kpi":
                parsed[slot.name] = _lookup(KPI_TERMS, value)
            case "severity":
                parsed[slot.name] = _lookup(SEVERITY_TERMS, value)
            case "report_type":
                parsed[slot.name] = _lookup(REPORT_TYPE_TERMS, value)
            case "verdict":
                parsed[slot.name] = _lookup(VERDICT_TERMS, value) or value
            case "view":
                parsed[slot.name] = VIEW_TERMS.get(normalise(value), value)
            case "period":
                period = parse_period(value, now)
                parsed[slot.name] = period.code
                parsed["period_start"] = period.start
                parsed["period_end"] = period.end
            case "datetime":
                parsed[slot.name] = parse_datetime(value, now)
            case _:
                parsed[slot.name] = normalise(value)
        if parsed.get(slot.name) is None:
            parsed.pop(slot.name, None)
    return parsed
