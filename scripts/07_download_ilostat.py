"""Download ILOSTAT annual bulk files by reference area."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.0-stage1"
SOURCE_ID = "ILOSTAT"
SOURCE_URL = "https://rplumber.ilo.org/data/ref_area"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, retries: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def pick_class(row: pd.Series, prefixes: tuple[str, ...]) -> object:
    for key in ("classif1", "classif2"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith(prefixes):
            return value
    return None


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
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
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "ilostat"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "ilostat_labor.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    frames: list[pd.DataFrame] = []
    endpoints: list[str] = []
    try:
        for country in countries:
            url = f"{SOURCE_URL}?id={country}_A&format=.csv.gz"
            endpoints.append(url)
            content = download(url)
            source = pd.read_csv(io.BytesIO(content), compression="gzip")
            source = source.rename(columns={"ref_area": "country_id", "time": "year", "obs_value": "value"})
            normalized = pd.DataFrame(
                {
                    "country_id": source["country_id"],
                    "year": pd.to_numeric(source["year"], errors="coerce").astype("Int64"),
                    "indicator_code": source["indicator"],
                    "indicator_name": source["indicator"],
                    "sex": source.get("sex"),
                    "age_group": source.apply(lambda row: pick_class(row, ("AGE_",)), axis=1),
                    "sector_code": source.apply(lambda row: pick_class(row, ("ECO_", "SECTOR_", "ISIC")), axis=1),
                    "occupation_code": source.apply(lambda row: pick_class(row, ("OCU_", "ISCO")), axis=1),
                    "value": pd.to_numeric(source["value"], errors="coerce"),
                    "unit": "",
                    "source_id": SOURCE_ID,
                }
            )
            frames.append(normalized)
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all annual",
                "raw_file_hash": None,
                "notes": f"ILOSTAT bulk pull failed after retries: {exc}",
            },
        )
        print(f"ILOSTAT pull failed: {exc}")
        return 2

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all annual",
                "raw_file_hash": None,
                "notes": "ILOSTAT bulk returned no rows.",
            },
        )
        return 2
    columns = [
        "country_id",
        "year",
        "indicator_code",
        "indicator_name",
        "sex",
        "age_group",
        "sector_code",
        "occupation_code",
        "value",
        "unit",
        "source_id",
    ]
    df = df[columns]
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": countries,
            "year_filter": "all annual",
            "raw_file_hash": sha256_file(out_file),
            "notes": "ILOSTAT bulk ref_area annual files. classif1/classif2 are mapped only when prefixes identify age, sector, or occupation.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
