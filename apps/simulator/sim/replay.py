"""Replay public PdM datasets as live Sparkplug B telemetry (FR-SIM-08).

python -m sim.replay --dataset cmapss|ai4i|metropt3 --file PATH [--units 1,2] --rate ROWS_PER_SEC
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from sim.catalog import Catalog
from sim.config import Settings
from sim.publisher import SparkplugEdgeNode
from sim.sensors import MetricDef

log = logging.getLogger(__name__)

EDGE_NODE = "replay"
CONNECT_WAIT_S = 10.0

CMAPSS_METRICS = [f"engine.op{i}" for i in range(1, 4)] + [f"engine.s{i:02d}" for i in range(1, 22)]
AI4I_COLUMNS = {
    "Air temperature [K]": ("mill.air_temp_k", "K"),
    "Process temperature [K]": ("mill.process_temp_k", "K"),
    "Rotational speed [rpm]": ("mill.rpm", "rpm"),
    "Torque [Nm]": ("mill.torque_nm", "Nm"),
    "Tool wear [min]": ("mill.tool_wear_min", "min"),
}
METROPT_SKIP = {"", "timestamp"}


@dataclass(frozen=True, slots=True)
class ReplayRow:
    asset_code: str
    values: dict[str, float]


def snake_case(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def read_cmapss(path: Path, units: set[int] | None = None) -> Iterator[ReplayRow]:
    """NASA C-MAPSS train_FD00x.txt: unit, cycle, 3 operational settings, 21 sensors."""
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 26:
                raise ValueError(f"{path}:{line_no}: expected 26 columns, got {len(fields)}")
            unit = int(fields[0])
            if units is None or unit in units:
                values = dict(zip(CMAPSS_METRICS, map(float, fields[2:]), strict=True))
                yield ReplayRow(f"engine-{unit:03d}", values)


def read_ai4i(path: Path, units: set[int] | None = None) -> Iterator[ReplayRow]:
    """UCI AI4I 2020 predictive maintenance CSV."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield ReplayRow(
                "ai4i-mill", {m: float(row[col]) for col, (m, _) in AI4I_COLUMNS.items()}
            )


def read_metropt3(path: Path, units: set[int] | None = None) -> Iterator[ReplayRow]:
    """UCI MetroPT-3 air production unit CSV: index, timestamp, analogue and digital signals."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        columns = [
            (i, f"apu.{snake_case(c)}")
            for i, c in enumerate(header)
            if c.strip() not in METROPT_SKIP
        ]
        for row in reader:
            if row:
                yield ReplayRow("metro-apu", {metric: float(row[i]) for i, metric in columns})


READERS: dict[str, Callable[[Path, set[int] | None], Iterator[ReplayRow]]] = {
    "cmapss": read_cmapss,
    "ai4i": read_ai4i,
    "metropt3": read_metropt3,
}


def metric_defs(dataset: str, row: ReplayRow) -> list[MetricDef]:
    units = {metric: unit for metric, unit in AI4I_COLUMNS.values()} if dataset == "ai4i" else {}
    return [MetricDef(name, "Double", units.get(name, "")) for name in row.values]


def replay(
    dataset: str,
    path: Path,
    rate: float,
    node: SparkplugEdgeNode,
    units: set[int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    interval = 1.0 / rate
    deadline = time.monotonic()
    sent = 0
    for row in READERS[dataset](path, units):
        if row.asset_code not in node.devices:
            node.add_device(row.asset_code, metric_defs(dataset, row))
        node.publish_device(row.asset_code, dict(row.values), {})
        sent += 1
        deadline += interval
        sleep(max(deadline - time.monotonic(), 0.0))
    return sent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sim.replay", description=__doc__)
    parser.add_argument("--dataset", choices=sorted(READERS), required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--units", default=None, help="comma-separated C-MAPSS unit numbers")
    parser.add_argument("--rate", type=float, default=10.0, help="rows per second")
    args = parser.parse_args(argv)
    if args.rate <= 0:
        parser.error("--rate must be positive")
    units = {int(u) for u in args.units.split(",")} if args.units else None
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings.from_env()
    plant = Catalog.load().fleet.plant.code
    node = SparkplugEdgeNode(settings.mqtt_host, settings.mqtt_port, plant, EDGE_NODE)
    node.start()
    waited = 0.0
    while not node.connected and waited < CONNECT_WAIT_S:
        time.sleep(0.2)
        waited += 0.2
    if not node.connected:
        log.warning(
            "MQTT broker %s:%s unreachable; rows are dropped until it connects",
            settings.mqtt_host,
            settings.mqtt_port,
        )
    try:
        sent = replay(args.dataset, args.file, args.rate, node, units)
        log.info("replayed %d rows from %s", sent, args.file)
    except KeyboardInterrupt:
        log.info("replay interrupted")
    finally:
        node.stop()


if __name__ == "__main__":
    main()
