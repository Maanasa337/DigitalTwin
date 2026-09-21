import asyncio
import math
import struct

from twinvoice_contracts.sparkplug import dbirth, ddata, decode_payload

from sim.catalog import Catalog
from sim.engine import SIM_EPOCH
from sim.live import LiveRuntime
from sim.modbus_server import ModbusMirror, float32_words, uint32_words
from sim.publisher import SparkplugEdgeNode, build_metrics
from sim.sensors import MetricDef

DEFS = [
    MetricDef("spindle.vib_rms", "Double", "mm/s"),
    MetricDef("state", "String", ""),
    MetricDef("good_count", "Int64", "count"),
]


def test_birth_metrics_carry_units_and_quality() -> None:
    values = {"spindle.vib_rms": 2.5, "state": "RUNNING", "good_count": 12}
    payload = decode_payload(dbirth(build_metrics(DEFS, values, {}, 1000, birth=True), seq=1))
    metrics = {m["name"]: m for m in payload["metrics"]}
    assert metrics["spindle.vib_rms"]["properties"] == {"engUnit": "mm/s", "Quality": 192}
    assert metrics["state"]["properties"] == {"Quality": 192}
    assert metrics["good_count"]["datatype"] == "Int64"
    assert metrics["good_count"]["value"] == 12
    assert all(m["timestamp"] == 1000 for m in payload["metrics"])


def test_data_metrics_by_name_with_null_quality() -> None:
    values = {"spindle.vib_rms": None, "state": "DOWN", "good_count": 3}
    metrics = build_metrics(DEFS, values, {"spindle.vib_rms": -7}, 5000, birth=False)
    payload = decode_payload(ddata(metrics, seq=200))
    by_name = {m["name"]: m for m in payload["metrics"]}
    assert by_name["spindle.vib_rms"]["is_null"] is True
    assert by_name["spindle.vib_rms"]["properties"] == {"Quality": 0}
    assert by_name["spindle.vib_rms"]["timestamp"] == 4993
    assert by_name["state"]["properties"] == {}
    assert by_name["state"]["value"] == "DOWN"


def test_edge_node_tolerates_missing_broker() -> None:
    node = SparkplugEdgeNode("127.0.0.1", 1, "plant-01", "line-01")
    node.add_device("cnc-01", DEFS)
    node.publish_device("cnc-01", {"state": "RUNNING"}, {})
    assert not node.connected
    node.stop()


def test_modbus_register_image(catalog: Catalog) -> None:
    # Pinned to the sim epoch (Monday 06:00 plant time, shift A) so the asserted RUNNING
    # state does not depend on the day and hour the suite happens to run.
    runtime = LiveRuntime(catalog, seed=2, time_scale=60.0, start=SIM_EPOCH)
    mirror = ModbusMirror(catalog, port=0)
    snapshots = runtime.tick()
    asyncio.run(mirror.publish(snapshots))
    snap = next(s for s in snapshots if s.code == "press-01")
    unit = mirror.units["press-01"]
    assert unit == 6
    image = mirror.images[unit]
    assert image[0] == 0  # RUNNING
    registers = catalog.modbus_registers("press-01")
    flow = struct.unpack(
        ">f", struct.pack(">HH", *image[registers["pump.flow"] : registers["pump.flow"] + 2])
    )
    assert flow[0] == struct.unpack(">f", struct.pack(">f", snap.values["pump.flow"]))[0]
    assert (image[2] << 16 | image[3]) == snap.values["good_count"]


def test_register_encoding_helpers() -> None:
    assert uint32_words(70_000) == (1, 4464)
    assert uint32_words(2**32 + 5) == (0, 5)
    assert math.isnan(struct.unpack(">f", struct.pack(">HH", *float32_words(None)))[0])
