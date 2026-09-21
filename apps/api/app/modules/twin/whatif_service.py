"""Assembles a what-if run: twin clone in, distribution and narration out (FR-DT-09)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.errors import UnprocessableError
from app.modules.analytics.repository import TariffRepository
from app.modules.assets.models import Asset
from app.modules.assets.repository import ComponentRepository, LineRepository, PlantRepository
from app.modules.simulation.client import SimulatorClient
from app.modules.twin import whatif
from app.modules.twin.schemas import (
    WhatIfConditions,
    WhatIfDistribution,
    WhatIfEnergy,
    WhatIfRequest,
    WhatIfResult,
)

# The run is reproducible: the same twin state and the same question give the same distribution.
SEED = 42


class WhatIfService:
    def __init__(self, session: Session, simulator: SimulatorClient) -> None:
        self.session = session
        self.simulator = simulator
        self.components = ComponentRepository(session)
        self.lines = LineRepository(session)
        self.plants = PlantRepository(session)

    def run(self, asset: Asset, request: WhatIfRequest) -> WhatIfResult:
        started = time.perf_counter()
        live = self._live_state(asset.code)

        components = self._clone(asset, live.get("damage", {}))
        if not components:
            raise UnprocessableError(
                f"{asset.name} has no component with a degradation model, so there is nothing to project."
            )

        baseline_cond = whatif.Conditions(
            load=float(live.get("load_pct", 100.0)) / 100.0,
            speed=float(live.get("speed_pct", 100.0)) / 100.0,
            ambient_c=request.ambient_c if request.ambient_c is not None else None,
        )
        hypothetical_cond = self._hypothetical(baseline_cond, request)

        rng = np.random.default_rng(SEED)
        baseline = whatif.simulate(components, baseline_cond, request.trials, rng)
        # A fresh generator, so the two arms are independent draws rather than the same shocks.
        hypothetical = whatif.simulate(
            self._after_maintenance(components, request),
            hypothetical_cond,
            request.trials,
            np.random.default_rng(SEED + 1),
        )

        tariff, currency = self._tariff(asset)
        energy = whatif.energy_impact(
            float(asset.rated_power_kw) if asset.rated_power_kw else None,
            baseline_cond,
            hypothetical_cond,
            request.horizon_h,
            tariff,
        )

        base_dist = self._distribution(baseline, request.horizon_h)
        hyp_dist = self._distribution(hypothetical, request.horizon_h)
        delta = (
            round(hyp_dist.p50_h - base_dist.p50_h, 2)
            if hyp_dist.p50_h is not None and base_dist.p50_h is not None
            else None
        )

        return WhatIfResult(
            asset_code=asset.code,
            asset_name=asset.name,
            horizon_h=request.horizon_h,
            baseline_conditions=_conditions_out(baseline_cond),
            hypothetical_conditions=_conditions_out(hypothetical_cond),
            baseline=base_dist,
            hypothetical=hyp_dist,
            delta_p50_h=delta,
            energy=WhatIfEnergy(**energy, currency=currency),
            components_modelled=len(components),
            exact_processes=sum(1 for c in components if c.exact),
            narrative=narrate(asset.name, base_dist, hyp_dist, delta, energy, currency, request),
            computed_ms=int((time.perf_counter() - started) * 1000),
        )

    def _live_state(self, code: str) -> dict[str, Any]:
        status = self.simulator.request("GET", "/status")
        for item in status.get("assets", []):
            if item.get("code") == code:
                return item
        raise UnprocessableError(f"The simulator is not carrying state for {code}.")

    def _clone(self, asset: Asset, damage: dict[str, Any]) -> list[whatif.ComponentState]:
        rows = self.components.for_assets([asset.id])
        states = [
            whatif.component_state(component, damage.get(component.code, 0.0))
            for component in rows
            if (component.physics_params or {}).get("life_h")
        ]
        return states

    @staticmethod
    def _hypothetical(baseline: whatif.Conditions, request: WhatIfRequest) -> whatif.Conditions:
        return whatif.Conditions(
            load=request.load_pct / 100.0 if request.load_pct is not None else baseline.load,
            speed=request.speed_pct / 100.0 if request.speed_pct is not None else baseline.speed,
            ambient_c=request.ambient_c if request.ambient_c is not None else baseline.ambient_c,
        )

    @staticmethod
    def _after_maintenance(
        components: list[whatif.ComponentState], request: WhatIfRequest
    ) -> list[whatif.ComponentState]:
        """Servicing resets the worn components, so the hypothetical starts from clean damage."""
        if request.maintenance_in_h is None:
            return components
        from dataclasses import replace

        return [replace(c, damage=0.0) for c in components]

    def _tariff(self, asset: Asset) -> tuple[float | None, str | None]:
        line = self.lines.get(asset.line_id)
        plant = self.plants.get(line.plant_id) if line else None
        if plant is None:
            return None, None
        tariffs = TariffRepository(self.session).all_active(plant.id)
        rate = TariffRepository.rate_at(tariffs, datetime.now(UTC)) if tariffs else None
        return rate or None, plant.currency

    @staticmethod
    def _distribution(result: dict[str, Any], horizon_h: float) -> WhatIfDistribution:
        pct = result.get("percentiles", {})
        samples = result.get("_samples", np.array([]))
        return WhatIfDistribution(
            trials=result.get("trials", 0),
            mean_h=result.get("mean"),
            p10_h=pct.get("p10"),
            p50_h=pct.get("p50"),
            p90_h=pct.get("p90"),
            risk_within_horizon=whatif.risk_within(samples, horizon_h),
            first_to_fail=result.get("first_to_fail", {}),
        )


def _conditions_out(cond: whatif.Conditions) -> WhatIfConditions:
    return WhatIfConditions(
        load_pct=round(cond.load * 100, 1),
        speed_pct=round(cond.speed * 100, 1),
        ambient_c=cond.ambient_c,
    )


def narrate(
    asset_name: str,
    baseline: WhatIfDistribution,
    hypothetical: WhatIfDistribution,
    delta: float | None,
    energy: dict[str, Any],
    currency: str | None,
    request: WhatIfRequest,
) -> str:
    """Deterministic summary. Every number here comes from the distribution above it (FR-XAI-07)."""
    if baseline.p50_h is None or hypothetical.p50_h is None:
        return f"I could not project a life for {asset_name}."

    parts = [
        f"{asset_name} has a median remaining life of {baseline.p50_h:.0f} hours "
        f"({baseline.p10_h:.0f} to {baseline.p90_h:.0f}) as it runs now."
    ]
    if delta is None or abs(delta) < 1:
        parts.append("The change makes no material difference to that.")
    else:
        direction = "extends" if delta > 0 else "shortens"
        parts.append(
            f"The change {direction} it by about {abs(delta):.0f} hours, to {hypothetical.p50_h:.0f} hours "
            f"({hypothetical.p10_h:.0f} to {hypothetical.p90_h:.0f})."
        )

    before = baseline.risk_within_horizon
    after = hypothetical.risk_within_horizon
    parts.append(
        f"Risk of failing within {request.horizon_h:.0f} hours moves from {before * 100:.0f} percent "
        f"to {after * 100:.0f} percent."
    )
    if baseline.first_to_fail:
        leader = next(iter(baseline.first_to_fail))
        share = baseline.first_to_fail[leader]
        parts.append(f"The {leader} is first to fail in {share * 100:.0f} percent of runs.")

    delta_kwh = energy.get("delta_kwh")
    if delta_kwh:
        cost = energy.get("delta_cost")
        money = f", about {abs(cost):.0f} {currency}" if cost and currency else ""
        verb = "more" if delta_kwh > 0 else "less"
        parts.append(f"It would use {abs(delta_kwh):.0f} kWh {verb} over the horizon{money}.")
    parts.append(f"Based on {baseline.trials} simulated trajectories.")
    return " ".join(parts)
