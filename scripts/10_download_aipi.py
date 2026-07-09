"""Download IMF AIPI indicators through World Bank Data360."""

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
SOURCE_ID = "IMF_AIPI_DATA360"
SOURCE_URL = "https://data360api.worldbank.org/data360/data?DATABASE_ID=IMF_AI"
INDICATOR_MAP = {
    "IMF_AI_AIPI_IX": "aipi_total",
    "IMF_AI_DIG_INF": "digital_infrastructure",
    "IMF_AI_HC_LMP": "human_capital_labor",
    "IMF_AI_INNOV_ECON_INT": "innovation_integration",
    "IMF_AI_REG_ETH": "regulation_ethics",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_json(retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(SOURCE_URL, timeout=60)
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
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    declared_countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "imf_aipi"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "aipi.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    try:
        data = get_json()
        values = data.get("value", []) if isinstance(data, dict) else []
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": SOURCE_URL,
                "country_filter": "ALL",
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": f"Data360 AIPI pull failed after retries: {exc}",
            },
        )
        print(f"AIPI pull failed: {exc}")
        return 2

    long = pd.DataFrame(values)
    if long.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": SOURCE_URL,
                "country_filter": "ALL",
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "Data360 AIPI endpoint returned no rows.",
            },
        )
        return 2
    long = long[long["INDICATOR"].isin(INDICATOR_MAP)]
    long["field"] = long["INDICATOR"].map(INDICATOR_MAP)
    long["OBS_VALUE"] = pd.to_numeric(long["OBS_VALUE"], errors="coerce")
    pivot = (
        long.pivot_table(index=["REF_AREA", "TIME_PERIOD"], columns="field", values="OBS_VALUE", aggfunc="first")
        .reset_index()
        .rename(columns={"REF_AREA": "country_id", "TIME_PERIOD": "year"})
    )
    for column in INDICATOR_MAP.values():
        if column not in pivot:
            pivot[column] = pd.NA
    pivot["year"] = pd.to_numeric(pivot["year"], errors="coerce").astype("Int64")
    pivot["source_id"] = SOURCE_ID
    df = pivot[
        [
            "country_id",
            "year",
            "aipi_total",
            "digital_infrastructure",
            "human_capital_labor",
            "innovation_integration",
            "regulation_ethics",
            "source_id",
        ]
    ]
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": SOURCE_URL,
            "country_filter": "ALL",
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "notes": f"Downloaded all AIPI economies as required for frontier benchmark. --countries was accepted ({declared_countries}) but not used to filter AIPI.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
