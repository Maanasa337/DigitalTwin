import logging
import uuid

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


def create_mqtt_client(prefix: str, host: str, port: int) -> mqtt.Client:
    """Connects asynchronously with automatic reconnect; callers add callbacks and call loop_start()."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{prefix}-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv5,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(host, port, keepalive=30)
    return client
