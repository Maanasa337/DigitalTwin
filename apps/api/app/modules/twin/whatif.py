"""Ask the twin: Monte-Carlo what-if over the twin's own degradation state (FR-DT-09).

The twin clone is the component damage vector the simulator is actually carrying, plus each
component's declared physics parameters. From there every component is advanced as a Wiener
first-passage problem — the same process `sim/physics/wiener.py` integrates — and the asset fails
when its first component does.

The first passage of a Wiener process with drift to a barrier is inverse-Gaussian, so a trajectory
does not have to be stepped: one `rng.wald` draw per component per trial is the exact answer. That
is what keeps 500 trajectories across a whole machine inside the 10-second budget the PRD sets.

Components whose declared process is not Wiener (Paris crack growth, Taylor tool life, Arrhenius,
motor efficiency) are advanced through the same first-passage surrogate, calibrated to their own
`life_h`, spread and load exponent. The surrogate reproduces their mean life and load sensitivity;
it does not reproduce the shape of their tails, and the response says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

HOUR_S = 3600.0
DEFAULT_TRIALS = 500
MAX_TRIALS = 5000
# Damage is a fraction of life in [0, 1]; a component this close to the barrier has effectively gone.
MIN_REMAINING = 1e-4
# Spread of the first-passage time when a process declares no `cv` of its own.
DEFAULT_CV = 0.15
# Arrhenius constants, matching sim/physics/arrhenius.py so both sides agree on a temperature factor.
BOLTZMANN_EV_PER_K = 8.617333262e-5
KELVIN = 273.15
PERCENTILES = (10, 50, 90)


@dataclass(frozen=True)
class Conditions:
    """The operating point a trajectory is run at. Load and speed are fractions of nominal."""

    load: float
    speed: float
    ambient_c: float | None = None


@dataclass(frozen=True)
class ComponentState:
    """One component's clone: where its damage stands and how fast it accrues."""

    code: str
    name: str
    physics_model: str
    damage: float
    life_h: float
    cv: float
    load_exp: float
    speed_exp: float
    activation_energy_ev: float | None
    t_ref_c: float | None

    @property
    def exact(self) -> bool:
        """True when the first-passage draw is the component's own process, not a surrogate."""
        return self.physics_model == "wiener"

    def acceleration(self, cond: Conditions) -> float:
        """Rate multiplier at an operating point: reference time advances this much faster."""
        factor = max(cond.load, 0.0) ** self.load_exp * max(cond.speed, 0.0) ** self.speed_exp
        if self.activation_energy_ev is not None and self.t_ref_c is not None and cond.ambient_c is not None:
            t_k = max(cond.ambient_c + KELVIN, 1.0)
            inv_diff = 1 / (self.t_ref_c + KELVIN) - 1 / t_k
            factor *= math.exp(min(self.activation_energy_ev / BOLTZMANN_EV_PER_K * inv_diff, 50.0))
        return factor


def component_state(component: Any, damage: float) -> ComponentState:
    """Build a clone entry from a Component row and the damage the simulator reports for it."""
    params = component.physics_params or {}
    return ComponentState(
        code=component.code,
        name=component.name,
        physics_model=component.physics_model or "wiener",
        damage=min(max(float(damage), 0.0), 1.0),
        life_h=float(params.get("life_h") or 0.0),
        cv=float(params.get("cv") or DEFAULT_CV),
        load_exp=float(params.get("load_exp") or 1.0),
        speed_exp=float(params.get("speed_exp") or 0.0),
        activation_energy_ev=_optional_float(params.get("ea_ev")),
        t_ref_c=_optional_float(params.get("t_ref_c")),
    )


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def time_to_failure_h(component: ComponentState, cond: Conditions, trials: int, rng: np.random.Generator) -> np.ndarray:
    """`trials` draws of this component's remaining life in wall-clock hours at `cond`.

    In reference time the process is X(t) = t/life + (cv/sqrt(life)) W(t) and failure is X = 1, so
    the remaining barrier is (1 - damage) and the first passage is inverse-Gaussian with
    mean = barrier * life and shape = (barrier / cv)^2 * life. Wall time divides by the
    acceleration the operating point applies.
    """
    remaining = 1.0 - component.damage
    if component.life_h <= 0 or remaining <= MIN_REMAINING:
        return np.zeros(trials)

    life_s = component.life_h * HOUR_S
    mean_ref_s = remaining * life_s
    # shape = barrier^2 / diffusion^2 with diffusion = cv / sqrt(life_s)
    shape_ref_s = (remaining**2) * life_s / max(component.cv, 1e-6) ** 2
    reference_s = rng.wald(mean_ref_s, shape_ref_s, size=trials)

    acceleration = component.acceleration(cond)
    if acceleration <= 0:
        # Stopped: nothing wears. Report a life longer than any horizon rather than infinity.
        return np.full(trials, float(mean_ref_s / HOUR_S) * 1e3)
    return reference_s / acceleration / HOUR_S


def simulate(
    components: list[ComponentState],
    cond: Conditions,
    trials: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Run `trials` trajectories; the asset's life is the first component's to end."""
    if not components:
        return {"trials": 0, "percentiles": {}, "mean": None, "first_to_fail": {}}

    per_component = np.vstack([time_to_failure_h(c, cond, trials, rng) for c in components])
    asset_life = per_component.min(axis=0)
    first_index = per_component.argmin(axis=0)

    counts = np.bincount(first_index, minlength=len(components))
    first_to_fail = {components[i].code: round(float(counts[i]) / trials, 4) for i in np.argsort(-counts) if counts[i]}
    return {
        "trials": trials,
        "percentiles": {f"p{p}": round(float(np.percentile(asset_life, p)), 2) for p in PERCENTILES},
        "mean": round(float(asset_life.mean()), 2),
        "first_to_fail": first_to_fail,
        "_samples": asset_life,
    }


def risk_within(samples: np.ndarray, horizon_h: float) -> float:
    """Share of trajectories that fail inside the horizon — the Monte-Carlo answer to 'will it hold?'."""
    if samples.size == 0 or horizon_h <= 0:
        return 0.0
    return round(float((samples <= horizon_h).mean()), 4)


def energy_impact(
    rated_power_kw: float | None,
    baseline: Conditions,
    hypothetical: Conditions,
    horizon_h: float,
    tariff_rate: float | None,
) -> dict[str, Any]:
    """Energy and cost difference over the horizon. Shaft power tracks load, so energy does too."""
    if not rated_power_kw or horizon_h <= 0:
        return {"baseline_kwh": None, "hypothetical_kwh": None, "delta_kwh": None, "delta_cost": None}
    base_kwh = rated_power_kw * max(baseline.load, 0.0) * horizon_h
    hyp_kwh = rated_power_kw * max(hypothetical.load, 0.0) * horizon_h
    delta = hyp_kwh - base_kwh
    return {
        "baseline_kwh": round(base_kwh, 2),
        "hypothetical_kwh": round(hyp_kwh, 2),
        "delta_kwh": round(delta, 2),
        "delta_cost": round(delta * tariff_rate, 2) if tariff_rate else None,
    }
