"""Download IMF DataMapper fiscal/macro indicators with browser headers."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.2-stage1"
SOURCE_ID = "IMF_WEO_GFS"
SOURCE_URL = "https://www.imf.org/external/datamapper/api/v1"
WEO_BULK_URL = "https://www.imf.org/en/Publications/WEO/weo-database"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.imf.org/external/datamapper/",
}
INDICATORS = {
    "GGXWDG_NGDP": {
        "source_code": "G_XWDG_G01_GDP_PT",
        "name": "General government gross debt, percent of GDP",
        "unit": "percent_of_gdp",
        "dataset_note": "Fiscal Monitor DataMapper alias used for consistency with primary balance and revenue.",
    },
    "GGXONLB_NGDP": {
        "source_code": "GGXONLB_G01_GDP_PT",
        "name": "General government primary net lending/borrowing, percent of GDP",
        "unit": "percent_of_gdp",
        "dataset_note": "Fiscal Monitor DataMapper alias because GGXONLB_NGDP is not exposed in the public WEO DataMapper catalog.",
    },
    "GGXCNL_NGDP": {
        "source_code": "GGXCNL_G01_GDP_PT",
        "name": "General government net lending/borrowing, percent of GDP",
        "unit": "percent_of_gdp",
        "dataset_note": "Fiscal Monitor DataMapper alias used for consistency with primary balance.",
    },
    "GGR_NGDP": {
        "source_code": "GGR_G01_GDP_PT",
        "name": "General government revenue, percent of GDP",
        "unit": "percent_of_gdp",
        "dataset_note": "Fiscal Monitor DataMapper alias because GGR_NGDP is not exposed in the public WEO DataMapper catalog.",
    },
    "NGDPD": {
        "source_code": "NGDPD",
        "name": "Gross domestic product, current prices, U.S. dollars",
        "unit": "current_usd",
        "dataset_note": "WEO DataMapper.",
    },
    "NGDP_RPCH": {
        "source_code": "NGDP_RPCH",
        "name": "Gross domestic product, constant prices, percent change",
        "unit": "percent_change",
        "dataset_note": "WEO DataMapper.",
    },
    "PCPIPCH": {
        "source_code": "PCPIPCH",
        "name": "Inflation, average consumer prices, percent change",
        "unit": "percent_change",
        "dataset_note": "WEO DataMapper.",
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
            response = requests.get(url, timeout=60, headers=HEADERS)
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


def write_manual_fallback(out_dir: Path, endpoints: list[str], countries: list[str], exc: Exception) -> int:
    write_metadata(
        out_dir,
        {
            "status": "manual_pending",
            "query_or_endpoint": endpoints,
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": None,
            "manual_registration": {
                "source_url": WEO_BULK_URL,
                "hash_status": "pending_manual_file",
                "instructions": (
                    "IMF DataMapper API remained unavailable after browser User-Agent retries. "
                    "Download the latest WEO database bulk file from IMF, store the original, "
                    "compute sha256, and register the file before using IMF fiscal anchors."
                ),
            },
            "notes": f"IMF DataMapper API failed after retries; WEO bulk registered as manual_pending: {exc}",
        },
    )
    print(f"IMF pull unavailable; registered manual_pending: {exc}")
    return 0


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
    out_dir = raw_root / "imf"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "imf_fiscal_macro.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    rows: list[dict[str, object]] = []
    endpoints: list[str] = []
    missing_required: list[str] = []
    resolved_codes: dict[str, object] = {}
    for code, spec in INDICATORS.items():
        source_code = str(spec["source_code"])
        resolved_codes[code] = spec
        for country in countries:
            url = f"{SOURCE_URL}/{source_code}/{country}"
            endpoints.append(url)
            try:
                data = get_json(url)
            except Exception as exc:  # noqa: BLE001
                return write_manual_fallback(out_dir, endpoints, countries, exc)
            values = ((data or {}).get("values") or {}).get(source_code) or {}
            series = values.get(country) or {}
            if not series:
                missing_required.append(f"{code} via {source_code}/{country}")
            for year, value in series.items():
                rows.append(
                    {
                        "country_id": country,
                        "year": int(year),
                        "variable_code": code,
                        "source_variable_code": source_code,
                        "variable_name": spec["name"],
                        "value": value,
                        "unit": spec["unit"],
                        "source_id": SOURCE_ID,
                    }
                )
    if missing_required:
        return write_manual_fallback(
            out_dir,
            endpoints,
            countries,
            RuntimeError("No DataMapper rows for required series: " + "; ".join(missing_required)),
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
                "notes": "IMF DataMapper API returned no rows for the requested country filters.",
            },
        )
        return 2
    df = df[["country_id", "year", "variable_code", "source_variable_code", "variable_name", "value", "unit", "source_id"]]
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "request_headers": {"User-Agent": HEADERS["User-Agent"], "Referer": HEADERS["Referer"]},
            "resolved_indicator_codes": resolved_codes,
            "manual_registration": {
                "source_url": WEO_BULK_URL,
                "status": "manual_contrast_optional",
                "instructions": "If exact WEO bulk fiscal codes are required later, download the latest WEO database bulk file from IMF, store the original, compute sha256, and register it before replacing these DataMapper Fiscal Monitor aliases.",
            },
            "notes": "IMF DataMapper API pull using browser User-Agent; response filtered explicitly to requested ISO3 countries. Fiscal Monitor DataMapper aliases are used where the requested WEO-style codes are not exposed in the public indicator catalog.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
