# Contributing

This repository is a research reproduction package. Changes must preserve the
separation between certified mechanics, calibration, data snapshots, and
outputs.

## Development Rules

1. Do not modify `src/ai_usp/` mechanics when a task is labelled calibration,
   diagnostics, reproducibility, or documentation only.
2. Do not commit `data/`, `db/`, `results/`, or raw source files. Use snapshot
   manifests and derived reports instead.
3. Every closing-stage change gets a commit named `etapa X: ...` and milestone
   tags are pushed with the commit.
4. If schemas change, update `reproducibility/config/schemas.yaml`, regenerate
   `reproducibility/reference/`, and run `python reproducibility/verify.py`.
5. If Monte Carlo outputs change, document seed, mode, draw count, tolerance,
   and whether the change affects final classification.

## Required Checks

```powershell
python -m pytest -q
python reproducibility\verify.py
python scripts\check_large_files.py <changed-files>
```

For release-candidate work, also run:

```powershell
make reproduce-full
docker build -t ai-usp-fiscal-thresholds .
```

## Reference Updates

Reference updates are allowed only when the change is intentional and
documented in `reproducibility/run_all.py` `REFERENCE_CHANGELOG`. The reference
manifest records the commit and dirty status at creation, so update it after the
relevant generated outputs have been produced.

## Data and Licensing

Raw data redistribution is source-dependent. GRD, Ookla, national microdata, and
manual files require their own policy notes. When in doubt, keep raw inputs
local and version only derived, non-restricted outputs with source attribution.
