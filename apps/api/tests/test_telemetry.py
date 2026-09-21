"""Unit tests for the M3 alarm engine.

This module previously imported a `TelemetryQueryRequest` schema and an `alarm_rule_evaluator`
function, neither of which has ever existed; the import error stopped pytest collecting the whole
suite. It is rewritten here against the engine the ingest consumer actually runs.

No database and no Valkey server: the adaptive rule's rolling window is a small in-memory fake, so
the sigma arithmetic is what is under test rather than a client library.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.ingest.alarm_engine import AlarmEngine

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
ASSET = uuid.uuid4()
SENSOR = uuid.uuid4()


class FakeValkey:
    """Just the list operations the adaptive rule uses."""

    def __init__(self) -> None:
        self.lists: dict[str, list[bytes]] = {}

    def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value.encode())

    def ltrim(self, key: str, start: int, end: int) -> None:
        self.lists[key] = self.lists.get(key, [])[start:] if start < 0 else self.lists.get(key, [])

    def expire(self, key: str, seconds: int) -> None:
        pass

    def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        return self.lists.get(key, [])


@pytest.fixture
def engine() -> AlarmEngine:
    return AlarmEngine(FakeValkey())  # type: ignore[arg-type]


def rule(**params: Any) -> dict[str, Any]:
    return {"id": uuid.uuid4(), "severity": "warning", "params": params}


def evaluate(engine: AlarmEngine, spec: dict[str, Any], value: float) -> dict[str, Any] | None:
    return engine.evaluate_threshold(spec, SENSOR, ASSET, value, "spindle.vib_rms", NOW)


# ── Threshold rules ───────────────────────────────────────────────────


def test_a_value_inside_the_band_raises_nothing(engine: AlarmEngine):
    assert evaluate(engine, rule(high=7.1, low=0.5), 4.0) is None


def test_a_value_above_the_high_threshold_raises(engine: AlarmEngine):
    alarm = evaluate(engine, rule(high=7.1), 9.3)
    assert alarm is not None
    assert alarm["threshold"] == 7.1
    assert alarm["value"] == 9.3
    assert "above" in alarm["title"]
    assert alarm["asset_id"] == ASSET


def test_a_value_below_the_low_threshold_raises(engine: AlarmEngine):
    alarm = evaluate(engine, rule(low=2.0), 1.1)
    assert alarm is not None
    assert alarm["threshold"] == 2.0
    assert "below" in alarm["title"]


def test_the_boundary_itself_is_not_a_violation(engine: AlarmEngine):
    """Strictly greater than: a sensor sitting exactly on its limit must not flap."""
    assert evaluate(engine, rule(high=7.1), 7.1) is None
    assert evaluate(engine, rule(low=2.0), 2.0) is None


def test_a_rule_with_no_thresholds_never_fires(engine: AlarmEngine):
    assert evaluate(engine, rule(), 1e6) is None


def test_the_severity_comes_from_the_rule(engine: AlarmEngine):
    spec = {**rule(high=1.0), "severity": "critical"}
    assert evaluate(engine, spec, 5.0)["severity"] == "critical"


# ── Clearing ──────────────────────────────────────────────────────────


def test_return_to_normal_requires_being_inside_every_threshold(engine: AlarmEngine):
    spec = rule(high=7.1, low=2.0)
    assert engine.check_return_to_normal(spec, 4.0)
    assert not engine.check_return_to_normal(spec, 8.0)
    assert not engine.check_return_to_normal(spec, 1.0)


# ── Adaptive rules ────────────────────────────────────────────────────


def adaptive(engine: AlarmEngine, spec: dict[str, Any], value: float) -> dict[str, Any] | None:
    return engine.evaluate_adaptive(spec, SENSOR, ASSET, value, "spindle.vib_rms", NOW)


def test_an_adaptive_rule_stays_quiet_until_it_has_a_window(engine: AlarmEngine):
    """Under thirty samples there is no distribution to be an outlier of."""
    spec = rule(sigma=3.0)
    for _ in range(29):
        assert adaptive(engine, spec, 4.0) is None


def test_an_outlier_fires_once_the_window_is_full(engine: AlarmEngine):
    spec = rule(sigma=3.0)
    for i in range(40):
        assert adaptive(engine, spec, 4.0 + (i % 2) * 0.1) is None
    alarm = adaptive(engine, spec, 50.0)
    assert alarm is not None
    assert "adaptive" in alarm["title"]
    assert alarm["value"] == 50.0


def test_a_constant_signal_never_produces_an_outlier(engine: AlarmEngine):
    """Zero variance would divide by zero; the engine must return None, not raise."""
    spec = rule(sigma=3.0)
    for _ in range(40):
        adaptive(engine, spec, 4.0)
    assert adaptive(engine, spec, 4.0) is None


def test_the_stored_window_is_json_decodable(engine: AlarmEngine):
    spec = rule(sigma=3.0)
    adaptive(engine, spec, 4.2)
    stored = engine._valkey.lists[f"alarm:adapt:{spec['id']}"]
    assert json.loads(stored[0])["v"] == 4.2
