"""Headless synthetic dataset export with ground truth (FR-SIM-09).

python -m sim.export [--scenario CODE] --hours H [--period S] [--seed N] [--out DIR]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from sim.catalog import Catalog
from sim.config import Settings
from sim.engine import SIM_EPOCH, Engine
from sim.machines import Machine

MAX_HOURS = 168.0
FLUSH_ROWS = 50_000
INT_METRICS = {"good_count", "reject_count"}


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    rows: int
    columns: list[str]


def _schema(engine: Engine) -> pa.Schema:
    metrics: dict[str, None] = {}
    components: dict[str, None] = {}
    for machine in engine.machines.values():
        metrics.update(
            (d.name, None) for d in machine.sensor_array.metric_defs if d.name != "state"
        )
        components.update((code, None) for code in machine.components)
    fields = [
        pa.field("time", pa.timestamp("ms", tz="UTC")),
        pa.field("asset_code", pa.string()),
        pa.field("asset_type", pa.string()),
        pa.field("state", pa.string()),
        *(pa.field(m, pa.int64() if m in INT_METRICS else pa.float64()) for m in metrics),
        pa.field("damage", pa.float64()),
        *(pa.field(f"damage.{c}", pa.float64()) for c in components),
        pa.field("true_rul_h", pa.float64()),
        pa.field("driver", pa.string()),
        pa.field("failure_mode", pa.string()),
    ]
    return pa.schema(fields)


class _Recorder:
    def __init__(self, engine: Engine, schema: pa.Schema, writer: pq.ParquetWriter) -> None:
        self.engine = engine
        self.schema = schema
        self.writer = writer
        self.names = schema.names
        self.buffers: dict[str, list[Any]] = {name: [] for name in self.names}
        self.rows = 0
        self.epoch_ms = int(engine.start.timestamp() * 1000)

    def __call__(self, machine: Machine) -> None:
        truth = machine.ground_truth()
        row: dict[str, Any] = machine.metric_values()
        row |= {f"damage.{code}": value for code, value in truth.damage.items()}
        row |= {
            "time": self.epoch_ms + round(self.engine.now_s * 1000),
            "asset_code": machine.code,
            "asset_type": machine.asset_type,
            "damage": max(truth.damage.values(), default=0.0),
            "true_rul_h": None if truth.true_rul_s is None else truth.true_rul_s / 3600.0,
            "driver": truth.driver,
            "failure_mode": truth.failure_mode,
        }
        for name in self.names:
            self.buffers[name].append(row.get(name))
        self.rows += 1
        if len(self.buffers["time"]) >= FLUSH_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.buffers["time"]:
            return
        self.writer.write_table(pa.table(self.buffers, schema=self.schema))
        self.buffers = {name: [] for name in self.names}


def export_run(
    catalog: Catalog,
    *,
    hours: float,
    out_dir: Path,
    period_s: float = 10.0,
    scenario_code: str | None = None,
    seed: int | None = None,
) -> ExportResult:
    if not 0 < hours <= MAX_HOURS:
        raise ValueError(f"hours must be within (0, {MAX_HOURS:g}]")
    if period_s <= 0:
        raise ValueError("period must be positive")
    scenario = catalog.scenarios[scenario_code] if scenario_code is not None else None
    if seed is None:
        seed = scenario.seed if scenario is not None else Settings.seed
    engine = Engine(catalog, seed, tick_s=period_s, start=SIM_EPOCH, scenario=scenario)
    schema = _schema(engine)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"{scenario_code or 'baseline'}_seed{seed}_{stamp}.parquet"
    with pq.ParquetWriter(path, schema) as writer:
        recorder = _Recorder(engine, schema, writer)
        engine.on_tick = recorder
        engine.env.run(until=hours * 3600.0 + period_s / 2)
        recorder.flush()
    return ExportResult(path, recorder.rows, schema.names)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sim.export", description=__doc__)
    parser.add_argument("--scenario", default=None, help="scenario code (default: baseline fleet)")
    parser.add_argument("--hours", type=float, required=True)
    parser.add_argument("--period", type=float, default=10.0, help="sample period in sim seconds")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Settings.from_env().export_dir)
    args = parser.parse_args(argv)
    catalog = Catalog.load()
    if args.scenario is not None and args.scenario not in catalog.scenarios:
        parser.error(f"unknown scenario {args.scenario}; known: {', '.join(catalog.scenarios)}")
    result = export_run(
        catalog,
        hours=args.hours,
        out_dir=args.out,
        period_s=args.period,
        scenario_code=args.scenario,
        seed=args.seed,
    )
    print(f"wrote {result.rows} rows x {len(result.columns)} columns to {result.path}")


if __name__ == "__main__":
    main()
