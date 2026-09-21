import base64

import numpy as np
import pytest

from sim.catalog import Catalog
from sim.engine import Engine
from sim.physics.bearing_waveform import SAMPLE_RATE_HZ, BearingGeometry, synthesize
from sim.publisher import waveform_message

GEOMETRY = BearingGeometry(n_balls=9, ball_d_mm=7.94, pitch_d_mm=39.04, contact_angle_deg=15.0)
SHAFT_HZ = 8000 / 60


def envelope_spectrum(
    signal: np.ndarray, band: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray]:
    """Band-pass around the structural resonance, demodulate, and return the envelope spectrum."""
    n = signal.size
    spectrum = np.fft.fft(signal)
    freqs = np.fft.fftfreq(n, 1 / SAMPLE_RATE_HZ)
    analytic = np.where((freqs >= band[0]) & (freqs <= band[1]), 2 * spectrum, 0)
    envelope = np.abs(np.fft.ifft(analytic))
    env_spectrum = np.abs(np.fft.rfft(envelope - envelope.mean()))
    return np.fft.rfftfreq(n, 1 / SAMPLE_RATE_HZ), env_spectrum


def dominant_frequency(freqs: np.ndarray, spectrum: np.ndarray, low: float, high: float) -> float:
    mask = (freqs >= low) & (freqs <= high)
    return float(freqs[mask][np.argmax(spectrum[mask])])


def test_defect_frequencies_from_geometry() -> None:
    f = GEOMETRY.defect_frequencies(SHAFT_HZ)
    ratio = 7.94 / 39.04 * np.cos(np.radians(15.0))
    assert f["bpfo"] == pytest.approx(4.5 * SHAFT_HZ * (1 - ratio))
    assert f["bpfi"] == pytest.approx(4.5 * SHAFT_HZ * (1 + ratio))
    assert f["bpfo"] + f["bpfi"] == pytest.approx(9 * SHAFT_HZ)


def test_outer_race_defect_peaks_at_bpfo() -> None:
    rng = np.random.default_rng(0)
    signal = synthesize(GEOMETRY, SHAFT_HZ, rng, outer=0.8)
    assert signal.dtype == np.float32 and signal.size == SAMPLE_RATE_HZ
    freqs, spectrum = envelope_spectrum(signal, (2000.0, 4500.0))
    bpfo = GEOMETRY.defect_frequencies(SHAFT_HZ)["bpfo"]
    assert dominant_frequency(freqs, spectrum, 20.0, 1000.0) == pytest.approx(bpfo, rel=0.02)


def test_inner_race_defect_peaks_at_bpfi() -> None:
    rng = np.random.default_rng(1)
    signal = synthesize(GEOMETRY, SHAFT_HZ, rng, inner=0.8)
    freqs, spectrum = envelope_spectrum(signal, (2000.0, 4500.0))
    bpfi = GEOMETRY.defect_frequencies(SHAFT_HZ)["bpfi"]
    assert dominant_frequency(freqs, spectrum, 400.0, 1000.0) == pytest.approx(bpfi, rel=0.02)


def test_impulse_energy_scales_with_damage() -> None:
    healthy = synthesize(GEOMETRY, SHAFT_HZ, np.random.default_rng(2), outer=0.0)
    worn = synthesize(GEOMETRY, SHAFT_HZ, np.random.default_rng(2), outer=0.9)
    assert np.std(worn) > 2 * np.std(healthy)


def test_waveform_message_for_running_bearing_components(catalog: Catalog) -> None:
    engine = Engine(catalog, seed=1, tick_s=60.0)
    engine.advance(600.0)
    rng = np.random.default_rng(0)
    waves = {
        (code, w.component_code): w
        for code, machine in engine.machines.items()
        for w in machine.waveforms(rng)
    }
    assert set(waves) == {
        ("cnc-01", "spindle"), ("cnc-02", "spindle"), ("compressor-01", "bearing"),
        ("compressor-02", "bearing"), ("conveyor-01", "bearing"), ("conveyor-02", "bearing"),
        ("conveyor-03", "bearing"),
    }  # fmt: skip
    message = waveform_message("cnc-01", waves[("cnc-01", "spindle")])
    assert message["metric_name"] == "spindle.vib_wave"
    assert message["sample_rate_hz"] == 20000
    samples = np.frombuffer(base64.b64decode(message["samples_b64"]), dtype="<f4")
    assert samples.size == message["n_samples"] == 20000
    assert set(message["defect_freqs_hz"]) == {"shaft", "bpfo", "bpfi", "bsf"}
    assert message["t"].endswith("Z")
