"""Closed vocabularies for slot types, and the regex fragment each type contributes to a template.

A slot whose values are known ahead of time (a KPI code, a period, a severity) is compiled as an
alternation rather than a wildcard. That is what keeps "what is the oee of line two this week" from
being read as one intent with a four-word KPI name, and it is why the router can tell `get_kpi`
apart from `navigate_dashboard` without asking the LLM.
"""

from __future__ import annotations

import re

# ── Closed vocabularies: surface form -> canonical code ───────────────

KPI_TERMS = {
    "oee": "oee",
    "o e e": "oee",
    "overall equipment effectiveness": "oee",
    "availability": "availability",
    "uptime": "availability",
    "performance": "performance",
    "quality": "quality",
    "mtbf": "mtbf",
    "mean time between failures": "mtbf",
    "mttr": "mttr",
    "mean time to repair": "mttr",
    "energy per unit": "energy_per_unit",
    "energy intensity": "energy_per_unit",
    "specific energy": "energy_per_unit",
    "idle energy share": "idle_energy_share",
    "idle share": "idle_energy_share",
    "peak demand": "peak_demand",
    "peak power": "peak_demand",
}

# period -> (bucket, offset in buckets from the current one)
PERIOD_TERMS = {
    "today": ("day", 0),
    "aaj": ("day", 0),
    "yesterday": ("day", -1),
    "kal": ("day", -1),
    "this week": ("week", 0),
    "is hafte": ("week", 0),
    "last week": ("week", -1),
    "pichle hafte": ("week", -1),
    "this month": ("month", 0),
    "last month": ("month", -1),
    "this shift": ("shift", 0),
    "last shift": ("shift", -1),
    "last hour": ("hour", -1),
    "last 24 hours": ("day", -1),
    "right now": ("hour", 0),
    "now": ("hour", 0),
    "abhi": ("hour", 0),
}

SEVERITY_TERMS = {
    "critical": "critical",
    "high": "high",
    "warning": "warning",
    "warn": "warning",
    "info": "info",
    "minor": "info",
}

# view -> the front-end route the navigate event carries
VIEW_TERMS = {
    "fleet": "/",
    "dashboard": "/",
    "home": "/",
    "twin": "/twin",
    "explorer": "/explorer",
    "trends": "/explorer",
    "alarms": "/alarms",
    "maintenance": "/maintenance",
    "work orders": "/maintenance",
    "schedule": "/maintenance/schedule",
    "gantt": "/maintenance/schedule",
    "production": "/analytics/production",
    "oee": "/analytics/production",
    "energy": "/analytics/energy",
    "power": "/analytics/energy",
    "models": "/models",
    "reports": "/reports",
    "simulation": "/simulation",
    "voice": "/voice",
}

REPORT_TYPE_TERMS = {
    "machine health": "machine_health",
    "health": "machine_health",
    "weekly maintenance": "weekly_maintenance",
    "weekly": "weekly_maintenance",
    "maintenance": "weekly_maintenance",
    "energy": "energy",
    "benchmark": "benchmark",
    "model benchmark": "benchmark",
    "incident": "incident",
    "failure": "incident",
}

VERDICT_TERMS = {
    "wrong": "disagree",
    "incorrect": "disagree",
    "not right": "disagree",
    "disagree": "disagree",
    "galat": "disagree",
    "right": "agree",
    "correct": "agree",
    "agree": "agree",
    "sahi": "agree",
}

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
}  # fmt: skip

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "somwar": 0, "mangalwar": 1, "budhwar": 2, "guruwar": 3, "shukrawar": 4, "shanivar": 5, "ravivar": 6,
}  # fmt: skip

TIME_OF_DAY = {
    "morning": 8, "subah": 8, "noon": 12, "afternoon": 14, "dopahar": 14,
    "evening": 18, "shaam": 18, "night": 22, "raat": 22,
}  # fmt: skip

# ── Noise tolerance (FR-VN-09) ────────────────────────────────────────
#
# Machine noise does not garble a transcript uniformly: it swallows unstressed function words and
# swaps short words for phonetically close ones. The matcher therefore treats these tokens as
# optional, and accepts these substitutions, wherever a template spells them literally. The intent
# suite injects the same damage plus corruption the matcher has never been told about, so the
# measured accuracy is not simply a restatement of this table.

FILLER = frozenset({"the", "a", "an", "is", "its", "are", "me", "do", "please", "of", "we", "i", "to"})

FILLER_PATTERN = "(?:" + "|".join(sorted(map(re.escape, FILLER), key=len, reverse=True)) + ")"

ASR_CONFUSIONS = {
    "two": ("to", "too"),
    "to": ("two", "too"),
    "four": ("for",),
    "for": ("four",),
    "one": ("on", "won"),
    "on": ("one",),
    "what": ("watt",),
    "how": ("now",),
    "show": ("so",),
    "line": ("lane",),
    "is": ("its",),
    "kya": ("kia",),
    "hai": ("he",),
    "batao": ("bata",),
    "ka": ("ke",),
}


def token_alternatives(token: str) -> tuple[str, ...]:
    return (token, *ASR_CONFUSIONS.get(token, ()))


# Widening a literal preposition to a number word ("on" also matching "one") is what lets the
# matcher survive a corrupted transcript, but it also lets the preposition in "work order for cnc
# one" eat the index off the asset. The alternation cannot tell those apart; `rules._best` breaks
# the tie afterwards, by preferring the reading whose asset still looks like a machine.
AMBIGUOUS_LITERALS = frozenset(t for t, alts in ASR_CONFUSIONS.items() if any(a in NUMBER_WORDS for a in alts))


CLOSED_VOCABS: dict[str, dict[str, object]] = {
    "kpi": dict(KPI_TERMS),
    "period": dict(PERIOD_TERMS),
    "severity": dict(SEVERITY_TERMS),
    "view": dict(VIEW_TERMS),
    "report_type": dict(REPORT_TYPE_TERMS),
    "verdict": dict(VERDICT_TERMS),
}

# An asset reference has a shape: a name of one to three words, optionally followed by an index —
# "compressor two", "line one", "press 4", "the cnc mill". Encoding that shape, rather than a flat
# run of up to four words, is what stops a greedy capture at the referent.
#
# The name repeat is lazy so it stops as soon as the rest of the template can match; the index is
# greedy so it is still taken when it is there. Without the lazy name, "work order on {asset} to
# {task}" reads "cnc one to replace" as the machine; without the greedy index, it reads just "cnc".
# A full-match with backtracking still lets the name expand when nothing else can absorb the words,
# which is what keeps a noise-corrupted "cnc on" matching.
_INDEX = r"(?:\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
_REFERENCE = rf"[\w%]+(?:\s+[\w%]+){{0,2}}?(?:\s+{_INDEX})?"

_OPEN_PATTERNS = {
    "asset": _REFERENCE,
    "alarm": _REFERENCE,
    "datetime": r"[\w%]+(?:\s+[\w%]+){0,3}",
    "number": r"\d+|[a-z]+",
    "text": r"[\w%]+(?:\s+[\w%]+){0,6}",
    "enum": r"[\w%]+",
}


def _alternation(vocab: dict[str, object]) -> str:
    """Longest surface first, so "energy per unit" wins over "energy"."""
    return "|".join(re.escape(term) for term in sorted(vocab, key=len, reverse=True))


def slot_pattern(slot_type: str) -> str:
    vocab = CLOSED_VOCABS.get(slot_type)
    if vocab is not None:
        return f"(?:{_alternation(vocab)})"
    return _OPEN_PATTERNS.get(slot_type, _OPEN_PATTERNS["text"])
