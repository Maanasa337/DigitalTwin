"""Edge runner settings, from environment variables (plain env: the edge has no pydantic-settings)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Asset-code prefix -> asset type, so `EDGE_ASSETS=cnc-01,press-01` needs no type spelled out.
TYPE_BY_PREFIX = {
    "cnc": "cnc_mill",
    "compressor": "compressor",
    "conveyor": "conveyor",
    "press": "hydraulic_press",
    "moulder": "injection_moulder",
}


@dataclass(frozen=True)
class AssetBinding:
    code: str
    model_name: str


@dataclass(frozen=True)
class EdgeConfig:
    assets: list[AssetBinding] = field(default_factory=list)
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    model_dir: Path = Path("data/models")
    buffer_path: Path = Path("data/edge/buffer.sqlite")
    log_path: Path = Path("data/edge/latency.csv")
    top_k: int = 8

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> EdgeConfig:
        env = dict(os.environ if env is None else env)
        return cls(
            assets=parse_assets(env.get("EDGE_ASSETS", "")),
            mqtt_host=env.get("EDGE_MQTT_HOST", "localhost"),
            mqtt_port=int(env.get("EDGE_MQTT_PORT", "1883")),
            model_dir=Path(env.get("EDGE_MODEL_DIR", "data/models")),
            buffer_path=Path(env.get("EDGE_BUFFER_PATH", "data/edge/buffer.sqlite")),
            log_path=Path(env.get("EDGE_LOG_PATH", "data/edge/latency.csv")),
            top_k=int(env.get("EDGE_TOP_K", "8")),
        )


def parse_assets(raw: str) -> list[AssetBinding]:
    """`cnc-01,press-01=rul-synthetic-hydraulic_press` -> bindings; the model defaults from the code prefix."""
    bindings = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        code, _, model = item.partition("=")
        if not model:
            asset_type = TYPE_BY_PREFIX.get(code.rsplit("-", 1)[0])
            if asset_type is None:
                raise ValueError(f"cannot infer the model for asset {code!r}; write it as {code}=<model name>")
            model = f"rul-synthetic-{asset_type}"
        bindings.append(AssetBinding(code=code, model_name=model))
    return bindings
