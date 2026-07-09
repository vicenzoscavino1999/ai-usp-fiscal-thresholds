"""Register SEDLAC/CEDLAS as a manual source for the pilot snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "SEDLAC"
SOURCE_URL = "https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/"

EXPECTED_FIELDS = [
    "country_id",
    "survey_year",
    "welfare_concept",
    "poverty_headcount",
    "poverty_gap",
    "gini",
    "income_deciles",
    "informality_rate",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    args = parser.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "sedlac"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "query_or_endpoint": "manual download: CEDLAS SEDLAC statistics Excel files",
        "country_filter": countries,
        "year_filter": "all available survey years",
        "raw_file_hash": None,
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        "status": "manual_pending",
        "manual_registration": {
            "registration_script": "12_register_manual_sources.py",
            "expected_fields": EXPECTED_FIELDS,
            "hash_status": "pending_manual_file",
            "instructions": (
                "Download SEDLAC/CEDLAS Excel statistics from the CEDLAS SEDLAC site, "
                "store the original file under the manual-source intake area, compute "
                "sha256, and update metadata/manual_source_registry.yml before any "
                "non-pilot run that uses SEDLAC values."
            ),
        },
        "notes": "SEDLAC/CEDLAS has no public API for this pull; registered as manual_pending, not as a pipeline failure.",
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(payload["notes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
