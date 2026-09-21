"""Twin write-back commands (FR-DT-04): twinvoice/cmd/{asset}/{command} -> ack payload."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sim.engine import InvalidRequestError, UnknownAssetError, iso
from sim.live import LiveRuntime

COMMAND_TOPIC_FILTER = "twinvoice/cmd/+/+"


def ack_topic(asset_code: str) -> str:
    return f"twinvoice/ack/{asset_code}"


def _number(params: dict[str, Any], key: str) -> float:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidRequestError(f"params.{key} must be a number")
    return float(value)


def _parse(payload: bytes) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidRequestError("payload is not valid JSON") from None
    if not isinstance(data, dict):
        raise InvalidRequestError("payload must be a JSON object")
    return data


def handle_command(
    runtime: LiveRuntime, asset_code: str, command: str, payload: bytes
) -> dict[str, Any]:
    command_id = None
    issued_by = None
    error: str | None = None
    try:
        data = _parse(payload)
        command_id, issued_by = data.get("command_id"), data.get("issued_by")
        params = data.get("params") or {}
        if not isinstance(command_id, str) or not command_id:
            raise InvalidRequestError("command_id is required")
        if not isinstance(params, dict):
            raise InvalidRequestError("params must be an object")
        with runtime.lock:
            engine = runtime.engine
            engine.machine(asset_code)
            match command:
                case "set_load":
                    engine.set_load(asset_code, _number(params, "load_pct"))
                case "set_speed":
                    engine.set_speed(asset_code, _number(params, "speed_pct"))
                case "maintenance_reset":
                    component = params.get("component_code")
                    if component is not None and not isinstance(component, str):
                        raise InvalidRequestError("params.component_code must be a string or null")
                    engine.reset(asset_code, component)
                case _:
                    raise InvalidRequestError(f"unknown command {command}")
    except UnknownAssetError:
        error = f"unknown asset {asset_code}"
    except InvalidRequestError as exc:
        error = str(exc)
    status = "rejected" if error else "accepted"
    with runtime.lock:
        known = asset_code in runtime.engine.machines
        runtime.engine.record(
            "warning" if error else "info",
            f"Command {command} from {issued_by or 'unknown'} {status}"
            + (f": {error}" if error else ""),
            asset_code if known else None,
        )
    return {
        "command_id": command_id,
        "command": command,
        "status": status,
        "error": error,
        "t": iso(datetime.now(UTC)),
    }
