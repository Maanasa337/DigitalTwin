"""Deterministic narration (FR-XAI-07).

Template text is the ground truth an LLM paraphrase is audited against, and the fallback shown when
that audit fails. It is composed only from numbers already in the explanation, so it cannot drift.
"""

from __future__ import annotations

from typing import Any

from twinvoice_xai.attribution import Attribution

NARRATION_KINDS = ("status", "why", "confidence", "counterfactual", "report_summary")

TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "status": "{asset} is {health_word} at {health:.0f} out of 100. Estimated remaining useful life "
        "is {rul:.0f} {unit}, between {low:.0f} and {high:.0f}.",
        "status_no_rul": "{asset} is {health_word} at {health:.0f} out of 100.",
        "why": "The main driver is {top_label} at {top_value:g}{top_unit}, {top_direction} the estimate "
        "and accounting for {top_share:.0f}% of it. Next are {others}.",
        "why_single": "The main driver is {top_label} at {top_value:g}{top_unit}, {top_direction} the "
        "estimate and accounting for {top_share:.0f}% of it.",
        "confidence": "Confidence is {label}. {reasons}",
        "counterfactual": "{action} That would move the estimate to about {outcome:.0f} {unit}.",
        "counterfactual_none": "No actionable change was found that reaches {target}.",
        "report_summary": "{asset}: health {health:.0f}, remaining life {rul:.0f} {unit}, "
        "{alarm_count} active alarm(s). Top driver: {top_label}.",
    },
    "hi": {
        "status": "{asset} {health_word} है, स्वास्थ्य 100 में से {health:.0f}। अनुमानित शेष उपयोगी जीवन "
        "{rul:.0f} {unit} है, {low:.0f} से {high:.0f} के बीच।",
        "status_no_rul": "{asset} {health_word} है, स्वास्थ्य 100 में से {health:.0f}।",
        "why": "मुख्य कारण {top_label} है, जो {top_value:g}{top_unit} पर है और अनुमान को {top_direction} "
        "करते हुए उसका {top_share:.0f}% हिस्सा रखता है। इसके बाद {others} हैं।",
        "why_single": "मुख्य कारण {top_label} है, जो {top_value:g}{top_unit} पर है और अनुमान को "
        "{top_direction} करते हुए उसका {top_share:.0f}% हिस्सा रखता है।",
        "confidence": "विश्वास स्तर {label} है। {reasons}",
        "counterfactual": "{action} इससे अनुमान लगभग {outcome:.0f} {unit} हो जाएगा।",
        "counterfactual_none": "{target} तक पहुँचने वाला कोई व्यावहारिक बदलाव नहीं मिला।",
        "report_summary": "{asset}: स्वास्थ्य {health:.0f}, शेष जीवन {rul:.0f} {unit}, "
        "{alarm_count} सक्रिय अलार्म। मुख्य कारण: {top_label}।",
    },
}

HEALTH_WORDS = {
    "en": {"healthy": "healthy", "degrading": "degrading", "critical": "critical"},
    "hi": {"healthy": "स्वस्थ", "degrading": "क्षीण हो रहा", "critical": "गंभीर"},
}

DIRECTION_WORDS = {
    "en": {"raising": "raising", "lowering": "lowering", "neutral": "not moving"},
    "hi": {"raising": "ऊपर", "lowering": "नीचे", "neutral": "स्थिर"},
}


def health_word(health: float, lang: str = "en") -> str:
    words = HEALTH_WORDS.get(lang, HEALTH_WORDS["en"])
    if health >= 70:
        return words["healthy"]
    return words["degrading"] if health >= 40 else words["critical"]


def narrate(kind: str, context: dict[str, Any], lang: str = "en") -> str:
    """Render one narration kind. Unknown kinds raise: a silent empty narration would be shown to a user."""
    if kind not in NARRATION_KINDS:
        raise ValueError(f"unknown narration kind '{kind}'")
    templates = TEMPLATES.get(lang, TEMPLATES["en"])
    key = kind
    if kind == "status" and context.get("rul") is None:
        key = "status_no_rul"
    if kind == "counterfactual" and not context.get("action"):
        key = "counterfactual_none"
    return templates[key].format(**context).strip()


def status_context(
    asset: str, health: float, rul: float | None, low: float | None, high: float | None, unit: str, lang: str = "en"
) -> dict[str, Any]:
    return {
        "asset": asset,
        "health": health,
        "health_word": health_word(health, lang),
        "rul": rul,
        "low": low if low is not None else rul,
        "high": high if high is not None else rul,
        "unit": unit,
    }


def why_context(attributions: list[Attribution], lang: str = "en", top_k: int = 3) -> dict[str, Any]:
    if not attributions:
        raise ValueError("cannot narrate 'why' without attributions")
    top = attributions[0]
    directions = DIRECTION_WORDS.get(lang, DIRECTION_WORDS["en"])
    others = [a.label for a in attributions[1:top_k]]
    return {
        "top_label": top.label,
        "top_value": round(top.value, 3),
        "top_unit": f" {top.unit}" if top.unit else "",
        "top_direction": directions.get(top.direction, top.direction),
        "top_share": top.share * 100,
        "others": ", ".join(others),
    }


def why(attributions: list[Attribution], lang: str = "en", top_k: int = 3) -> str:
    context = why_context(attributions, lang, top_k)
    key = "why" if context["others"] else "why_single"
    return TEMPLATES.get(lang, TEMPLATES["en"])[key].format(**context).strip()
