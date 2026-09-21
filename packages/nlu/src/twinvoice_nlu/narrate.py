"""Grounded response composition (FR-NL-03).

Every sentence here is built from a tool result. There is no branch that answers from the model's
own knowledge, and a tool that returned nothing produces "I don't have that" rather than a guess —
which is the whole point of the requirement.

A response carries its citations (asset, timestamp, model version) so the transcript shows where the
number came from; the UI renders them under the answer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

EMPTY = {
    "en": "I don't have that yet.",
    "hi": "Mere paas abhi yeh jaankari nahi hai.",
}

HELP_INTRO = {
    "en": (
        "I can report machine status, explain a prediction, list alarms, give KPIs, "
        "run what-ifs, raise work orders and generate reports."
    ),
    "hi": "Main machine ka status, prediction ki wajah, alarms, KPI, what-if, work order aur report bata sakta hoon.",
}

DID_YOU_MEAN = {
    "en": "I didn't catch that. Did you mean {options}?",
    "hi": "Samajh nahi aaya. Kya aapka matlab {options} tha?",
}

NOT_UNDERSTOOD = {
    "en": "I didn't understand that. Say 'help' to hear what I can do.",
    "hi": "Samajh nahi aaya. 'Help' boliye.",
}

HYPOTHETICAL = {
    "en": " This is a simulation, nothing has changed.",
    "hi": " Yeh sirf simulation hai, kuch badla nahi.",
}

_TEMPLATES: dict[str, dict[str, str]] = {
    "get_machine_status": {
        "en": (
            "{asset} is at {health} percent health with {rul} {unit} of life left{interval}. "
            "The main driver is {driver}.{alarms}"
        ),
        "hi": (
            "{asset} ki health {health} percent hai, {rul} {unit} life bachi hai{interval}. "
            "Sabse bada kaaran {driver} hai.{alarms}"
        ),
    },
    # An asset the inference worker has not reached yet. Saying what *is* known beats both an
    # invented number and a flat "I don't have that" about a machine that is plainly running.
    "get_machine_status_unpredicted": {
        "en": "{asset} is {status}. I don't have a health estimate for it yet.{alarms}",
        "hi": "{asset} abhi {status} hai. Iski health ka andaza abhi nahi hai.{alarms}",
    },
    "list_alarms": {
        "en": "{count} open {word} on {scope}.{detail}",
        "hi": "{scope} par {count} {word} khule hain.{detail}",
    },
    "get_kpi": {
        "en": "{kpi} for {scope} {period} is {value}{unit}.",
        "hi": "{scope} ka {kpi} {period} mein {value}{unit} hai.",
    },
    "run_what_if": {
        "en": "With {change}, remaining life goes from {before} to {after} {unit}.",
        "hi": "{change} par life {before} se {after} {unit} ho jaati hai.",
    },
    "create_work_order": {
        "en": "Work order {number} created for {asset}.",
        "hi": "{asset} ke liye work order {number} ban gaya.",
    },
    "acknowledge_alarm": {
        "en": "Alarm on {asset} acknowledged.",
        "hi": "{asset} ka alarm acknowledge ho gaya.",
    },
    "generate_report": {
        "en": "The {type} report is being generated. I'll read the summary when it's ready.",
        "hi": "{type} report ban rahi hai. Taiyaar hote hi summary sunaunga.",
    },
    "set_simulation_scenario": {
        "en": "{scenario} injected into {asset}.",
        "hi": "{asset} mein {scenario} inject ho gaya.",
    },
    "navigate_dashboard": {
        "en": "Opening {target}.",
        "hi": "{target} khol raha hoon.",
    },
    "give_feedback": {
        "en": "Recorded. Thank you{sensor}.",
        "hi": "Darj kar liya. Dhanyavaad{sensor}.",
    },
}


def _pick(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table["en"]


def _number(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def citations(result: dict[str, Any]) -> dict[str, Any]:
    """The provenance the transcript shows: which asset, from when, from which model."""
    return {
        key: result[key]
        for key in ("asset", "asset_code", "at", "model_version", "prediction_id", "explanation_id")
        if result.get(key) is not None
    }


def compose(intent: str, result: dict[str, Any] | None, lang: str = "en", *, hypothetical: bool = False) -> str:
    """Turn a tool result into the sentence the operator hears. No result, no claim."""
    if not result:
        return _pick(EMPTY, lang)
    if intent == "help":
        return _pick(HELP_INTRO, lang)
    if intent == "explain_prediction":
        return result.get("narration") or _pick(EMPTY, lang)
    if intent == "get_counterfactual":
        return result.get("action_text") or _pick(EMPTY, lang)

    if intent == "get_machine_status" and result.get("health_pct") is None and result.get("rul") is None:
        intent = "get_machine_status_unpredicted"

    template = _TEMPLATES.get(intent)
    if template is None:
        return _pick(EMPTY, lang)
    text = _pick(template, lang).format(**_fields(intent, result, lang))
    return text + (_pick(HYPOTHETICAL, lang) if hypothetical else "")


def _fields(intent: str, result: dict[str, Any], lang: str) -> dict[str, Any]:
    match intent:
        case "get_machine_status_unpredicted":
            alarms = int(result.get("open_alarms") or 0)
            return {
                "asset": result.get("asset", "The asset"),
                "status": str(result.get("status", "unknown")).lower(),
                "alarms": f" {alarms} alarm{'s' if alarms != 1 else ''} open." if alarms else "",
            }
        case "get_machine_status":
            interval = result.get("rul_interval") or []
            alarms = int(result.get("open_alarms") or 0)
            return {
                "asset": result.get("asset", "The asset"),
                "health": _number(result.get("health_pct"), 0),
                "rul": _number(result.get("rul"), 0),
                "unit": result.get("rul_unit", "cycles"),
                "interval": (
                    f", between {_number(interval[0])} and {_number(interval[1])}" if len(interval) == 2 else ""
                ),
                "driver": result.get("top_driver") or "not identified yet",
                "alarms": f" {alarms} alarm{'s' if alarms != 1 else ''} open." if alarms else "",
            }
        case "list_alarms":
            count = int(result.get("count") or 0)
            top = result.get("top") or []
            return {
                "count": count,
                "word": "alarm" if count == 1 else "alarms",
                "scope": result.get("scope", "the plant"),
                "detail": (" Most severe: " + ", ".join(top) + ".") if top else "",
            }
        case "get_kpi":
            return {
                "kpi": str(result.get("kpi", "")).replace("_", " "),
                "scope": result.get("scope", "the plant"),
                "period": result.get("period", "today"),
                "value": _number(result.get("value"), 1),
                "unit": f" {result['unit']}" if result.get("unit") else "",
            }
        case "run_what_if":
            return {
                "change": result.get("change", "that change"),
                "before": _number(result.get("baseline_rul"), 0),
                "after": _number(result.get("rul"), 0),
                "unit": result.get("rul_unit", "cycles"),
            }
        case "create_work_order":
            return {"number": result.get("number", ""), "asset": result.get("asset", "the asset")}
        case "acknowledge_alarm":
            return {"asset": result.get("asset", "the asset")}
        case "generate_report":
            return {"type": str(result.get("type", "")).replace("_", " ")}
        case "set_simulation_scenario":
            return {"scenario": result.get("scenario", "the fault"), "asset": result.get("asset", "the asset")}
        case "navigate_dashboard":
            return {"target": result.get("label") or result.get("path", "the dashboard")}
        case "give_feedback":
            sensor = result.get("suspect_sensor")
            return {"sensor": f". I've flagged {sensor}" if sensor else ""}
        case _:
            return {}


def did_you_mean(options: list[str], lang: str = "en") -> str:
    return _pick(DID_YOU_MEAN, lang).format(options=" or ".join(options))


def not_understood(lang: str = "en") -> str:
    return _pick(NOT_UNDERSTOOD, lang)


def period_label(start: datetime, end: datetime) -> str:
    return f"{start:%d %b} to {end:%d %b}"
