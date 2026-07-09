"""Download World Bank PIP poverty statistics for the raw PIP table."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.0-stage1"
SOURCE_ID = "PIP"
SOURCE_URL = "https://api.worldbank.org/pip/v1/pip"


def parse_countries(value: str) -> list[str]:
    return [c.strip().upper() for c in value.split(",") if c.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_json(params: dict[str, str], retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(SOURCE_URL, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


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
    parser.add_argument("--poverty-lines", default="3.00,4.20,8.30")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    countries = parse_countries(args.countries)
    poverty_lines = [p.strip() for p in args.poverty_lines.split(",") if p.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "pip"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "pip_poverty.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    rows: list[dict[str, object]] = []
    endpoints: list[str] = []
    for country in countries:
        for poverty_line in poverty_lines:
            params = {"country": country, "povline": poverty_line, "format": "json"}
            endpoints.append(requests.Request("GET", SOURCE_URL, params=params).prepare().url or SOURCE_URL)
            data = get_json(params)
            if not isinstance(data, list):
                continue
            for item in data:
                rows.append(
                    {
                        "country_id": item.get("country_code") or country,
                        "year": item.get("reporting_year"),
                        "poverty_line": item.get("poverty_line"),
                        "poverty_line_type": "international",
                        "unit": "USD_PPP_per_day",
                        "currency": "USD_PPP",
                        "periodicity": "daily",
                        "ppp_version": item.get("ppp_version") or "2021",
                        "price_base_year": 2021,
                        "reporting_level": item.get("reporting_level"),
                        "headcount": item.get("headcount"),
                        "poverty_gap": item.get("poverty_gap"),
                        "mean_income_or_consumption": item.get("mean"),
                        "welfare_type": item.get("welfare_type"),
                        "source_id": SOURCE_ID,
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "PIP API returned no rows.",
            },
        )
        return 2
    columns = [
        "country_id",
        "year",
        "poverty_line",
        "poverty_line_type",
        "unit",
        "currency",
        "periodicity",
        "ppp_version",
        "price_base_year",
        "reporting_level",
        "headcount",
        "poverty_gap",
        "mean_income_or_consumption",
        "welfare_type",
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
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "notes": "PIP REST pull preserving unit/currency/periodicity/ppp fields required by Plan 01 section 13.4.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
