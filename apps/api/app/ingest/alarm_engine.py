"""Per-message alarm evaluation engine running inside the ingest consumer.

Supports threshold and adaptive (rolling sigma) rules.
ML alarms are raised separately by the inference worker.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, cast

import valkey

log = logging.getLogger(__name__)

HYSTERESIS_S = 30
# Samples kept per adaptive rule, by the window the rule asks for, at roughly 1 Hz.
WINDOW_SAMPLES = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "6h": 21600, "24h": 86400}
DEFAULT_WINDOW = "1h"
MIN_SAMPLES = 30
ADAPTIVE_WINDOW_KEY = "alarm:adapt:{rule_id}"


class AlarmEngine:
    """Stateful alarm evaluator that keeps rolling stats in Valkey for adaptive rules."""

    def __init__(self, valkey_client: valkey.Valkey) -> None:
        self._valkey = valkey_client

    def evaluate_threshold(
        self,
        rule: dict[str, Any],
        sensor_id: uuid.UUID,
        asset_id: uuid.UUID,
        value: float,
        metric_name: str,
        time: datetime,
    ) -> dict[str, Any] | None:
        """Returns an alarm dict if threshold is violated, None otherwise."""
        params = rule["params"]
        rule_id = rule["id"]
        severity = rule["severity"]

        alarm_high = params.get("high")
        alarm_low = params.get("low")

        violated = False
        threshold = None
        direction = ""

        if alarm_high is not None and value > alarm_high:
            violated = True
            threshold = alarm_high
            direction = "above"
        elif alarm_low is not None and value < alarm_low:
            violated = True
            threshold = alarm_low
            direction = "below"

        if not violated:
            return None

        return {
            "rule_id": rule_id,
            "asset_id": asset_id,
            "sensor_id": sensor_id,
            "severity": severity,
            "title": f"{metric_name} {direction} threshold",
            "message": f"{metric_name} = {value:.2f} ({direction} {threshold})",
            "value": value,
            "threshold": threshold,
        }

    def evaluate_adaptive(
        self,
        rule: dict[str, Any],
        sensor_id: uuid.UUID,
        asset_id: uuid.UUID,
        value: float,
        metric_name: str,
        time: datetime,
    ) -> dict[str, Any] | None:
        """Adaptive alarm: tracks rolling mean/std in Valkey, alerts when value deviates > N sigma."""
        params = rule["params"]
        rule_id = rule["id"]
        sigma_threshold = params.get("sigma", 3.0)
        # The rule's own window, not a fixed hour: a rule asking for 15 minutes was silently
        # getting an hour of history, which is a different alarm from the one it configured.
        samples = WINDOW_SAMPLES.get(params.get("window", DEFAULT_WINDOW), WINDOW_SAMPLES[DEFAULT_WINDOW])

        key = ADAPTIVE_WINDOW_KEY.format(rule_id=rule_id)
        self._valkey.rpush(key, json.dumps({"v": value, "t": time.isoformat()}))
        self._valkey.ltrim(key, -samples, -1)
        self._valkey.expire(key, 7200)

        # Compute stats from stored values
        # The sync client is typed as possibly returning an awaitable; this engine only ever
        # holds the synchronous one.
        raw = cast(list[Any], self._valkey.lrange(key, 0, -1))
        if len(raw) < MIN_SAMPLES:  # not enough history to call anything an outlier
            return None

        values = [json.loads(r)["v"] for r in raw]
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        std = variance**0.5

        if std < 1e-10:
            return None

        z_score = abs(value - mean) / std
        if z_score <= sigma_threshold:
            return None

        return {
            "rule_id": rule_id,
            "asset_id": asset_id,
            "sensor_id": sensor_id,
            "severity": rule["severity"],
            "title": f"{metric_name} adaptive alert ({z_score:.1f} sigma)",
            "message": f"{metric_name} = {value:.2f} (mean={mean:.2f}, std={std:.2f}, z={z_score:.1f})",
            "value": value,
            "threshold": mean + sigma_threshold * std,
        }

    def check_return_to_normal(
        self,
        rule: dict[str, Any],
        value: float,
    ) -> bool:
        """Returns True if the value is back within thresholds (for clearing)."""
        params = rule["params"]
        high = params.get("high")
        low = params.get("low")

        above = high is not None and value > high
        below = low is not None and value < low
        return not (above or below)
