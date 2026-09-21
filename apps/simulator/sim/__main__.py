"""Live simulator service: engine + MQTT/Sparkplug + OPC UA + Modbus + control API."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import uvicorn

from sim.api import create_app
from sim.catalog import Catalog
from sim.config import Settings
from sim.live import LiveRuntime, Output, run_live
from sim.modbus_server import ModbusMirror
from sim.opcua_server import OpcUaMirror
from sim.publisher import MqttBridge

log = logging.getLogger("sim")


async def _started(server: OpcUaMirror | ModbusMirror) -> bool:
    try:
        await server.start()
    except Exception:
        log.exception("%s failed to start; continuing without it", type(server).__name__)
        return False
    return True


async def serve(settings: Settings) -> None:
    catalog = Catalog.load()
    runtime = LiveRuntime(catalog, settings.seed, settings.time_scale)
    if settings.scenario:
        runtime.start_scenario(settings.scenario)
    mqtt = MqttBridge(settings.mqtt_host, settings.mqtt_port, runtime)
    mqtt.start()
    candidates: list[OpcUaMirror | ModbusMirror] = []
    if settings.opcua_enabled:
        candidates.append(OpcUaMirror(catalog, runtime.metric_defs))
    if settings.modbus_enabled:
        candidates.append(ModbusMirror(catalog))
    servers = [server for server in candidates if await _started(server)]
    outputs: list[Output] = [mqtt, *servers]
    waveform_sink = mqtt if settings.waveforms_enabled else None
    loop_task = asyncio.create_task(run_live(runtime, outputs, waveform_sink))
    api = uvicorn.Server(
        uvicorn.Config(
            create_app(runtime, settings.export_dir),
            host="0.0.0.0",
            port=settings.api_port,
            log_level="warning",
        )
    )
    log.info(
        "simulator running: seed=%s time_scale=%s scenario=%s api=:%s",
        runtime.seed,
        runtime.time_scale,
        settings.scenario,
        settings.api_port,
    )
    try:
        await api.serve()
    finally:
        loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await loop_task
        mqtt.stop()
        for server in servers:
            with contextlib.suppress(Exception):
                await server.stop()
        log.info("simulator stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    asyncio.run(serve(Settings.from_env()))


if __name__ == "__main__":
    main()
