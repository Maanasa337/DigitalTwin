"""Twin write-back over MQTT: publish `twinvoice/cmd/{asset}/{command}` and wait for the machine's ack."""

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from app.core.errors import ServiceUnavailableError
from app.core.mqtt import create_mqtt_client

log = logging.getLogger(__name__)

ACK_TOPIC = "twinvoice/ack/+"


@dataclass
class _Pending:
    event: threading.Event
    ack: dict[str, Any] | None = None


class CommandGateway:
    def __init__(self, host: str, port: int) -> None:
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._client = create_mqtt_client("twinvoice-api-cmd", host, port)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason: Any, _props: Any) -> None:
        if reason.is_failure:
            log.warning("mqtt connect refused", extra={"reason": str(reason)})
            return
        client.subscribe(ACK_TOPIC, qos=1)
        self._connected.set()

    def _on_disconnect(self, *_args: Any) -> None:
        self._connected.clear()

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            ack = json.loads(message.payload)
            pending = self._pending.get(str(ack["command_id"]))
        except (ValueError, KeyError, TypeError):
            log.warning("malformed command ack", extra={"topic": message.topic})
            return
        if pending:
            pending.ack = ack
            pending.event.set()

    def execute(
        self,
        asset_code: str,
        command: str,
        params: dict[str, Any],
        *,
        issued_by: str,
        tier: str,
        timeout_s: float,
    ) -> tuple[str, dict[str, Any] | None]:
        """Returns (command_id, ack); ack is None when the machine did not answer in time."""
        if not self.connected:
            raise ServiceUnavailableError("MQTT broker unavailable; command not sent")
        command_id = str(uuid.uuid4())
        pending = _Pending(threading.Event())
        with self._lock:
            self._pending[command_id] = pending
        try:
            payload = {"command_id": command_id, "params": params, "issued_by": issued_by, "tier": tier}
            info = self._client.publish(f"twinvoice/cmd/{asset_code}/{command}", json.dumps(payload), qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise ServiceUnavailableError("MQTT publish failed; command not sent")
            pending.event.wait(timeout_s)
            return command_id, pending.ack
        finally:
            with self._lock:
                self._pending.pop(command_id, None)
