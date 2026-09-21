import re

import yaml

from sim.catalog import SCENARIOS_DIR, SENSOR_FAULT_KINDS, Catalog, ScenarioSpec

CODE = re.compile(r"^[a-z0-9_-]+$")
ASSET_TYPES = {"cnc_mill", "compressor", "conveyor", "hydraulic_press", "injection_moulder"}
SENSOR_KINDS = {
    "vibration", "temperature", "current", "voltage", "power", "pressure", "flow", "speed",
    "torque", "position", "count", "other",
}  # fmt: skip
COMPONENT_TYPES = {
    "motor", "bearing", "spindle", "pump", "belt", "heater", "valve", "tool", "screw", "seal",
    "other",
}  # fmt: skip
PHYSICS = {"wiener", "gamma", "paris", "arrhenius", "taylor", "motor_efficiency", "none"}
ASSET_KEYS = {
    "code", "name", "asset_type", "line_code", "manufacturer", "model", "serial_no", "install_date",
    "fidelity_level", "ideal_cycle_time_s", "rated_power_kw", "position", "components", "sensors",
    "modbus",
}  # fmt: skip
SENSOR_KEYS = {
    "code", "component_code", "metric_name", "name", "unit", "kind", "sample_rate_hz", "min_valid",
    "max_valid", "warn_low", "warn_high", "alarm_low", "alarm_high",
}  # fmt: skip


def test_document_top_level(catalog: Catalog) -> None:
    doc = catalog.document()
    assert set(doc) == {"plant", "lines", "shifts", "assets", "failure_modes", "scenarios"}
    assert doc["plant"] == {"code": "plant-01", "name": "Pune Plant", "timezone": "Asia/Kolkata"}
    assert [(ln["code"], ln["sequence"]) for ln in doc["lines"]] == [("line-01", 1), ("line-02", 2)]
    # The seeder turns these into the plant's shifts, which is what OEE divides by.
    assert [(s["code"], s["starts_local"], s["ends_local"]) for s in doc["shifts"]] == [
        ("A", "06:00", "14:00"),
        ("B", "14:00", "22:00"),
        ("C", "22:00", "06:00"),
    ]
    assert all(s["days_of_week"] == [0, 1, 2, 3, 4, 5] for s in doc["shifts"])


def test_fleet_composition(catalog: Catalog) -> None:
    by_line = {ln.code: [a.code for a in ln.assets] for ln in catalog.fleet.lines}
    assert by_line == {
        "line-01": ["cnc-01", "cnc-02", "compressor-01", "conveyor-01", "conveyor-02"],
        "line-02": ["press-01", "moulder-01", "moulder-02", "compressor-02", "conveyor-03"],
    }


def test_assets_follow_contract(catalog: Catalog) -> None:
    doc = catalog.document()
    for unit_id, asset in enumerate(doc["assets"], start=1):
        assert set(asset) == ASSET_KEYS
        assert CODE.match(asset["code"])
        assert asset["asset_type"] in ASSET_TYPES
        assert asset["fidelity_level"] == 3
        assert set(asset["position"]) == {"x", "y", "z", "rot"}
        for component in asset["components"]:
            assert CODE.match(component["code"])
            assert component["component_type"] in COMPONENT_TYPES
            assert component["physics_model"] in PHYSICS
        component_codes = {c["code"] for c in asset["components"]}
        metric_names = [s["metric_name"] for s in asset["sensors"]]
        assert len(metric_names) == len(set(metric_names))
        for sensor in asset["sensors"]:
            assert set(sensor) == SENSOR_KEYS
            assert CODE.match(sensor["code"])
            assert sensor["kind"] in SENSOR_KINDS
            assert sensor["min_valid"] < sensor["max_valid"]
            if sensor["component_code"] is None:
                assert sensor["metric_name"] == sensor["code"]
            else:
                assert sensor["component_code"] in component_codes
                assert sensor["metric_name"] == f"{sensor['component_code']}.{sensor['code']}"
        bare = {s["metric_name"]: s for s in asset["sensors"] if s["component_code"] is None}
        assert bare["power_kw"]["kind"] == "power" and bare["power_kw"]["unit"] == "kW"
        assert bare["load_pct"]["kind"] == "other" and bare["load_pct"]["unit"] == "%"
        assert asset["modbus"]["unit_id"] == unit_id


def test_modbus_register_map(catalog: Catalog) -> None:
    for asset in catalog.document()["assets"]:
        registers = asset["modbus"]["registers"]
        assert registers["state"] == 0
        assert registers["good_count"] == 2
        assert registers["reject_count"] == 4
        metric_addresses = [registers[s["metric_name"]] for s in asset["sensors"]]
        assert metric_addresses == list(range(10, 10 + 2 * len(asset["sensors"]), 2))


def test_failure_modes(catalog: Catalog) -> None:
    doc = catalog.document()
    metrics_by_type: dict[str, set[str]] = {}
    for asset in doc["assets"]:
        metrics_by_type[asset["asset_type"]] = {s["metric_name"] for s in asset["sensors"]}
    counts: dict[str, int] = {}
    for mode in doc["failure_modes"]:
        counts[mode["asset_type"]] = counts.get(mode["asset_type"], 0) + 1
        assert CODE.match(mode["code"])
        assert 1 <= mode["severity"] <= 4
        assert mode["component_type"] in COMPONENT_TYPES
        assert mode["signature"]["pattern"] in {"trend", "spike", "level"}
        metrics = metrics_by_type[mode["asset_type"]]
        assert mode["driver"] in metrics
        assert set(mode["signature"]["metrics"]) <= metrics
    assert set(counts) == ASSET_TYPES
    assert all(n >= 4 for n in counts.values())
    keys = [(m["asset_type"], m["code"]) for m in doc["failure_modes"]]
    assert len(keys) == len(set(keys))


def test_scenario_files_parse_and_reference_real_things(catalog: Catalog) -> None:
    files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    names = {f.stem for f in files}
    assert {"demo_day", "bearing_failure_cnc01", "energy_drift"} <= names
    assert {f"user_study_{x}" for x in "ABCD"} <= names
    documented = {s["code"]: s for s in catalog.document()["scenarios"]}
    for path in files:
        raw = path.read_text(encoding="utf-8")
        spec = ScenarioSpec.model_validate(yaml.safe_load(raw))
        assert documented[spec.code]["yaml"] == raw
        for event in spec.events:
            asset_type = catalog.asset(event.asset).asset_type
            modes = {m.code for _, m in catalog.types[asset_type].failure_modes}
            if event.action == "inject_fault":
                assert event.failure_mode in modes
            if event.action == "sensor_fault":
                assert event.failure_mode in SENSOR_FAULT_KINDS
                assert event.metric in catalog.sensor_specs(event.asset)
