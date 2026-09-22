"""Which failure mode an explanation points at, for models that predict remaining life but no mode.

The RUL models say how long, not what. The failure-mode catalog records, per asset type, the metrics
that make up each mode's signature, so the mode whose signature carries the largest share of the
top attributions is the one the evidence supports. A healthy prediction is "normal" regardless:
naming a failure mode for a machine inside its learned envelope would send a technician for nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session
from twinvoice_xai.attribution import Attribution

from app.modules.assets.models import Asset, FailureMode

HEALTHY_INDEX = 70.0
TOP_K = 5


def _supports(feature: str, metrics: Sequence[str]) -> bool:
    return any(feature == metric or feature.startswith(f"{metric}_") for metric in metrics)


def signature_mode(
    session: Session, asset_id: uuid.UUID, attributions: Sequence[Attribution], health_index: float | None
) -> str:
    if health_index is not None and float(health_index) >= HEALTHY_INDEX:
        return "normal"
    asset_type = session.scalar(select(Asset.asset_type).where(Asset.id == asset_id))
    if asset_type is None:
        return "normal"
    best, best_share = "normal", 0.0
    for mode in session.scalars(select(FailureMode).where(FailureMode.asset_type == asset_type)):
        metrics = (mode.signature or {}).get("metrics") or []
        share = sum(a.share for a in attributions[:TOP_K] if _supports(a.feature, metrics))
        if share > best_share:
            best, best_share = mode.code, share
    return best
