"""Benchmark runner shared by the CLI (`benchmarks/run.py`) and the Celery task (FR-PM-09).

``run_benchmark`` returns ``{dataset: {metric: value}}`` — the exact shape `benchmark_runs.results`
stores and the "Model benchmark" report template iterates.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinvoice_pdm.datasets import dataset_sha

DATASETS = ("FD001", "FD002", "FD003", "FD004", "AI4I", "METROPT3")
# Which data/raw/<folder> (and `python data/download.py <name>`) each benchmark dataset needs.
RAW_NAME = {"FD001": "cmapss", "FD002": "cmapss", "FD003": "cmapss", "FD004": "cmapss",
            "AI4I": "ai4i", "METROPT3": "metropt3"}  # fmt: skip

# PRD §4.5 / §13 targets. `le` means the value must be at most `value`, `ge` at least.
TARGETS: dict[str, dict[str, dict[str, Any]]] = {
    "FD001": {
        "rmse": {"op": "le", "value": 13.0},
        "nasa_score": {"op": "le", "value": 300.0},
        "coverage_90": {"op": "ge", "value": 0.88},
    },
    "FD002": {"rmse": {"op": "le", "value": 17.0}},
    "FD003": {"rmse": {"op": "le", "value": 13.0}},
    "FD004": {"rmse": {"op": "le", "value": 19.0}},
    "AI4I": {"auc": {"op": "ge", "value": 0.96}},
    "METROPT3": {
        "event_recall": {"op": "ge", "value": 0.9},
        "mean_lead_time_h": {"op": "ge", "value": 2.0},
    },
}


QUICK_NOTE = "quick (subsampled smoke run — not comparable to published numbers)"


def missing_datasets(datasets: list[str], raw_dir: Path | str) -> list[str]:
    """The data/raw folders (download names) that the requested datasets need but are not there."""
    missing = []
    for name in datasets:
        raw = RAW_NAME[name]
        folder = Path(raw_dir) / raw
        present = folder.exists() and any(p for p in folder.iterdir() if p.name != ".complete")
        if not present and raw not in missing:
            missing.append(raw)
    return missing


def git_sha() -> str | None:
    """The commit being benchmarked: TV_GIT_SHA inside containers (no git there), else git itself."""
    env = os.environ.get("TV_GIT_SHA")
    if env:
        return env
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _runner(name: str) -> Callable[..., dict[str, float]]:
    if name.startswith("FD"):
        from twinvoice_pdm.benchmark import cmapss

        return lambda raw_dir, seed, quick: cmapss.run(raw_dir, name, seed=seed, quick=quick)
    if name == "AI4I":
        from twinvoice_pdm.benchmark import ai4i

        return lambda raw_dir, seed, quick: ai4i.run(raw_dir, seed=seed, quick=quick)
    if name == "METROPT3":
        from twinvoice_pdm.benchmark import metropt

        return lambda raw_dir, seed, quick: metropt.run(raw_dir, seed=seed, quick=quick)
    raise ValueError(f"unknown benchmark dataset {name!r}; known: {', '.join(DATASETS)}")


def run_benchmark(
    datasets: list[str],
    raw_dir: Path | str,
    seed: int = 42,
    quick: bool = False,
    on_progress: Callable[[str, dict[str, float]], None] | None = None,
) -> dict[str, dict[str, float]]:
    """Run each dataset's benchmark in turn; adds `seconds` (wall time) to each result."""
    unknown = [d for d in datasets if d not in DATASETS]
    if unknown:
        raise ValueError(f"unknown benchmark dataset(s) {unknown}; known: {', '.join(DATASETS)}")
    results: dict[str, dict[str, float]] = {}
    for name in datasets:
        started = time.perf_counter()
        metrics = _runner(name)(raw_dir, seed, quick)
        metrics["seconds"] = round(time.perf_counter() - started, 1)
        results[name] = metrics
        if on_progress:
            on_progress(name, metrics)
    return results


def run_meta(datasets: list[str], raw_dir: Path | str, seed: int, quick: bool) -> dict[str, Any]:
    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "git_sha": git_sha(),
        "seed": seed,
        "quick": quick,
        "datasets": list(datasets),
        "dataset_sha": {RAW_NAME[d]: dataset_sha(raw_dir, RAW_NAME[d]) for d in datasets},
    }


def check(value: float, target: dict[str, Any]) -> bool:
    return value <= target["value"] if target["op"] == "le" else value >= target["value"]


def render_markdown(
    results: dict[str, dict[str, float]],
    targets: dict[str, dict[str, dict[str, Any]]] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """The Markdown report: run metadata, then one row per metric with its target and pass/fail."""
    targets = TARGETS if targets is None else targets
    meta = meta or {}
    lines = ["# TwinVoice model benchmark", ""]
    if meta:
        lines += [
            f"- Date: {meta.get('date', '')}",
            f"- Commit: `{meta.get('git_sha') or 'unknown'}`",
            f"- Seed: {meta.get('seed')}",
            f"- Mode: {QUICK_NOTE if meta.get('quick') else 'full'}",
        ]
        for name, sha in (meta.get("dataset_sha") or {}).items():
            lines.append(f"- Dataset `{name}` sha256: `{sha or 'unknown'}`")
        lines.append("")

    lines += ["| Dataset | Metric | Value | Target | Result |", "|---|---|---:|---|---|"]
    passed = failed = 0
    for dataset, metrics in results.items():
        if dataset.startswith("_"):
            continue
        for metric, value in metrics.items():
            target = targets.get(dataset, {}).get(metric)
            if target is None:
                target_text, verdict = "", ""
            else:
                ok = check(float(value), target)
                passed, failed = passed + ok, failed + (not ok)
                target_text = f"{'≤' if target['op'] == 'le' else '≥'} {target['value']:g}"
                verdict = "pass" if ok else "**fail**"
            lines.append(f"| {dataset} | {metric} | {float(value):.4g} | {target_text} | {verdict} |")
    lines += ["", f"{passed} of {passed + failed} targeted metrics meet the PRD §4.5 target.", ""]
    lines += [
        "Protocols: C-MAPSS — RUL capped at 125, official test split scored on each engine's last",
        "window, CV+ 90 % intervals with engine-grouped folds. AI4I — stratified 5-fold, class weights,",
        "in-fold isotonic calibration, out-of-fold AUC/F1/ECE. MetroPT-3 — IsolationForest fitted on the",
        "healthy period before the first reported failure; event recall/precision over a 48 h horizon.",
        "",
    ]
    return "\n".join(lines)
