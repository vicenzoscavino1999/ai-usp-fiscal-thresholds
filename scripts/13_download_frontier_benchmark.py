"""Download frontier benchmark inputs that have public APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "FRONTIER_BENCHMARK"
EUROSTAT_SOURCE_ID = "EUROSTAT_ISOC_EB_AI"
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/isoc_eb_ai?format=JSON"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_json(url: str, retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def category_codes(dataset: dict[str, object], dim: str) -> list[str]:
    category = dataset["dimension"][dim]["category"]
    index = category.get("index") or {}
    if isinstance(index, dict):
        return [code for code, _ in sorted(index.items(), key=lambda item: item[1])]
    if isinstance(index, list):
        return list(index)
    raise RuntimeError(f"Unsupported Eurostat category index for {dim}")


def unravel_index(flat_index: int, sizes: list[int]) -> list[int]:
    coords = [0] * len(sizes)
    remainder = flat_index
    for pos in range(len(sizes) - 1, -1, -1):
        size = sizes[pos]
        coords[pos] = remainder % size
        remainder //= size
    return coords


def eurostat_to_frame(dataset: dict[str, object]) -> pd.DataFrame:
    dimensions = dataset["id"]
    sizes = dataset["size"]
    codes_by_dim = {dim: category_codes(dataset, dim) for dim in dimensions}
    labels_by_dim = {
        dim: (dataset["dimension"][dim]["category"].get("label") or {})
        for dim in dimensions
    }
    values = dataset.get("value") or {}
    rows: list[dict[str, object]] = []
    for key, value in values.items():
        coords = unravel_index(int(key), sizes)
        row = {
            "benchmark_source": EUROSTAT_SOURCE_ID,
            "metric_family": "adoption_proxy",
            "value": value,
            "source_id": SOURCE_ID,
            "download_date": datetime.now(timezone.utc).date().isoformat(),
        }
        for dim, coord in zip(dimensions, coords, strict=True):
            code = codes_by_dim[dim][coord]
            row[dim] = code
            label = labels_by_dim[dim].get(code)
            if label is not None:
                row[f"{dim}_label"] = label
        rows.append(row)
    return pd.DataFrame(rows)


def country_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path, columns=["country_id"])
        return int(df["country_id"].dropna().astype(str).nunique())
    except Exception:  # noqa: BLE001
        return None


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": EUROSTAT_URL,
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        **payload,
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    declared_countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "frontier"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "frontier_benchmark.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    try:
        dataset = get_json(EUROSTAT_URL)
        df = eurostat_to_frame(dataset)
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": EUROSTAT_URL,
                "country_filter": "EU_BENCHMARK_ECONOMIES_ALL",
                "declared_pilot_countries": declared_countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": f"Eurostat isoc_eb_ai adoption-proxy pull failed: {exc}",
            },
        )
        print(f"Frontier benchmark pull failed: {exc}")
        return 2

    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": EUROSTAT_URL,
                "country_filter": "EU_BENCHMARK_ECONOMIES_ALL",
                "declared_pilot_countries": declared_countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "Eurostat isoc_eb_ai returned no values.",
            },
        )
        return 2

    df.to_parquet(out_file, index=False)
    aipi_metadata = load_json(raw_root / "imf_aipi" / "metadata.json")
    itu_metadata = load_json(raw_root / "itu" / "metadata.json")
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": EUROSTAT_URL,
            "country_filter": "EU_BENCHMARK_ECONOMIES_ALL",
            "declared_pilot_countries": declared_countries,
            "year_filter": sorted(df["time"].dropna().astype(str).unique().tolist()) if "time" in df else "all",
            "raw_file_hash": sha256_file(out_file),
            "input_completeness_checks": {
                "aipi_country_filter": aipi_metadata.get("country_filter"),
                "aipi_n_countries": country_count(raw_root / "imf_aipi" / "aipi.parquet"),
                "itu_country_filter": itu_metadata.get("country_filter"),
                "itu_n_countries": country_count(raw_root / "itu" / "itu_digital.parquet"),
            },
            "manual_registered_sources": [
                {
                    "source_id": "FRONTIER_NON_EU_AI_ADOPTION_USA",
                    "status": "manual_pending",
                    "notes": "Non-EU benchmarks such as USA remain registered manual inputs; benchmark-set selection is deferred to Phase 1 calibration.",
                }
            ],
            "notes": (
                "Captured Eurostat isoc_eb_ai adoption_proxy inputs. "
                "No benchmark set is selected here; Phase 1 calibration chooses the benchmark population."
            ),
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
