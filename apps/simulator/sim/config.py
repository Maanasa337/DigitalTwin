from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value not in _TRUE | _FALSE:
        raise ValueError(f"{name} must be a boolean, got {raw!r}")
    return value in _TRUE


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    opcua_enabled: bool = True
    modbus_enabled: bool = True
    waveforms_enabled: bool = True
    seed: int = 42
    time_scale: float = 1.0
    scenario: str | None = None
    export_dir: Path = Path("/data/synthetic")
    api_port: int = 8090

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            mqtt_host=env.get("SIM_MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(env.get("SIM_MQTT_PORT", cls.mqtt_port)),
            opcua_enabled=_flag(env, "SIM_OPCUA_ENABLED", cls.opcua_enabled),
            modbus_enabled=_flag(env, "SIM_MODBUS_ENABLED", cls.modbus_enabled),
            waveforms_enabled=_flag(env, "SIM_WAVEFORMS_ENABLED", cls.waveforms_enabled),
            seed=int(env.get("SIM_SEED", cls.seed)),
            time_scale=float(env.get("SIM_TIME_SCALE", cls.time_scale)),
            scenario=env.get("SIM_SCENARIO") or None,
            export_dir=Path(env.get("SIM_EXPORT_DIR", str(cls.export_dir))),
            api_port=int(env.get("SIM_API_PORT", cls.api_port)),
        )
