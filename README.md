# AI-USP Fiscal Thresholds

Reproduction package for a calibrated accounting-fiscal threshold framework on
AI-induced fiscal space and universal or categorical social protection in Peru,
Chile, Colombia, and Mexico.

**Archived replication package:** DOI [10.5281/zenodo.21348535](https://doi.org/10.5281/zenodo.21348535)

Current status: the official pipeline is complete, five registered post-baseline
extensions are implemented, and paper v3 is in submission preparation. The
official data snapshot is `v1.0.1-official-4c`; the deterministic grid remains
`baseline-official-v2`, while uncertainty and diagnostics use
`baseline-official-v3`. See `REPRODUCING.md` for reviewer commands and
`REPRODUCIBILITY_STATUS.md` for the current operational inventory.

## Requirements

- Python 3.12.x.
- Docker 27+ for the canonical clean-run recipe.
- GNU Make in Docker or locally. Windows users can run the direct Python commands.
- The curated Zenodo ZIP includes every redistributable input required by
  `make reproduce-public`; `db/`, `results/`, and `figures/` are created at run
  time. A bare Git checkout intentionally omits `data/` and must restore the
  public snapshot first.
- Only the optional ENAHO microdata validation requires a separately obtained,
  non-redistributed input.

Install locally:

```powershell
python -m pip install --upgrade pip
pip install --require-hashes -r requirements-lock.txt
pip install --no-deps -e .
```

## Canonical Docker Run

```powershell
docker build -t ai-usp-fiscal-thresholds .
docker run --rm `
  -v "${PWD}\data:/app/data" `
  -v "${PWD}\db:/app/db" `
  -v "${PWD}\results:/app/results" `
  -v "${PWD}\reports:/app/reports" `
  -v "${PWD}\figures:/app/figures" `
  ai-usp-fiscal-thresholds `
  sh -lc "make reproduce-public"
```

The Dockerfile is pinned to `python:3.12.4-slim` by digest. `make
reproduce-public` first verifies the pristine freeze, then runs Tier A+B,
deterministic robustness, diagnostics, Phase B closure, H*, reference
verification, and all public extension checks. It does not contact data
providers.

## Local Commands

With Make:

```powershell
make reproduce-deterministic
make reproduce-full
make run-diagnostics
make verify
make test
```

Direct Windows recipe:

```powershell
python reproducibility\verify_freeze.py
python reproducibility\run_all.py --tier B --run-label official --parameter-set-id baseline-official-v2 --dataset-version v1.0.1-official-4c
python scripts\run_deterministic_robustness_6a.py
python scripts\run_diagnostics_6b.py
python scripts\finalize_phase_b.py
python scripts\run_h_star_extension_7_1.py
python reproducibility\verify.py
python reproducibility\verify_extensions.py
python -m pytest -q
```

`verify.py` compares `results/official/` against
`reproducibility/reference/`, enforces schemas, rejects missing/extra rows or
columns, checks NaN/type violations, and verifies the frozen snapshot manifest
hash.

## Building the Public Bundle

The public ZIP is built from tracked files plus an explicit data allowlist; do
not use a generic recursive archiver:

```powershell
python scripts\build_zenodo_bundle.py
python scripts\verify_zenodo_bundle.py dist\zenodo_bundle_v1.1.1-rc1.zip
```

The builder verifies frozen input hashes, excludes provider raw payloads and
ENAHO row-level microdata, normalizes text to LF, and writes a per-file
`BUNDLE_MANIFEST.json`. The verifier checks that manifest, unsafe paths,
symlinks, executable payloads, and the canonical primary-specification hash.

## Folder Structure

- `src/ai_usp/`: deterministic mechanics.
- `scripts/`: ingestion, anchor builders, calibration, runners, closure exports.
- `reproducibility/`: run harness, schemas, tolerances, snapshot manifests, reference outputs.
- `reproducibility/reference/`: versioned official reference CSVs and hashes.
- `reports/`: versioned audit reports, calibration exports, paper-table mirror.
- `results/`: local runtime outputs, including `results/paper_tables/`.
- `figures/`: local generated figures; mirrored under `reports/figures/` for review.
- `tests/`: unit, regression, schema, verifier, and closure tests.
- `metadata/`: conventions and manual source registry notes.
- `data/`: ignored by Git; curated redistributable snapshots are added only to
  the release ZIP. Restricted provider payloads remain local.
- `db/`: generated DuckDB runtime state, ignored by Git.

## Data Policy

The package stores snapshot manifests and derived audit artifacts, not all raw
inputs. `data/`, `db/`, `results/`, and `figures/` are ignored runtime folders.
Restricted microdata and author-downloaded raw files are not redistributed.
GRD 2025 is registered with the official UNU-WIDER citation and DOI. Ookla
Speedtest raw data is treated under CC BY-NC-SA 4.0: raw tiles are not
redistributed in this package; the derived `gap_index` is archived with
attribution and the license caveat.

## Paper Artifact Map

| Paper element | Code | Output | Verification |
| --- | --- | --- | --- |
| Feasibility ratio `Vgross` | `src/ai_usp/fiscal_space.py` | `fiscal_space_result.csv` | `verify.py`, `test_cost_monotonicity` |
| Threshold inversion | `src/ai_usp/thresholds.py` | `threshold_inversion_result.csv` | `test_frozen_weight_inversion` |
| Historical plausibility | `src/ai_usp/historical.py` | `historical_plausibility_result.csv` | `test_historical_class` |
| Monte Carlo probabilities | `scripts/run_official_monte_carlo.py` | `monte_carlo_result.csv` | Tier B tolerances, `test_determinism_mc` |
| Placebo ICT and controls | `scripts/run_diagnostics_6b.py` | `diagnostic_*_result.csv` | `test_diagnostics_6b` |
| Informality ablation H3 | `scripts/finalize_phase_b.py` | `informality_adoption_ablation_result.csv` | `test_phase_b_closure` |
| Paper tables/figures | `scripts/finalize_phase_b.py` | `results/paper_tables/`, `figures/` | final `verify.py` + pytest |
| Hypothesis H1-H5 | `scripts/finalize_phase_b.py` | `hypothesis_adjudication.csv` | schema-locked by `verify.py` |

## Governance

Author-approved calibration rows are materialized before result generation.
The primary specification hash is stored in `PRIMARY_SPEC_HASH.txt`; pre-flight
warns if it differs from the checked-out plan 02. Closing-stage commits are
tagged at each milestone.
