"""Pre-commit guard against accidentally versioning large or restricted files."""

from __future__ import annotations

import sys
from pathlib import Path


MAX_BYTES = 10 * 1024 * 1024
BLOCKED_PREFIXES = ("data/", "db/", "results/", "figures/")
BLOCKED_SUFFIXES = (".parquet", ".duckdb", ".sqlite", ".xlsx", ".xls", ".dta", ".sav")
ALLOWLIST_PREFIXES = (
    "reports/",
    "reproducibility/reference/",
    "reproducibility/snapshot/",
)


def normalized(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def allowed(path: str) -> bool:
    return path.startswith(ALLOWLIST_PREFIXES)


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv or sys.argv[1:])]
    failures: list[str] = []
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        rel = normalized(str(path))
        size = path.stat().st_size
        if not allowed(rel) and rel.startswith(BLOCKED_PREFIXES):
            failures.append(f"{rel}: blocked runtime/data path")
        if not allowed(rel) and rel.lower().endswith(BLOCKED_SUFFIXES):
            failures.append(f"{rel}: blocked binary/raw suffix")
        if size > MAX_BYTES and not allowed(rel):
            failures.append(f"{rel}: {size} bytes exceeds {MAX_BYTES} byte limit")
    if failures:
        print("Large-file/data guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
