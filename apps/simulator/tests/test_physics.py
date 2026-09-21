import math
from itertools import pairwise

import numpy as np
import pytest

from sim.physics import (
    Arrhenius,
    Conditions,
    DegradationProcess,
    GammaProcess,
    MotorEfficiencyLoss,
    ParisLaw,
    TaylorToolLife,
    WienerProcess,
)

NOMINAL = Conditions(load=0.9, speed=1.0, temp_c=50.0)


def make(kind: str) -> DegradationProcess:
    match kind:
        case "gamma":
            return GammaProcess("m", life_h=10.0, cv=0.2)
        case "paris":
            return ParisLaw("m", life_h=10.0, rpm=3000.0)
        case "taylor":
            return TaylorToolLife("m", life_h=10.0, cutting_speed_m_min=200.0)
        case "motor_efficiency":
            return MotorEfficiencyLoss("m", life_h=10.0)
        case "arrhenius":
            return GammaProcess("m", life_h=10.0, arrhenius=Arrhenius(0.7, 50.0))
    raise ValueError(kind)


MONOTONE = ["gamma", "paris", "taylor", "motor_efficiency", "arrhenius"]


@pytest.mark.parametrize("kind", MONOTONE)
def test_monotone_processes_never_heal(kind: str) -> None:
    rng = np.random.default_rng(1)
    process = make(kind)
    previous = process.damage
    for dt in rng.uniform(1.0, 2000.0, size=400):
        process.step(float(dt), NOMINAL, rng)
        assert 0.0 <= process.damage <= 1.0
        assert process.damage >= previous
        previous = process.damage
    assert process.failed


@pytest.mark.parametrize("kind", MONOTONE)
def test_true_rul_decreases_under_constant_conditions(kind: str) -> None:
    rng = np.random.default_rng(2)
    process = make(kind)
    ruls = []
    for _ in range(30):
        process.step(600.0, NOMINAL, rng)
        ruls.append(process.true_rul(NOMINAL))
    assert all(b <= a for a, b in pairwise(ruls))
    assert ruls[-1] < ruls[0]


def test_wiener_rul_decreases_without_diffusion() -> None:
    process = WienerProcess("m", life_h=10.0, cv=0.0)
    rng = np.random.default_rng(0)
    ruls = []
    for _ in range(20):
        process.step(600.0, NOMINAL, rng)
        ruls.append(process.true_rul(NOMINAL))
    assert all(b < a for a, b in pairwise(ruls))


def test_wiener_mean_drift_matches_mu_t() -> None:
    rng = np.random.default_rng(3)
    life_h, t = 10.0, 4 * 3600.0
    cond = Conditions(load=1.0, speed=1.0)
    levels = []
    for _ in range(3000):
        process = WienerProcess("m", life_h=life_h, cv=0.1)
        for _ in range(4):
            process.step(t / 4, cond, rng)
        levels.append(process.level)
    mu = 1.0 / (life_h * 3600.0)
    assert np.mean(levels) == pytest.approx(mu * t, abs=0.01)
    assert np.std(levels) == pytest.approx(0.1 * math.sqrt(t / (life_h * 3600.0)), rel=0.1)


def test_wiener_is_not_monotone_but_latches_failure() -> None:
    rng = np.random.default_rng(4)
    process = WienerProcess("m", life_h=5.0, cv=0.4)
    decreases = 0
    previous = process.level
    while not process.failed:
        process.step(300.0, NOMINAL, rng)
        decreases += process.level < previous
        previous = process.level
    assert decreases > 0
    assert process.damage == 1.0
    process.step(300.0, NOMINAL, rng)
    assert process.damage == 1.0


@pytest.mark.parametrize("kind", ["paris", "taylor"])
def test_deterministic_processes_are_exact_for_large_dt(kind: str) -> None:
    rng = np.random.default_rng(0)
    one_big, many_small = make(kind), make(kind)
    one_big.step(1000.0, NOMINAL, rng)
    for _ in range(1000):
        many_small.step(1.0, NOMINAL, rng)
    assert one_big.damage == pytest.approx(many_small.damage, rel=1e-9)


def test_gamma_mean_is_step_size_invariant() -> None:
    rng = np.random.default_rng(5)
    big, small = [], []
    for _ in range(2000):
        a, b = GammaProcess("m", life_h=100.0, cv=0.3), GammaProcess("m", life_h=100.0, cv=0.3)
        a.step(20_000.0, NOMINAL, rng)
        for _ in range(20):
            b.step(1000.0, NOMINAL, rng)
        big.append(a.damage)
        small.append(b.damage)
    assert np.mean(big) == pytest.approx(np.mean(small), rel=0.03)


@pytest.mark.parametrize("kind", [*MONOTONE, "wiener"])
def test_thousand_second_steps_stay_finite_and_bounded(kind: str) -> None:
    rng = np.random.default_rng(6)
    process = WienerProcess("m", life_h=10.0) if kind == "wiener" else make(kind)
    for _ in range(100):
        process.step(1000.0, NOMINAL, rng)
        assert math.isfinite(process.damage)
        assert 0.0 <= process.damage <= 1.0
        rul = process.true_rul(NOMINAL)
        assert rul >= 0.0 and not math.isnan(rul)


@pytest.mark.parametrize("kind", [*MONOTONE, "wiener"])
def test_initial_rul_matches_calibrated_life(kind: str) -> None:
    process = WienerProcess("m", life_h=10.0) if kind == "wiener" else make(kind)
    reference = Conditions(load=1.0, speed=1.0, temp_c=50.0)
    assert process.true_rul(reference) == pytest.approx(10.0 * 3600.0, rel=1e-6)


def test_paris_crack_growth_law() -> None:
    process = ParisLaw("m", life_h=10.0, rpm=3000.0, m=3.0, a0_mm=0.1, a_crit_mm=2.0)
    rng = np.random.default_rng(0)
    a_before = process.a
    cycles = 3000.0 / 60.0  # one second of rotation: short enough to linearise da/dN
    process.step(1.0, Conditions(1.0, 1.0), rng)
    delta_k = 1.12 * 120.0 * math.sqrt(math.pi * a_before)
    expected = process.c * delta_k**3 * cycles
    assert process.a - a_before == pytest.approx(expected, rel=1e-4)
    heavier = ParisLaw("m", life_h=10.0, rpm=3000.0)
    assert heavier.true_rul(Conditions(1.0, 1.0)) / heavier.true_rul(
        Conditions(0.5, 1.0)
    ) == pytest.approx(0.5**3)


def test_taylor_tool_life_equation() -> None:
    tool = TaylorToolLife("m", life_h=2.0, cutting_speed_m_min=200.0, n=0.25)
    life = tool.tool_life_min(200.0)
    assert life == pytest.approx(120.0)
    assert 400.0 * tool.tool_life_min(400.0) ** 0.25 == pytest.approx(tool.c)
    assert tool.true_rul(Conditions(1.0, 2.0)) == pytest.approx(
        tool.tool_life_min(400.0) * 60.0, rel=1e-9
    )


def test_arrhenius_factor() -> None:
    arrhenius = Arrhenius(activation_energy_ev=0.7, t_ref_c=60.0)
    assert arrhenius.factor(60.0) == pytest.approx(1.0)
    assert arrhenius.factor(70.0) > 1.0
    assert arrhenius.factor(50.0) < 1.0
    hot = GammaProcess("m", life_h=10.0, arrhenius=arrhenius)
    assert hot.true_rul(Conditions(1.0, 1.0, 80.0)) < hot.true_rul(Conditions(1.0, 1.0, 60.0))


def test_motor_efficiency_drops_with_damage() -> None:
    motor = MotorEfficiencyLoss("m", life_h=10.0, eta0=0.92, k=0.12)
    assert motor.efficiency() == pytest.approx(0.92)
    motor.jump(0.5)
    assert motor.efficiency() == pytest.approx(0.86)


def test_rate_multiplier_and_reset() -> None:
    process = make("paris")
    base = process.true_rul(NOMINAL)
    process.rate_multiplier = 4.0
    assert process.true_rul(NOMINAL) == pytest.approx(base / 4.0)
    process.jump(0.3)
    process.reset()
    assert process.damage == 0.0
    assert process.true_rul(NOMINAL) == pytest.approx(base)
