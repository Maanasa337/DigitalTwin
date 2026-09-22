"""Benchmark runner CLI (FR-PM-09).

    python benchmarks/run.py --datasets FD001,AI4I --seed 42 [--quick] [--raw-dir data/raw] [--out benchmarks/results]

Needs `twinvoice_pdm` importable: run it from the pdm environment
(`cd packages/pdm && uv run python ../../benchmarks/run.py ...`) or inside the worker container
(`make benchmark`). Writes `<out>/<YYYY-MM-DD>.md`; when TV_DATABASE_URL is set it also records a
`benchmark_runs` row, which the "Model benchmark" report and /models/benchmarks read.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from twinvoice_pdm.benchmark import DATASETS, missing_datasets, render_markdown, run_benchmark, run_meta

REPO = Path(__file__).resolve().parents[1]


def default_raw_dir() -> Path:
    env = os.environ.get("TV_RAW_DIR")
    if env:
        return Path(env)
    return Path("/data/raw") if Path("/data/raw").exists() else REPO / "data" / "raw"


def record_run(database_url: str, run_id: uuid.UUID, started: datetime, meta: dict, results: dict, report: Path) -> None:
    """Insert the finished run with plain SQL, so the CLI does not need the API's ORM."""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO benchmark_runs (id, started_at, finished_at, git_sha, seed, datasets, results, "
                "report_uri, status) VALUES (:id, :started, :finished, :sha, :seed, :datasets, "
                "CAST(:results AS jsonb), :report, 'done')"
            ),
            {
                "id": run_id,
                "started": started,
                "finished": datetime.now(UTC),
                "sha": meta.get("git_sha"),
                "seed": meta["seed"],
                "datasets": meta["datasets"],
                "results": json.dumps(results),
                "report": f"file://{report.resolve().as_posix()}",
            },
        )
    engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", default="FD001,AI4I", help=f"comma-separated subset of {','.join(DATASETS)}")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quick", action="store_true", help="subsampled smoke run (seconds, not comparable)")
    parser.add_argument("--raw-dir", type=Path, default=default_raw_dir())
    parser.add_argument("--out", type=Path, default=REPO / "benchmarks" / "results")
    args = parser.parse_args(argv)

    datasets = [d.strip().upper() for d in args.datasets.split(",") if d.strip()]
    unknown = [d for d in datasets if d not in DATASETS]
    if unknown:
        parser.error(f"unknown dataset(s) {unknown}; choose from {', '.join(DATASETS)}")
    missing = missing_datasets(datasets, args.raw_dir)
    if missing:
        print(f"missing raw data in {args.raw_dir}: run `python data/download.py {' '.join(missing)}`", file=sys.stderr)
        return 2

    started = datetime.now(UTC)
    meta = run_meta(datasets, args.raw_dir, args.seed, args.quick)
    results = run_benchmark(
        datasets,
        args.raw_dir,
        seed=args.seed,
        quick=args.quick,
        on_progress=lambda name, metrics: print(f"[{name}] " + ", ".join(f"{k}={v:.4g}" for k, v in metrics.items())),
    )

    args.out.mkdir(parents=True, exist_ok=True)
    report = args.out / f"{started:%Y-%m-%d}{'-quick' if args.quick else ''}.md"
    report.write_text(render_markdown(results, meta=meta), encoding="utf-8")
    print(f"report written to {report}")

    database_url = os.environ.get("TV_DATABASE_URL")
    if database_url:
        try:
            record_run(database_url, uuid.uuid4(), started, meta, results, report)
            print("benchmark_runs row recorded")
        except Exception as exc:  # the report on disk is the primary output; a DB hiccup must not lose it
            print(f"could not record benchmark_runs row: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
