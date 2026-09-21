"""Monte-Carlo what-if (FR-DT-09): the distribution, the physics response and the narration."""

import numpy as np
import pytest

from app.modules.twin import whatif
from app.modules.twin.schemas import WhatIfDistribution, WhatIfRequest
from app.modules.twin.whatif_service import narrate


def component(
    code: str = "spindle",
    damage: float = 0.5,
    life_h: float = 1000.0,
    cv: float = 0.1,
    load_exp: float = 1.0,
    model: str = "wiener",
    **extra: float,
) -> whatif.ComponentState:
    return whatif.ComponentState(
        code=code,
        name=code.title(),
        physics_model=model,
        damage=damage,
        life_h=life_h,
        cv=cv,
        load_exp=load_exp,
        speed_exp=extra.get("speed_exp", 0.0),
        activation_energy_ev=extra.get("ea_ev"),
        t_ref_c=extra.get("t_ref_c"),
    )


NOMINAL = whatif.Conditions(load=1.0, speed=1.0)


def test_first_passage_mean_matches_the_remaining_life():
    """Half-worn component with a 1000 h life should average ~500 h left at nominal load."""
    rng = np.random.default_rng(0)
    draws = whatif.time_to_failure_h(component(damage=0.5, life_h=1000.0), NOMINAL, 4000, rng)

    assert draws.mean() == pytest.approx(500.0, rel=0.05)
    assert np.all(draws > 0)


def test_higher_load_shortens_life_by_the_declared_exponent():
    """load_exp=1 means double the load, half the life — the simulator's own acceleration law."""
    rng = np.random.default_rng(1)
    comp = component(damage=0.0, life_h=1000.0, load_exp=1.0)

    nominal = whatif.time_to_failure_h(comp, NOMINAL, 4000, rng).mean()
    doubled = whatif.time_to_failure_h(comp, whatif.Conditions(load=2.0, speed=1.0), 4000, rng).mean()

    assert doubled == pytest.approx(nominal / 2, rel=0.05)


def test_a_squared_load_exponent_bites_harder():
    """A motor with load_exp=2 loses three quarters of its life at double load, not half."""
    rng = np.random.default_rng(2)
    comp = component(code="motor", damage=0.0, life_h=1000.0, load_exp=2.0)

    nominal = whatif.time_to_failure_h(comp, NOMINAL, 4000, rng).mean()
    doubled = whatif.time_to_failure_h(comp, whatif.Conditions(load=2.0, speed=1.0), 4000, rng).mean()

    assert doubled == pytest.approx(nominal / 4, rel=0.06)


def test_a_worn_out_component_has_no_life_left():
    draws = whatif.time_to_failure_h(component(damage=1.0), NOMINAL, 10, np.random.default_rng(3))
    assert np.all(draws == 0.0)


def test_a_stopped_asset_does_not_wear():
    """Zero load means zero acceleration; the answer must be 'beyond any horizon', not a crash."""
    draws = whatif.time_to_failure_h(
        component(damage=0.5), whatif.Conditions(load=0.0, speed=0.0), 10, np.random.default_rng(4)
    )
    assert np.all(np.isfinite(draws))
    assert whatif.risk_within(draws, 8760.0) == 0.0


def test_the_asset_fails_when_its_first_component_does():
    """Machine life is the min over components, and the weakest should dominate first_to_fail."""
    components = [
        component(code="spindle", damage=0.9, life_h=1000.0),  # ~100 h left
        component(code="motor", damage=0.1, life_h=1000.0),  # ~900 h left
    ]
    result = whatif.simulate(components, NOMINAL, 500, np.random.default_rng(5))

    assert result["trials"] == 500
    assert result["percentiles"]["p50"] == pytest.approx(100.0, rel=0.2)
    assert result["first_to_fail"]["spindle"] > 0.95
    assert result["percentiles"]["p10"] <= result["percentiles"]["p50"] <= result["percentiles"]["p90"]


def test_servicing_pushes_the_distribution_out():
    worn = [component(damage=0.85, life_h=1000.0)]
    fresh = [component(damage=0.0, life_h=1000.0)]
    rng = np.random.default_rng(6)

    before = whatif.simulate(worn, NOMINAL, 500, rng)["percentiles"]["p50"]
    after = whatif.simulate(fresh, NOMINAL, 500, rng)["percentiles"]["p50"]

    assert after > before * 5


def test_risk_within_horizon_is_the_share_of_failing_runs():
    samples = np.array([10.0, 20.0, 30.0, 40.0, 500.0])
    assert whatif.risk_within(samples, 35.0) == 0.6
    assert whatif.risk_within(samples, 0.0) == 0.0
    assert whatif.risk_within(np.array([]), 100.0) == 0.0


def test_ambient_temperature_accelerates_an_arrhenius_component():
    """A lube circuit run 30 C hotter than its reference should wear measurably faster."""
    comp = component(code="lube", damage=0.0, life_h=1000.0, ea_ev=0.4, t_ref_c=45.0)
    rng = np.random.default_rng(7)

    at_ref = whatif.time_to_failure_h(comp, whatif.Conditions(1.0, 1.0, ambient_c=45.0), 2000, rng).mean()
    hotter = whatif.time_to_failure_h(comp, whatif.Conditions(1.0, 1.0, ambient_c=75.0), 2000, rng).mean()

    assert hotter < at_ref


def test_energy_impact_scales_with_load_and_prices_it():
    impact = whatif.energy_impact(
        rated_power_kw=10.0,
        baseline=whatif.Conditions(load=1.0, speed=1.0),
        hypothetical=whatif.Conditions(load=0.8, speed=1.0),
        horizon_h=100.0,
        tariff_rate=8.5,
    )
    assert impact["baseline_kwh"] == 1000.0
    assert impact["hypothetical_kwh"] == 800.0
    assert impact["delta_kwh"] == -200.0
    assert impact["delta_cost"] == -1700.0


def test_energy_impact_is_silent_without_a_power_rating():
    impact = whatif.energy_impact(None, NOMINAL, NOMINAL, 100.0, 8.5)
    assert impact["delta_kwh"] is None


def test_exactness_is_reported_per_process():
    assert component(model="wiener").exact is True
    assert component(model="paris").exact is False


# ── Narration (FR-XAI-07: every number traceable to the distribution) ──


def distribution(p50: float, risk: float = 0.1, trials: int = 500) -> WhatIfDistribution:
    return WhatIfDistribution(
        trials=trials,
        mean_h=p50,
        p10_h=p50 * 0.7,
        p50_h=p50,
        p90_h=p50 * 1.4,
        risk_within_horizon=risk,
        first_to_fail={"spindle": 0.8, "motor": 0.2},
    )


def test_narration_states_the_interval_the_delta_and_the_trial_count():
    text = narrate(
        "CNC Mill 01",
        distribution(200.0, risk=0.3),
        distribution(320.0, risk=0.1),
        delta=120.0,
        energy={"delta_kwh": -150.0, "delta_cost": -1275.0},
        currency="INR",
        request=WhatIfRequest(horizon_h=168.0),
    )

    assert "CNC Mill 01" in text
    assert "200 hours" in text and "140 to 280" in text
    assert "extends" in text and "120 hours" in text
    assert "30 percent to 10 percent" in text
    assert "spindle is first to fail in 80 percent" in text
    assert "150 kWh less" in text and "1275 INR" in text
    assert "500 simulated trajectories" in text


def test_narration_says_so_when_nothing_changes():
    same = distribution(200.0)
    text = narrate("Press 01", same, same, delta=0.0, energy={}, currency=None, request=WhatIfRequest())
    assert "no material difference" in text


def test_narration_reports_a_shortened_life_as_such():
    text = narrate(
        "Press 01",
        distribution(300.0),
        distribution(150.0),
        delta=-150.0,
        energy={},
        currency=None,
        request=WhatIfRequest(),
    )
    assert "shortens" in text and "150 hours" in text
