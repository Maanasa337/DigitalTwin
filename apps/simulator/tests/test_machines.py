from datetime import UTC, datetime

import pytest

from sim.catalog import Catalog
from sim.engine import Engine, InvalidRequestError, UnknownAssetError
from sim.machines import State

HOUR = 3600.0


def test_fleet_runs_on_shift_with_published_metrics(engine: Engine) -> None:
    engine.advance(HOUR)
    for machine in engine.machines.values():
        assert machine.state is State.RUNNING
        values = machine.metric_values()
        names = [d.name for d in machine.sensor_array.metric_defs]
        assert list(values) == names
        assert machine.power() > machine.asset.rated_power_kw * machine.spec.idle_power_fraction
        assert values["good_count"] > 0
        truth = machine.ground_truth()
        assert truth.true_rul_s is not None and truth.true_rul_s > 0
        assert truth.failure_mode != "none"


def test_sunday_is_idle(catalog: Catalog) -> None:
    sunday_noon = datetime(2026, 1, 11, 6, 30, tzinfo=UTC)  # 12:00 IST
    engine = Engine(catalog, seed=1, tick_s=60.0, start=sunday_noon)
    engine.advance(HOUR)
    for machine in engine.machines.values():
        assert machine.state is State.IDLE
        assert machine.load_pct == 0.0
        idle_kw = machine.asset.rated_power_kw * machine.spec.idle_power_fraction
        assert machine.power() == pytest.approx(idle_kw)


def test_gradual_fault_eventually_brings_machine_down(engine: Engine) -> None:
    engine.inject_fault("cnc-01", "bearing_wear", "gradual", severity=1.0)
    rul_h = engine.asset_status(engine.machines["cnc-01"])["true_rul_h"]
    assert rul_h == pytest.approx(1.0, rel=0.25)
    engine.advance(0.5 * HOUR)
    assert engine.machines["cnc-01"].state is State.RUNNING
    engine.advance(2 * HOUR)
    machine = engine.machines["cnc-01"]
    assert machine.state is State.DOWN
    truth = machine.ground_truth()
    assert (truth.true_rul_s, truth.failure_mode, truth.driver) == (
        0.0,
        "bearing_wear",
        "spindle.vib_rms",
    )
    good = machine.counter.good
    engine.advance(HOUR)
    assert machine.counter.good == good
    idle_kw = machine.asset.rated_power_kw * machine.spec.idle_power_fraction
    assert machine.power() == pytest.approx(idle_kw)
    assert any("DOWN" in entry.message for entry in engine.log)


def test_gradual_fault_raises_signature_metric(engine: Engine) -> None:
    machine = engine.machines["compressor-01"]
    engine.advance(HOUR)
    before = machine.clean["airend.discharge_temp"]
    engine.inject_fault("compressor-01", "overheating", "gradual", severity=0.8)
    peak = before
    while machine.state is State.RUNNING:
        engine.advance(60.0)
        peak = max(peak, machine.clean["airend.discharge_temp"])
    assert machine.state is State.DOWN
    assert peak > before + 15.0


def test_sudden_full_severity_is_immediate_failure(engine: Engine) -> None:
    engine.inject_fault("press-01", "seal_leakage", "sudden", severity=1.0)
    machine = engine.machines["press-01"]
    assert machine.state is State.DOWN
    status = engine.asset_status(machine)
    assert status["failure_mode"] == "seal_leakage"
    assert status["true_rul_h"] == 0.0
    assert status["active_modes"][0]["mode"] == "sudden"


def test_reset_clears_damage_then_maintenance_then_running(engine: Engine) -> None:
    engine.inject_fault("moulder-01", "screw_wear", "sudden", severity=1.0)
    machine = engine.machines["moulder-01"]
    assert machine.state is State.DOWN
    assert engine.reset("moulder-01") == ["barrel", "screw", "clamp", "drive"]
    assert all(value == 0.0 for value in machine.ground_truth().damage.values())
    assert machine.state is State.MAINTENANCE
    engine.advance(10 * 60.0)
    assert machine.state is State.MAINTENANCE
    engine.advance(engine.catalog.fleet.maintenance_duration_s)
    assert machine.state is State.RUNNING
    assert engine.asset_status(machine)["active_modes"] == []


def test_component_reset_only_touches_that_component(engine: Engine) -> None:
    engine.advance(HOUR)
    machine = engine.machines["cnc-02"]
    engine.inject_fault("cnc-02", "tool_wear", "sudden", severity=0.5)
    others = {c: d for c, d in machine.ground_truth().damage.items() if c != "tool"}
    assert engine.reset("cnc-02", "tool") == ["tool"]
    damage = machine.ground_truth().damage
    assert damage["tool"] == 0.0
    assert {c: d for c, d in damage.items() if c != "tool"} == others


def test_motor_efficiency_loss_shows_in_power_and_current(engine: Engine) -> None:
    engine.set_load("compressor-02", 80.0)
    engine.advance(HOUR)
    machine = engine.machines["compressor-02"]
    power, current = machine.power(), machine.clean["motor.current"]
    engine.inject_fault("compressor-02", "motor_efficiency_loss", "sudden", severity=0.6)
    engine.advance(60.0)
    assert machine.state is State.RUNNING
    assert machine.power() > power * 1.06
    assert machine.clean["motor.current"] > current * 1.06


def test_sensor_stuck_holds_a_constant_value(engine: Engine) -> None:
    engine.advance(10 * 60.0)
    engine.inject_fault("cnc-01", "sensor_stuck", metric="spindle.temp")
    values = []
    for _ in range(30):
        engine.advance(60.0)
        values.append(engine.machines["cnc-01"].readings["spindle.temp"].value)
    assert len(set(values)) == 1 and values[0] is not None
    assert engine.asset_status(engine.machines["cnc-01"])["sensor_faults"] == [
        {"metric": "spindle.temp", "kind": "sensor_stuck", "until": None}
    ]


def test_sensor_dropout_publishes_null_until_expiry(engine: Engine) -> None:
    engine.inject_fault("conveyor-01", "sensor_dropout", metric="belt.speed", duration_s=600.0)
    machine = engine.machines["conveyor-01"]
    for _ in range(5):
        engine.advance(60.0)
        assert machine.metric_values()["belt.speed"] is None
    until = engine.asset_status(machine)["sensor_faults"][0]["until"]
    assert until is not None and until.endswith("Z")
    engine.advance(10 * 60.0)
    assert machine.metric_values()["belt.speed"] is not None
    assert engine.asset_status(machine)["sensor_faults"] == []


def test_sensor_offset_and_drift_bias_readings(engine: Engine) -> None:
    engine.advance(HOUR)
    machine = engine.machines["press-01"]
    span = 120.0 - -20.0
    engine.inject_fault("press-01", "sensor_offset", severity=0.5, metric="oil.temp")
    engine.advance(60.0)
    offset = machine.readings["oil.temp"].value - machine.clean["oil.temp"]
    assert offset == pytest.approx(0.5 * 0.2 * span, abs=2.0)
    engine.inject_fault("press-01", "sensor_drift", severity=1.0, metric="pump.flow")
    engine.advance(2 * HOUR)
    drift = machine.readings["pump.flow"].value - machine.clean["pump.flow"]
    assert drift == pytest.approx(2 * 0.05 * 200.0, abs=3.0)


def test_invalid_requests(engine: Engine) -> None:
    with pytest.raises(UnknownAssetError):
        engine.inject_fault("cnc-99", "bearing_wear")
    with pytest.raises(InvalidRequestError):
        engine.inject_fault("cnc-01", "belt_slip")
    with pytest.raises(InvalidRequestError):
        engine.inject_fault("cnc-01", "sensor_stuck")
    with pytest.raises(InvalidRequestError):
        engine.inject_fault("cnc-01", "sensor_stuck", metric="belt.speed")
    with pytest.raises(InvalidRequestError):
        engine.inject_fault("cnc-01", "bearing_wear", severity=1.5)
    with pytest.raises(InvalidRequestError):
        engine.set_speed("cnc-01", 130.0)
    with pytest.raises(InvalidRequestError):
        engine.reset("cnc-01", "belt")


def test_set_load_holds_operator_setpoint(engine: Engine) -> None:
    engine.set_load("conveyor-02", 40.0)
    engine.advance(HOUR)
    assert engine.machines["conveyor-02"].load_pct == 40.0


def test_tick_period_change_applies_immediately(catalog: Catalog) -> None:
    engine = Engine(catalog, seed=3, tick_s=1000.0)
    engine.advance(1000.0)
    engine.advance(1000.0)
    engine.set_tick(1.0)
    ticks = []
    engine.on_tick = lambda machine: (
        ticks.append(engine.now_s) if machine.code == "cnc-01" else None
    )
    for _ in range(5):
        engine.advance(1.0)
    assert len(ticks) >= 4
    assert ticks[-1] - ticks[-2] == pytest.approx(1.0)


def test_shift_changes_are_logged(engine: Engine) -> None:
    engine.advance(9 * HOUR)
    messages = [entry.message for entry in engine.log]
    assert "Shift B (Afternoon) started" in messages
