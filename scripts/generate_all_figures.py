"""Generate paper figures from official result CSVs."""

from __future__ import annotations

import json

from scripts.finalize_phase_b import ensure_dirs, generate_heatmaps


def main() -> int:
    ensure_dirs()
    figures = generate_heatmaps()
    print(json.dumps({"status": "OK", "figures": figures}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
