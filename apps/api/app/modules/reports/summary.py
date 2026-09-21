"""Executive summary and its numeric audit (FR-RP-04).

A 150-word summary is asked of the local LLM from the report's figures alone, then checked: every
number the text states must be present in those figures. A summary that invents a number is
discarded and the deterministic template summary is shipped instead — so an unavailable, slow or
imaginative LLM degrades the prose, never the facts.

Without `TV_LLM_ENDPOINT` the template summary is the summary, which is the default deployment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

WORD_LIMIT = 150
TOLERANCE = 0.005  # a summary may round 62.37 to 62.4, but not to 65

_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
# Small counting words that appear in ordinary prose ("the top 3", "in 24 hours"). Matched
# exactly, never with tolerance: 100 is deliberately absent, because a relative tolerance around it
# is half a percentage point wide and would let a hallucinated "99.9 percent" through.
_ALLOWED_ALWAYS = frozenset({0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0, 12.0, 24.0})

SYSTEM_PROMPT = f"""You write the executive summary of a factory maintenance report.
Rules, all mandatory:
- Use ONLY numbers that appear in the JSON. Never compute, estimate or round to a new value.
- Never introduce a machine, cause or action that is not in the JSON.
- At most {WORD_LIMIT} words, plain language, no bullet points, no preamble, no headings.
- Lead with what changed and what needs attention.
Reply with the summary text only."""


@dataclass(frozen=True)
class SummaryAudit:
    passed: bool
    used_llm: bool
    word_count: int
    unsupported_numbers: list[float] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def numbers_in(text: str) -> list[float]:
    out = []
    for token in _NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return out


def supported_numbers(data: Any) -> set[float]:
    """Every number anywhere in the report data, flattened — nesting is not a hiding place."""
    found: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            found.add(float(node))
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            found.update(numbers_in(node))

    walk(data)
    return found


def audit(text: str, data: Any, *, used_llm: bool) -> SummaryAudit:
    supported = supported_numbers(data)
    unsupported = [value for value in numbers_in(text) if not _is_supported(value, supported)]
    words = len(text.split())
    reason = None
    if unsupported:
        reason = "numbers not present in the report data"
    elif words > WORD_LIMIT:
        reason = f"summary is {words} words, limit is {WORD_LIMIT}"
    return SummaryAudit(
        passed=reason is None,
        used_llm=used_llm,
        word_count=words,
        unsupported_numbers=sorted(set(unsupported)),
        reason=reason,
    )


def _is_supported(value: float, supported: set[float]) -> bool:
    """A figure from the data may be rounded; a prose counting word must match exactly."""
    if value in _ALLOWED_ALWAYS:
        return True
    return any(abs(value - ok) <= TOLERANCE * max(abs(ok), 1.0) for ok in supported)


# ── Template summaries: the ground truth an LLM paraphrase is audited against ──


def template_summary(report_type: str, data: dict[str, Any]) -> str:
    match report_type:
        case "machine_health":
            asset = data.get("asset", {})
            return (
                f"{asset.get('name', 'The machine')} ({asset.get('code', '')}) is at "
                f"{_fmt(data.get('health_pct'))} percent health with {_fmt(data.get('rul'))} "
                f"{data.get('rul_unit', 'cycles')} of remaining life. OEE over the period was "
                f"{_fmt(data.get('oee_pct'))} percent. {data.get('alarm_count', 0)} alarms were raised and "
                f"{data.get('open_work_orders', 0)} work orders are still open."
            )
        case "weekly_maintenance":
            accuracy = data.get("prediction_accuracy_pct")
            accuracy_text = (
                f"Prediction accuracy on {data.get('predictions_scored', 0)} scored orders was "
                f"{_fmt(accuracy)} percent."
                if accuracy is not None
                else "No closed order was scored against its prediction this period."
            )
            return (
                f"{data.get('raised', 0)} work orders were raised on {data.get('scope_name', 'the plant')} "
                f"and {data.get('closed', 0)} were closed. MTBF was {_fmt(data.get('mtbf_h'))} hours and "
                f"MTTR {_fmt(data.get('mttr_h'))} hours across {data.get('breakdowns', 0)} breakdowns. "
                f"{accuracy_text}"
            )
        case "energy":
            return (
                f"{data.get('scope_name', 'The plant')} consumed {_fmt(data.get('energy_kwh'))} kWh, costing "
                f"{_fmt(data.get('cost'))} {data.get('currency', '')} and emitting "
                f"{_fmt(data.get('co2_kg'))} kg of CO2. Peak demand reached "
                f"{_fmt(data.get('peak_demand_kw'))} kW and idle consumption was "
                f"{_fmt(data.get('idle_energy_share_pct'))} percent of the total. "
                f"{data.get('anomaly_count', 0)} consumption anomalies were detected."
            )
        case "benchmark":
            run = data.get("run")
            if not run:
                return "No completed benchmark run is on record yet."
            return (
                f"The most recent benchmark ran on {', '.join(run.get('datasets', []))} with seed "
                f"{run.get('seed')}. {data.get('model_count', 0)} models are in production."
            )
        case "incident":
            asset = data.get("asset", {})
            return (
                f"{asset.get('name', 'The machine')} failed at {data.get('failure_at', '')}. In the "
                f"{data.get('window_hours', 48)} hours either side there were "
                f"{data.get('prediction_count', 0)} predictions, {data.get('alarm_count', 0)} alarms and "
                f"{data.get('work_order_count', 0)} work orders. "
                + (
                    "The recommended action was: " + "; ".join(data["recommended_actions"]) + "."
                    if data.get("recommended_actions")
                    else "No action had been recommended before the failure."
                )
            )
        case _:
            return "No summary is available for this report type."


def _fmt(value: Any) -> str:
    if value is None:
        return "an unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.1f}".rstrip("0").rstrip(".")


# ── The composed summary ──────────────────────────────────────────────


def compose(
    report_type: str,
    data: dict[str, Any],
    *,
    endpoint: str | None,
    model: str = "qwen3",
    timeout_s: float = 10.0,
) -> tuple[str, SummaryAudit]:
    """Return (summary, audit). The template text is the floor; the LLM can only improve on it."""
    template = template_summary(report_type, data)
    candidate = _paraphrase(report_type, data, endpoint=endpoint, model=model, timeout_s=timeout_s)
    if candidate is None:
        return template, audit(template, data, used_llm=False)

    result = audit(candidate, data, used_llm=True)
    if result.passed:
        return candidate, result
    log.info("report summary rejected by audit", extra={"reason": result.reason, "type": report_type})
    return template, result


def _paraphrase(
    report_type: str, data: dict[str, Any], *, endpoint: str | None, model: str, timeout_s: float
) -> str | None:
    if not endpoint:
        return None
    try:
        import httpx

        response = httpx.post(
            endpoint,
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"type": report_type, "data": data}, default=str)},
                ],
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
        return ((response.json().get("message") or {}).get("content") or "").strip() or None
    except Exception:
        log.warning("report summary llm failed, using template", exc_info=True)
        return None
