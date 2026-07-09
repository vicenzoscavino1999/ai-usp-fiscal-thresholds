"""Download public Peru macro-fiscal contrast series from BCRPData."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "NATIONAL_PER_BCRP"
SOURCE_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SUNAT_URL = "https://www.sunat.gob.pe/estadisticasestudios/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

BCRP_GROUPS = {
    "annual": {
        "start": "1990",
        "end": "2025",
        "codes": {
            "PM10103FA": {
                "variable_code": "tax_revenue_central_gov_gdp",
                "unit": "percent_of_gdp",
                "description": "Ingresos tributarios del Gobierno Central (% PBI)",
            },
            "PM04863AA": {
                "variable_code": "gdp_growth_real",
                "unit": "percent_change",
                "description": "PBI (variacion porcentual)",
            },
            "PM05776FA": {
                "variable_code": "primary_balance_spnf_gdp",
                "unit": "percent_of_gdp",
                "description": "Resultado primario del sector publico no financiero (% PBI)",
            },
            "PM05848FA": {
                "variable_code": "overall_balance_central_gov_gdp",
                "unit": "percent_of_gdp",
                "description": "Resultado economico del Gobierno Central (% PBI)",
            },
            "PM05846FA": {
                "variable_code": "primary_balance_central_gov_gdp",
                "unit": "percent_of_gdp",
                "description": "Resultado primario del Gobierno Central (% PBI)",
            },
            "PM05876FA": {
                "variable_code": "tax_revenue_general_gov_gdp",
                "unit": "percent_of_gdp",
                "description": "Ingresos tributarios del Gobierno General (% PBI)",
            },
        },
    },
    "quarterly": {
        "start": "1990-1",
        "end": "2026-1",
        "codes": {
            "PN03112FQ": {
                "variable_code": "primary_balance_spnf_gdp_quarterly",
                "unit": "percent_of_gdp",
                "description": "Resultado primario del sector publico no financiero (% PBI), trimestral",
            },
            "PN03432FQ": {
                "variable_code": "public_debt_spnf_gdp_quarterly",
                "unit": "percent_of_gdp",
                "description": "Saldo de deuda del sector publico no financiero (% PBI), trimestral",
            },
        },
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_json(url: str, retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def parse_period(period: str, frequency: str) -> tuple[int | None, int | None]:
    if frequency == "annual":
        return int(period), None
    match = re.fullmatch(r"T([1-4])\.(\d{2})", period)
    if not match:
        return None, None
    quarter = int(match.group(1))
    yy = int(match.group(2))
    year = 1900 + yy if yy >= 50 else 2000 + yy
    return year, quarter


def rows_from_group(frequency: str, group: dict[str, object]) -> tuple[list[dict[str, object]], str]:
    codes = list(group["codes"].keys())
    url = f"{SOURCE_URL}/{'-'.join(codes)}/json/{group['start']}/{group['end']}"
    payload = get_json(url)
    series_meta = (payload.get("config") or {}).get("series") or []
    periods = payload.get("periods") or []
    rows: list[dict[str, object]] = []
    for period in periods:
        period_name = period.get("name")
        values = period.get("values") or []
        year, quarter = parse_period(str(period_name), frequency)
        for position, code in enumerate(codes):
            value = values[position] if position < len(values) else None
            if value in {"n.d.", "nd", ""}:
                value = None
            code_meta = group["codes"][code]
            rows.append(
                {
                    "country_id": "PER",
                    "frequency": frequency,
                    "period": period_name,
                    "year": year,
                    "quarter": quarter,
                    "series_code": code,
                    "series_name": (series_meta[position] or {}).get("name") if position < len(series_meta) else code_meta["description"],
                    "variable_code": code_meta["variable_code"],
                    "value": pd.to_numeric(value, errors="coerce"),
                    "unit": code_meta["unit"],
                    "source_id": SOURCE_ID,
                    "download_date": datetime.now(timezone.utc).date().isoformat(),
                }
            )
    return rows, url


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
    out_dir = raw_root / "national"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "national_per_bcrp.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    if "PER" not in countries:
        write_metadata(
            out_dir,
            {
                "status": "manual_pending",
                "query_or_endpoint": None,
                "country_filter": countries,
                "year_filter": "not_applicable",
                "raw_file_hash": None,
                "notes": "No BCRPData pull attempted because PER is not in --countries.",
            },
        )
        return 0

    rows: list[dict[str, object]] = []
    endpoints: list[str] = []
    try:
        for frequency, group in BCRP_GROUPS.items():
            group_rows, endpoint = rows_from_group(frequency, group)
            rows.extend(group_rows)
            endpoints.append(endpoint)
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "1990-2026",
                "raw_file_hash": None,
                "notes": f"BCRPData API pull failed: {exc}. SUNAT remains manual_registered.",
            },
        )
        print(f"BCRPData pull failed: {exc}")
        return 2

    df = pd.DataFrame(rows)
    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "1990-2026",
                "raw_file_hash": None,
                "notes": "BCRPData API returned no rows. SUNAT remains manual_registered.",
            },
        )
        return 2

    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": ["PER"],
            "year_filter": {"annual": "1990-2025", "quarterly": "1990Q1-2026Q1"},
            "raw_file_hash": sha256_file(out_file),
            "bcrp_series_codes": {frequency: list(group["codes"].keys()) for frequency, group in BCRP_GROUPS.items()},
            "manual_registered_sources": [
                {
                    "source_id": "SUNAT_PER",
                    "source_url": SUNAT_URL,
                    "status": "manual_pending",
                    "instructions": "Download SUNAT statistical Excel tables manually and register file hash before use.",
                }
            ],
            "notes": "BCRPData API implemented for Peru macro-fiscal contrast series; SUNAT Excel tables are manual_registered.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
