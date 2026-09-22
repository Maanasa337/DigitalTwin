"""Edge runner (FR-EDGE-02): Sparkplug DDATA in, `twinvoice/pred/{asset}` out.

Per asset: decode the Sparkplug payload, add the sample to a rolling window, and on every stride run
ONNX inference and local TreeSHAP, then publish an `EdgePrediction`. Publishing goes through the
SQLite store-and-forward queue whenever the broker is unreachable (FR-EDGE-03), and every prediction's
latency is appended to a CSV for the on-device cost study.
"""

from __future__ import annotations

import csv
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinvoice_contracts.prediction import (
    Confidence,
    EdgeAttribution,
    EdgeExplanation,
    EdgeLatency,
    EdgePrediction,
    RulInterval,
    pred_topic,
)

from edge.buffer import StoreAndForward
from edge.config import EdgeConfig
from edge.features import RollingWindow
from edge.onnx_infer import EdgeModel, latest_bundle_dir
from edge.treeshap_local import LocalExplainer

log = logging.getLogger(__name__)

LATENCY_FIELDS = ["time", "asset", "model_version", "infer_ms", "explain_ms"]


class AssetPipeline:
    """Model, explainer and window for one asset."""

    def __init__(self, code: str, model: EdgeModel) -> None:
        self.code = code
        self.model = model
        self.window = RollingWindow(model.bundle.spec, model.feature_names)
        self.explainer = LocalExplainer(model.bundle.booster_path, model.feature_names)


class EdgeRunner:
    def __init__(self, config: EdgeConfig, client: Any | None = None) -> None:
        self.config = config
        self.pipelines: dict[str, AssetPipeline] = {}
        for binding in config.assets:
            bundle_dir = latest_bundle_dir(config.model_dir, binding.model_name)
            self.pipelines[binding.code] = AssetPipeline(binding.code, EdgeModel(bundle_dir))
            log.info("asset %s -> %s", binding.code, self.pipelines[binding.code].model.model_version)
        self.outbox = StoreAndForward(config.buffer_path)
        self.client = client
        self.connected = False
        self._drain_lock = threading.Lock()

    # ── Scoring ───────────────────────────────────────────────────────

    def handle_sample(self, asset: str, time: datetime, metrics: dict[str, float | None]) -> EdgePrediction | None:
        """Feed one sample; returns (and publishes) a prediction when a window is due."""
        pipeline = self.pipelines.get(asset)
        if pipeline is None or not pipeline.window.add(time, metrics):
            return None
        x = pipeline.window.vector()
        inference = pipeline.model.predict(x)
        explanation, explain_ms = pipeline.explainer.explain(x, self.config.top_k)
        window_start, window_end = pipeline.window.span

        prediction = EdgePrediction(
            id=str(uuid.uuid4()),
            asset_code=asset,
            time=datetime.now(UTC),
            window_start=window_start,
            window_end=window_end,
            model_version=pipeline.model.model_version,
            health_index=inference.health_index,
            anomaly_score=inference.anomaly_score,
            failure_probability=inference.failure_probability,
            rul=RulInterval(**inference.rul) if inference.rul else None,
            confidence=Confidence(label=inference.confidence, reasons=inference.reasons),  # type: ignore[arg-type]
            explanation=EdgeExplanation(
                method=explanation.method,
                base_value=explanation.base_value,
                attributions=[EdgeAttribution(**a.to_dict()) for a in explanation.attributions],
            ),
            latency_ms=EdgeLatency(infer_ms=round(inference.infer_ms, 3), explain_ms=round(explain_ms, 3)),
        )
        self._log_latency(prediction)
        self.publish(prediction)
        return prediction

    def _log_latency(self, prediction: EdgePrediction) -> None:
        path = Path(self.config.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if new:
                writer.writerow(LATENCY_FIELDS)
            writer.writerow(
                [
                    prediction.time.isoformat(),
                    prediction.asset_code,
                    prediction.model_version,
                    prediction.latency_ms.infer_ms,
                    prediction.latency_ms.explain_ms,
                ]
            )

    # ── Publishing and store-and-forward ──────────────────────────────

    def publish(self, prediction: EdgePrediction) -> bool:
        """Send now if the broker takes it, else queue. Returns whether it went out immediately."""
        topic = pred_topic(prediction.asset_code)
        payload = prediction.model_dump_json().encode("utf-8")
        # Anything still queued goes first, so predictions reach the platform in order.
        if self.outbox.pending() == 0 and self._send(topic, payload, 1):
            return True
        self.outbox.enqueue(topic, payload, 1)
        return False

    def _send(self, topic: str, payload: bytes, qos: int) -> bool:
        if self.client is None or not self.connected:
            return False
        import paho.mqtt.client as mqtt

        info = self.client.publish(topic, payload, qos=qos)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def drain(self) -> int:
        with self._drain_lock:
            sent = self.outbox.drain(self._send)
        if sent:
            log.info("replayed %d queued predictions", sent)
        return sent

    # ── MQTT ──────────────────────────────────────────────────────────

    def on_connect(self, client: Any, _userdata: Any, _flags: Any, reason_code: Any, _props: Any = None) -> None:
        if getattr(reason_code, "is_failure", False):
            log.warning("broker refused the connection: %s", reason_code)
            return
        self.connected = True
        topics = [(f"spBv1.0/+/{kind}/+/{asset}", 0) for asset in self.pipelines for kind in ("DDATA", "DBIRTH")]
        client.subscribe(topics)
        log.info(
            "connected; subscribed for %s; %d predictions queued", ", ".join(self.pipelines), self.outbox.pending()
        )
        threading.Thread(target=self.drain, daemon=True).start()

    def on_disconnect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _props: Any = None) -> None:
        self.connected = False
        log.warning("disconnected from broker (%s); buffering predictions", reason_code)

    def on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        from twinvoice_contracts.sparkplug import decode_payload

        try:
            asset = message.topic.rsplit("/", 1)[-1]
            decoded = decode_payload(message.payload)
            ts = decoded.get("timestamp")
            time = datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else datetime.now(UTC)
            metrics = {
                m["name"]: float(m["value"])  # type: ignore[arg-type]
                for m in decoded["metrics"]
                if isinstance(m.get("value"), int | float) and not isinstance(m.get("value"), bool)
            }
            self.handle_sample(asset, time, metrics)
        except Exception:
            log.exception("failed to score message on %s", message.topic)

    def run_forever(self) -> None:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"twinvoice-edge-{uuid.uuid4().hex[:8]}")
        client.reconnect_delay_set(1, 30)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        self.client = client
        # connect_async + loop_forever(retry_first_connection): the runner starts even while the
        # broker is down, buffering until it appears.
        client.connect_async(self.config.mqtt_host, self.config.mqtt_port, keepalive=30)
        client.loop_forever(retry_first_connection=True)
