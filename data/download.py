"""Download public PdM datasets into data/raw/<name>/ with sha256 verification (stdlib only).

Usage: python data/download.py cmapss ai4i metropt3 [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent / "raw"
CHUNK = 1 << 20


@dataclass(frozen=True)
class Dataset:
    url: str
    sha256: str | None


DATASETS: dict[str, Dataset] = {
    "cmapss": Dataset(
        "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip",
        "c9c5dec12a945a82e8bb4446589d7fb3cc057b5e5d81fa1a12e25ee9912ad3b2",
    ),
    "ai4i": Dataset(
        "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip",
        "f601f14294bcf190f9d720676b7f0aea46a26cde9ab8ebc7b4f8174d9d26b252",
    ),
    "metropt3": Dataset(
        "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip",
        "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a",
    ),
}


def fetch(url: str, dest: Path) -> str:
    digest = hashlib.sha256()
    tmp = dest.with_suffix(".part")
    request = urllib.request.Request(url, headers={"User-Agent": "twinvoice-data-download/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1e6:8.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    tmp.replace(dest)
    return digest.hexdigest()


def extract_all(archive: Path, target: Path) -> None:
    """Extract a zip, then any zips nested inside it (C-MAPSS ships a zip within a zip)."""
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            resolved = (target / member).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise RuntimeError(f"unsafe path in archive: {member}")
        zf.extractall(target)
    for inner in sorted(target.rglob("*.zip")):
        if inner != archive:
            extract_all(inner, inner.parent)
            inner.unlink()


def download(name: str, force: bool) -> bool:
    ds = DATASETS[name]
    target = RAW_DIR / name
    marker = target / ".complete"
    if marker.exists() and not force:
        print(f"[{name}] already present in {target}")
        return True
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    archive = RAW_DIR / f"{name}.zip"
    print(f"[{name}] downloading {ds.url}")
    actual = fetch(ds.url, archive)
    if ds.sha256 is None:
        print(
            f"[{name}] WARNING: no pinned checksum; integrity NOT verified.\n"
            f"[{name}] computed sha256 = {actual} (pin it in DATASETS to enable verification)",
            file=sys.stderr,
        )
    elif actual != ds.sha256:
        archive.unlink()
        print(
            f"[{name}] ERROR: sha256 mismatch: expected {ds.sha256}, got {actual}", file=sys.stderr
        )
        return False
    else:
        print(f"[{name}] sha256 verified")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    extract_all(archive, target)
    archive.unlink()
    marker.write_text(actual)
    print(f"[{name}] extracted to {target}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("datasets", nargs="+", choices=sorted(DATASETS))
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()
    ok = True
    for name in args.datasets:
        try:
            ok = download(name, args.force) and ok
        except OSError as exc:
            print(f"[{name}] ERROR: {exc}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
