from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from twinvoice_contracts.prediction import (
    EdgePrediction,
    asset_from_pred_topic,
    pred_topic,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


def payload(**overrides: object) -> dict:
    body = {
        "id": "b3c1c5e2-0000-4000-8000-000000000001",
        "asset_code": "cnc-01",
        "time": NOW.isoformat(),
        "window_start": NOW.isoformat(),
        "window_end": NOW.isoformat(),
        "model_version": "rul-synthetic-cnc_mill:2026.09.21-1000",
        "health_index": 71.2,
        "rul": {"point": 38, "low": 29, "high": 47},
        "confidence": {"label": "medium", "reasons": []},
        "explanation": {
            "method": "tree_shap",
            "base_value": 60.0,
            "attributions": [
                {"feature": "spindle.vib_rms_mean", "value": 2.1, "contribution": -4.2, "rank": 1}
            ],
        },
        "latency_ms": {"infer_ms": 1.4, "explain_ms": 6.2},
    }
    body.update(overrides)
    return body


def test_a_full_edge_payload_round_trips_through_json() -> None:
    parsed = EdgePrediction.model_validate(payload())
    again = EdgePrediction.model_validate_json(parsed.model_dump_json())
    assert again == parsed
    assert again.source == "edge"
    assert again.rul is not None and again.rul.unit == "cycles"


def test_health_index_outside_0_100_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EdgePrediction.model_validate(payload(health_index=140))


def test_latency_is_required() -> None:
    body = payload()
    del body["latency_ms"]
    with pytest.raises(ValidationError):
        EdgePrediction.model_validate(body)


def test_topic_helpers() -> None:
    assert pred_topic("cnc-01") == "twinvoice/pred/cnc-01"
    assert asset_from_pred_topic("twinvoice/pred/cnc-01") == "cnc-01"
    assert asset_from_pred_topic("twinvoice/ack/cnc-01") is None
    assert asset_from_pred_topic("spBv1.0/plant/DDATA/line/cnc-01") is None
