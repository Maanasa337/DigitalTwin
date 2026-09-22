"""Copy a model bundle to a device directory (e.g. a Raspberry Pi's /opt/twinvoice/models).

    python -m edge.export_models --src data/models --dst /mnt/pi/models rul-synthetic-cnc_mill [...]

Only what the edge reads is copied — bundle.json, model.onnx, booster.txt, anomaly.onnx — never
model.pkl: a device must not unpickle anything.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from edge.onnx_infer import latest_bundle_dir

EDGE_FILES = ("bundle.json", "model.onnx", "booster.txt", "anomaly.onnx")


def export_bundle(src: Path, dst: Path, model_name: str, version: str | None = None) -> Path:
    source = src / model_name / version if version else latest_bundle_dir(src, model_name)
    if not (source / "bundle.json").exists():
        raise FileNotFoundError(f"no bundle at {source}")
    target = dst / model_name / source.name
    target.mkdir(parents=True, exist_ok=True)
    for name in EDGE_FILES:
        if (source / name).exists():
            shutil.copy2(source / name, target / name)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m edge.export_models", description=__doc__)
    parser.add_argument("--src", type=Path, default=Path("data/models"))
    parser.add_argument("--dst", type=Path, required=True)
    parser.add_argument("--version", default=None, help="bundle version (default: newest)")
    parser.add_argument("models", nargs="+", help="model names, e.g. rul-synthetic-cnc_mill")
    args = parser.parse_args(argv)
    for name in args.models:
        print(f"{name} -> {export_bundle(args.src, args.dst, name, args.version)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
