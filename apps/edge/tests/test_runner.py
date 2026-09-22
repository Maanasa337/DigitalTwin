"""The runner's output is a valid `EdgePrediction`, and it buffers while the broker is unreachable."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt
from twinvoice_contracts.prediction import EdgePrediction
from twinvoice_contracts.sparkplug import DataType, MetricDict, ddata

from edge.config import EdgeConfig, parse_assets
from edge.runner import EdgeRunner
from tests.conftest import SENSORS, SPEC, telemetry

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []
        self.up = True

    def publish(self, topic: str, payload: bytes, qos: int = 0):
        class Info:
            rc = mqtt.MQTT_ERR_SUCCESS if self.up else mqtt.MQTT_ERR_NO_CONN

        if self.up:
            self.published.append((topic, payload))
        return Info()

    def subscribe(self, topics):
        self.subscribed = topics


def make_runner(model_dir: Path, tmp_path: Path) -> tuple[EdgeRunner, FakeClient]:
    config = EdgeConfig(
        assets=parse_assets("cnc-01"),
        model_dir=model_dir,
        buffer_path=tmp_path / "buffer.sqlite",
        log_path=tmp_path / "latency.csv",
    )
    client = FakeClient()
    runner = EdgeRunner(config, client=client)
    runner.connected = True
    return runner, client


def feed(runner: EdgeRunner, n: int) -> list[EdgePrediction]:
    df = telemetry(seed=4)
    out = []
    for i in range(n):
        prediction = runner.handle_sample("cnc-01", T0 + timedelta(seconds=10 * i), {s: df.at[i, s] for s in SENSORS})
        if prediction is not None:
            out.append(prediction)
    return out


def test_every_stride_publishes_a_schema_valid_prediction(model_dir: Path, tmp_path: Path) -> None:
    runner, client = make_runner(model_dir, tmp_path)
    predictions = feed(runner, SPEC.window_size + SPEC.stride)
    assert len(predictions) == 2
    topic, payload = client.published[0]
    assert topic == "twinvoice/pred/cnc-01"
    parsed = EdgePrediction.model_validate_json(payload)
    assert parsed.source == "edge"
    assert parsed.model_version.startswith("rul-synthetic-cnc_mill:")
    assert parsed.window_end - parsed.window_start == timedelta(seconds=10 * (SPEC.window_size - 1))
    assert parsed.explanation is not None and parsed.explanation.attributions
    assert parsed.latency_ms.explain_ms is not None
    assert (tmp_path / "latency.csv").read_text().count("\n") == 3  # header + two predictions


def test_predictions_are_buffered_while_disconnected_and_replayed_in_order(model_dir: Path, tmp_path: Path) -> None:
    runner, client = make_runner(model_dir, tmp_path)
    runner.connected = False
    predictions = feed(runner, SPEC.window_size + 2 * SPEC.stride)
    assert client.published == []
    assert runner.outbox.pending() == len(predictions) == 3

    runner.connected = True
    assert runner.drain() == 3
    ids = [EdgePrediction.model_validate_json(p).id for _, p in client.published]
    assert ids == [p.id for p in predictions]


def test_a_publish_the_broker_rejects_is_queued(model_dir: Path, tmp_path: Path) -> None:
    runner, client = make_runner(model_dir, tmp_path)
    client.up = False
    feed(runner, SPEC.window_size)
    assert runner.outbox.pending() == 1


def test_sparkplug_ddata_is_decoded_and_scored(model_dir: Path, tmp_path: Path) -> None:
    runner, client = make_runner(model_dir, tmp_path)
    df = telemetry(seed=4)

    class Message:
        topic = "spBv1.0/plant-01/DDATA/line-01/cnc-01"

    for i in range(SPEC.window_size):
        msg = Message()
        msg.payload = ddata(  # type: ignore[attr-defined]
            [MetricDict(name=s, datatype=DataType.DOUBLE, value=float(df.at[i, s])) for s in SENSORS],
            seq=i,
            timestamp=int((T0 + timedelta(seconds=i)).timestamp() * 1000),
        )
        runner.on_message(None, None, msg)
    assert len(client.published) == 1
