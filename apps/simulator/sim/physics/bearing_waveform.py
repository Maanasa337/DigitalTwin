"""Rolling-element bearing vibration bursts with defect impulse trains (FR-SIM-07)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE_HZ = 20_000


@dataclass(frozen=True, slots=True)
class BearingGeometry:
    n_balls: int
    ball_d_mm: float
    pitch_d_mm: float
    contact_angle_deg: float

    def defect_frequencies(self, shaft_hz: float) -> dict[str, float]:
        ratio = self.ball_d_mm / self.pitch_d_mm * math.cos(math.radians(self.contact_angle_deg))
        return {
            "shaft": shaft_hz,
            "bpfo": self.n_balls / 2 * shaft_hz * (1 - ratio),
            "bpfi": self.n_balls / 2 * shaft_hz * (1 + ratio),
            "bsf": self.pitch_d_mm / (2 * self.ball_d_mm) * shaft_hz * (1 - ratio**2),
            "ftf": shaft_hz / 2 * (1 - ratio),
        }


def _impulse_train(
    n: int, fs: int, freq_hz: float, rng: np.random.Generator, slip: float = 0.01
) -> np.ndarray:
    """Unit impulses at `freq_hz` with small random period slip, as real bearings exhibit."""
    train = np.zeros(n)
    if freq_hz <= 0:
        return train
    period = 1.0 / freq_hz
    t = rng.uniform(0, period)
    duration = n / fs
    while t < duration:
        train[int(t * fs)] = 1.0
        t += period * (1 + slip * rng.normal())
    return train


def _resonance_kernel(fs: int, resonance_hz: float, decay_s: float) -> np.ndarray:
    t = np.arange(int(fs * decay_s * 6)) / fs
    return np.exp(-t / decay_s) * np.sin(2 * np.pi * resonance_hz * t)


def synthesize(
    geometry: BearingGeometry,
    shaft_hz: float,
    rng: np.random.Generator,
    *,
    outer: float = 0.0,
    inner: float = 0.0,
    ball: float = 0.0,
    unbalance: float = 0.2,
    misalignment: float = 0.05,
    noise_rms: float = 0.05,
    resonance_hz: float = 3000.0,
    decay_s: float = 0.0015,
    duration_s: float = 1.0,
    fs: int = SAMPLE_RATE_HZ,
) -> np.ndarray:
    """Acceleration signal (g). Defect severities in [0, 1] scale impulse amplitudes."""
    n = int(fs * duration_s)
    t = np.arange(n) / fs
    freqs = geometry.defect_frequencies(shaft_hz)
    kernel = _resonance_kernel(fs, resonance_hz, decay_s)
    excitation = np.zeros(n)
    if outer > 0:
        excitation += 2.0 * outer * _impulse_train(n, fs, freqs["bpfo"], rng)
    if inner > 0:
        # Inner race defect rotates through the load zone: amplitude modulated at shaft speed.
        load_zone = 0.5 * (1 + np.cos(2 * np.pi * shaft_hz * t))
        excitation += 2.0 * inner * load_zone * _impulse_train(n, fs, freqs["bpfi"], rng)
    if ball > 0:
        cage = 0.5 * (1 + np.cos(2 * np.pi * freqs["ftf"] * t))
        excitation += 1.5 * ball * cage * _impulse_train(n, fs, 2 * freqs["bsf"], rng)
    signal = np.convolve(excitation, kernel)[:n]
    signal += unbalance * np.sin(2 * np.pi * shaft_hz * t)
    signal += misalignment * np.sin(4 * np.pi * shaft_hz * t + 0.3)
    signal += noise_rms * rng.normal(size=n)
    return signal.astype(np.float32)
