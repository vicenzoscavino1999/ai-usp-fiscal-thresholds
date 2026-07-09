"""Download GRD from HDX when the 2025 resources are mirrored there."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "GRD"
HDX_PACKAGE_URL = "https://data.humdata.org/api/3/action/package_show?id=government-revenue-dataset"
UNU_WIDER_URL = "https://www.wider.unu.edu/project/grd-government-revenue-dataset"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, retries: int = 4) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def candidate_2025_resources(resources: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = []
    for resource in resources:
        name = str(resource.get("name") or "")
        fmt = str(resource.get("format") or "").lower()
        url = str(resource.get("url") or "")
        if "2025" not in f"{name} {url}":
            continue
        if not any(token in fmt for token in ["xlsx", "excel", "stata"]) and not re.search(r"\.(xlsx|dta|zip)(\?|$)", url, re.I):
            continue
        candidates.append(resource)
    return candidates


def dataframe_from_resource(payload: bytes, url: str) -> pd.DataFrame:
    lower_url = url.lower()
    if lower_url.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(payload))
    if lower_url.endswith(".dta"):
        return pd.read_stata(io.BytesIO(payload))
    if lower_url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = zf.namelist()
            dta = [name for name in names if name.lower().endswith(".dta")]
            xlsx = [name for name in names if name.lower().endswith(".xlsx")]
            if dta:
                with zf.open(dta[0]) as fh:
                    return pd.read_stata(fh)
            if xlsx:
                with zf.open(xlsx[0]) as fh:
                    return pd.read_excel(fh)
    raise RuntimeError(f"Unsupported GRD resource format: {url}")


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": HDX_PACKAGE_URL,
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
    out_dir = raw_root / "grd"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "grd_revenue.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    try:
        package = get(HDX_PACKAGE_URL).json()["result"]
        resources = package.get("resources") or []
        candidates = candidate_2025_resources(resources)
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "manual_pending",
                "query_or_endpoint": HDX_PACKAGE_URL,
                "country_filter": countries,
                "year_filter": "1980-2023 expected in GRD 2025",
                "raw_file_hash": None,
                "manual_registration": {
                    "source_url": UNU_WIDER_URL,
                    "hash_status": "pending_manual_file",
                    "instructions": "HDX CKAN request failed; download GRD 2025 Excel/Stata from UNU-WIDER and register sha256 before use.",
                },
                "notes": f"HDX CKAN package_show failed; registered UNU-WIDER GRD 2025 as manual_pending: {exc}",
            },
        )
        print("GRD HDX failed; registered manual_pending")
        return 0

    if not candidates:
        available = [resource.get("name") for resource in resources]
        write_metadata(
            out_dir,
            {
                "status": "manual_pending",
                "query_or_endpoint": HDX_PACKAGE_URL,
                "country_filter": countries,
                "year_filter": "1980-2023 expected in GRD 2025",
                "raw_file_hash": None,
                "manual_registration": {
                    "source_url": UNU_WIDER_URL,
                    "hash_status": "pending_manual_file",
                    "instructions": (
                        "HDX CKAN package is reachable but does not expose a 2025 GRD Excel/Stata resource. "
                        "Download the November 2025 GRD file from UNU-WIDER, store the original, compute sha256, "
                        "and update metadata/manual_source_registry.yml."
                    ),
                },
                "available_hdx_resources": available,
                "notes": "HDX mirror did not expose the requested Nov 2025 GRD resources; old 2022 resources were not used.",
            },
        )
        print("GRD 2025 not available in HDX CKAN; registered manual_pending")
        return 0

    resource = candidates[0]
    resource_url = str(resource["url"])
    payload = get(resource_url).content
    try:
        df = dataframe_from_resource(payload, resource_url)
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "manual_pending",
                "query_or_endpoint": [HDX_PACKAGE_URL, resource_url],
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "download_file_hash": sha256_bytes(payload),
                "manual_registration": {
                    "source_url": UNU_WIDER_URL,
                    "hash_status": "downloaded_but_parse_failed",
                    "instructions": f"GRD 2025 file downloaded from HDX but parsing failed: {exc}",
                },
                "notes": "GRD 2025 HDX resource was found but could not be converted to parquet automatically.",
            },
        )
        print(f"GRD parse failed; registered manual_pending: {exc}")
        return 0

    if "ISO" in df.columns:
        df = df[df["ISO"].isin(countries)]
    elif "iso" in df.columns:
        df = df[df["iso"].str.upper().isin(countries)]
    df["source_id"] = SOURCE_ID
    df["download_date"] = datetime.now(timezone.utc).date().isoformat()
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": [HDX_PACKAGE_URL, resource_url],
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "download_file_hash": sha256_bytes(payload),
            "resource_name": resource.get("name"),
            "notes": "GRD 2025 resource downloaded from HDX CKAN and converted to parquet.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
