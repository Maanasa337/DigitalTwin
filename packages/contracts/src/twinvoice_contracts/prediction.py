"""Edge prediction message on ``twinvoice/pred/{asset_code}`` (ARCHITECTURE §5.4, §6.4).

The edge runner builds one of these per stride and the platform's ingest consumer validates it, so
both sides share a single schema instead of two dicts that drift apart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PRED_TOPIC_PREFIX = "twinvoice/pred"
PRED_TOPIC_FILTER = f"{PRED_TOPIC_PREFIX}/+"


def pred_topic(asset_code: str) -> str:
    return f"{PRED_TOPIC_PREFIX}/{asset_code}"


def asset_from_pred_topic(topic: str) -> str | None:
    """The asset code of a ``twinvoice/pred/{asset}`` topic, or None for any other topic."""
    parts = topic.split("/")
    if len(parts) == 3 and f"{parts[0]}/{parts[1]}" == PRED_TOPIC_PREFIX and parts[2]:
        return parts[2]
    return None


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RulInterval(_Model):
    point: float
    low: float
    high: float
    unit: str = "cycles"
    coverage: float | None = 0.9


class Confidence(_Model):
    label: Literal["high", "medium", "low"] | None = None
    reasons: list[str] = Field(default_factory=list)


class Drift(_Model):
    flag: bool = False
    score: float | None = None


class EdgeAttribution(_Model):
    feature: str
    label: str = ""
    value: float
    unit: str = ""
    contribution: float
    direction: str = ""
    share: float = 0.0
    rank: int


class EdgeExplanation(_Model):
    method: str = "tree_shap"
    base_value: float = 0.0
    attributions: list[EdgeAttribution] = Field(default_factory=list)


class EdgeLatency(_Model):
    infer_ms: float
    explain_ms: float | None = None


class EdgePrediction(_Model):
    """§6.4 `Prediction`, plus what only the edge knows: its own explanation and timings."""

    id: str
    asset_code: str
    component_code: str | None = None
    time: datetime
    window_start: datetime
    window_end: datetime
    model_version: str = Field(
        description="`{name}:{version}` of the bundle, resolved to a models row on ingest"
    )
    health_index: float | None = Field(None, ge=0, le=100)
    anomaly_score: float | None = None
    failure_probability: dict[str, float] | None = None
    rul: RulInterval | None = None
    confidence: Confidence = Field(default_factory=Confidence)
    drift: Drift = Field(default_factory=Drift)
    explanation: EdgeExplanation | None = None
    latency_ms: EdgeLatency
    source: Literal["edge"] = "edge"
