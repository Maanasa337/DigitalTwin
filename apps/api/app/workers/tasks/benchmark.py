"""Celery task: run a benchmark (FR-PM-09) for a `benchmark_runs` row created by `POST /benchmarks/run`.

The work itself is `twinvoice_pdm.benchmark.run_benchmark` — the same code `benchmarks/run.py` runs
from a terminal — so a number in the UI and a number in `benchmarks/results/*.md` mean the same thing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.benchmark.run_benchmark_task", ignore_result=True, acks_late=False)
def run_benchmark_task(run_id: str, quick: bool = False) -> str:
    """Fill in results and the Markdown report; marks the row failed (with the message) on error.

    Not acks_late: a benchmark takes minutes, and a worker restart re-delivering it would run it twice.
    """
    from twinvoice_pdm.benchmark import render_markdown, run_benchmark, run_meta

    from app.core.config import get_settings
    from app.core.db import get_sessionmaker
    from app.modules.pdm.models import BenchmarkRun

    settings = get_settings()
    with get_sessionmaker()() as session:
        run = session.get(BenchmarkRun, uuid.UUID(run_id))
        if run is None:
            log.warning("benchmark run %s vanished before it started", run_id)
            return "missing"
        datasets, seed = list(run.datasets), run.seed

    try:
        meta = run_meta(datasets, settings.raw_data_dir, seed, quick)
        results = run_benchmark(
            datasets,
            settings.raw_data_dir,
            seed=seed,
            quick=quick,
            on_progress=lambda name, metrics: log.info("benchmark %s: %s done %s", run_id, name, metrics),
        )
        report_dir = Path(settings.benchmarks_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / f"{run_id}.md"
        report.write_text(render_markdown(results, meta=meta), encoding="utf-8")
    except Exception as exc:
        log.exception("benchmark run %s failed", run_id)
        _finish(run_id, status="failed", results={"_error": {"message": str(exc)[:500]}}, git_sha=None, report=None)
        return "failed"

    _finish(run_id, status="done", results=results, git_sha=meta.get("git_sha"), report=report)
    return "done"


def _finish(run_id: str, *, status: str, results: dict, git_sha: str | None, report: Path | None) -> None:
    from app.core.db import get_sessionmaker
    from app.modules.pdm.models import BenchmarkRun

    with get_sessionmaker()() as session:
        run = session.get(BenchmarkRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = status
        run.results = results
        run.finished_at = datetime.now(UTC)
        run.git_sha = git_sha
        run.report_uri = f"file://{report.resolve().as_posix()}" if report else None
        session.commit()
