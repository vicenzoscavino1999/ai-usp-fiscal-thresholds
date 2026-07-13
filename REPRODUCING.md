# Reproducing the Package

This is the operational contract for reviewers. The frozen design remains in
`REPRODUCIBILITY_PLAN.md`; this file records commands and outputs that were
actually exercised in the canonical container on 2026-07-10 and recaptured with
the direct Windows commands on 2026-07-11. `DATA_AVAILABILITY.md` states which
inputs may be redistributed, which derived artifacts enter the public archive,
and how to re-obtain and hash-check inputs that are not redistributed.

## One Command

The canonical environment is the digest-pinned Docker image. From the repository
root, with the author-held runtime folders present:

```powershell
docker build -t ai-usp-fiscal-thresholds .
docker run --rm `
  -v "${PWD}\data:/app/data" `
  -v "${PWD}\db:/app/db" `
  -v "${PWD}\results:/app/results" `
  -v "${PWD}\reports:/app/reports" `
  -v "${PWD}\figures:/app/figures" `
  ai-usp-fiscal-thresholds `
  sh -lc "make reproduce"
```

`make reproduce` runs the full primary package, verifies the archived reference,
audits the freeze, and verifies the five committed post-baseline extensions. It
does not re-download the extension inputs; use `make reproduce-extensions` for
that separate, network-dependent operation.

## The Seven Published Elements

The publication contract in the paper is implemented by the following tracked
artifacts. Paths are relative to the repository root.

1. **Country-year dataset.** The published four-country, 2024 anchor dataset is
   `reports/paper_tables/table1_anchors.csv` (one row each for CHL, COL, MEX, and
   PER). Its frozen-source provenance is
   `reproducibility/snapshot/dataset_manifest_v1.0.1-official-4c.json`; acquisition
   and redistribution status by source is in `DATA_AVAILABILITY.md`.
2. **Parameter matrix.** The publication matrix is
   `reports/paper_tables/master_calibration_matrix.csv`; the complete assignment
   and calibrated registries are
   `reports/value_assignment_table_baseline-official-v3.csv` and
   `reports/calibrated_parameter_registry_baseline-official-v3.csv`.
3. **Random seed.** `reproducibility/config/rng_policy.yaml`, field
   `monte_carlo_master_seed`, records `20260709`; the same value is preserved in
   `reports/run_manifest_baseline-official-v3.json` at
   `seeds.monte_carlo_master`. The historical bootstrap seed is the field
   `historical_bootstrap_seed` in the same YAML file.
4. **Draw count.** `reproducibility/config/rng_policy.yaml`, field
   `monte_carlo_draws_baseline`, records `5000`; every canonical result row records
   it in `reports/monte_carlo_result_baseline-official-v3.csv`, column
   `mc_n_draws`. The run manifest repeats it at `monte_carlo_draws_base` and
   records the convergence grid at `monte_carlo_convergence_grid`.
5. **Distributional supports.** The columns `low_value`, `baseline_value`,
   `high_value`, `distribution`, `truncation_rule`, and `support_type` in
   `reports/paper_tables/master_calibration_matrix.csv` publish the supports. The
   PERT shape convention is `monte_carlo_pert_lambda: 4` in
   `reproducibility/config/rng_policy.yaml`.
6. **Cleaning rules.** Source-specific fetch and filtering rules are executable in
   `scripts/01_download_wdi.py` through `scripts/18_download_casen_2024.py`;
   harmonization and anchor construction are implemented in
   `scripts/build_anchors_from_snapshot.py` and
   `scripts/build_official_4c_anchors.py`. Cross-source conventions are recorded
   in `metadata/data_conventions.yml`, and the frozen Tier-C input contract is
   `reproducibility/config/tierC_snapshot.yaml` plus the snapshot manifests under
   `reproducibility/snapshot/`.
7. **Exact code used to generate tables.** `scripts/finalize_phase_b.py` builds the
   paper tables and `scripts/reexport_paper_tables_designed.py` performs the
   designed re-export. `reports/paper_tables/paper_tables_manifest.csv` maps each
   artifact to its CSV and LaTeX outputs; the rendered inputs are tracked under
   `paper/tables/`.

   The split manuscript renders the core result tables (4--7) twice: a compact version in the
   main text (`table{4,5,6,7}_*.tex`) and a full-grid version in the online supplement
   (`table{4,5,6,7}_supp_full.tex`). Both sets live under `paper/tables/` and are drawn from
   the same manifest-cataloged source CSVs (`table4_vgross_baseline.csv`,
   `table5_threshold_inversion.csv`, `table6_historical_plausibility.csv`,
   `table7_monte_carlo.csv`); the `_supp_full` renderings extend the row coverage but introduce
   no new data object. `table8_final_classification` is a replication-package artifact catalogued
   in the manifest and not printed in the manuscript.

The additional requirement of at least two seeds or convergence diagnostics is
satisfied by the convergence arm. The 5,000/10,000/25,000/50,000-draw ladder and
its `delta_from_previous`, `convergence_tolerance`, and `converged_flag` fields are
published in `reports/paper_tables/appendix_j_mc_convergence.csv` (and its `.tex`
counterpart), with the full report in
`reports/mc_convergence_report_baseline-official-v3.csv`. Seeded repeatability is
also checked by `make determinism-check`, whose direct test modules are
`tests/test_determinism.py` and `tests/test_determinism_mc.py`.

## Captured Contract Lines

The 2026-07-10 parity audit was captured in the digest-pinned Linux container
with the author-held folders mounted. The clean image build took 54.3 seconds.
These canonical Docker lines are captured Make outputs, not examples:

| Target or direct equivalent | Captured final line | Measured wall time |
| --- | --- | ---: |
| `make verify-freeze` | `FREEZE VERIFY PASS: 14 protected files intact, spec hash intact, 5 amendment registries coherent` | <1 s |
| `make verify-extensions` | `EXTENSIONS VERIFY PASS: 5 extensions, 17 committed files, 382 stable columns, 8680 numeric comparisons` | 214 s |
| `make determinism-check` | `3 passed in 2.97s` | 3 s |
| `make test` | `43 passed in 10.62s` | 12 s |
| `make verify` | JSON status `PASS`; 30/30 reference files `PASS` | 3 s |

The cheap contracts were recaptured on 2026-07-11 with the direct Windows
PowerShell recipes listed under Non-Canonical Platforms. These are the current
local outputs; they supplement, but do not replace, the digest-pinned Docker
evidence above. The protected-file count rose from 14 to 15 between the two
captures because `paper/main.tex` entered the freeze manifest at the
post-compression swap (commit `0bb450a`); no other manifest entry changed:

| Direct Windows command | Captured final line | Measured wall time |
| --- | --- | ---: |
| `python reproducibility\verify_freeze.py` | `FREEZE VERIFY PASS: 15 protected files intact, spec hash intact, 5 amendment registries coherent` | 0.4 s |
| `python reproducibility\verify_extensions.py` | `EXTENSIONS VERIFY PASS: 5 extensions, 17 committed files, 382 stable columns, 8680 numeric comparisons` | 88.9 s |
| `python -m pytest tests\test_determinism.py tests\test_determinism_mc.py -q` | `3 passed in 2.44s` | 4.1 s |
| `python -m pytest -q` | `43 passed in 8.93s` | 10.0 s |
| `python reproducibility\verify.py` | JSON status `PASS`; 30/30 reference files `PASS` | 3.2 s |

`make reproduce-full` was not rerun during this documentation-only phase because
it rewrites `results/official/`. The last verified P03 record reports about 30
minutes for the complete run; the plan's measured envelope remains 15--40
minutes. This is prior recorded evidence, not a fresh capture.

## Target Map

```text
make verify-freeze        tracked specification, protected files, amendment chains
make verify-extensions    in-memory recomputation against committed extension CSVs
make reproduce-extensions public downloads plus all five extension runners
make determinism-check    repeated deterministic and seeded-MC checks
make test                 complete unit and contract suite
make verify               current results against reproducibility/reference
make reproduce            full primary reproduction plus freeze/extension verification
```

The volatile fields intentionally excluded by `verify-extensions` are:
`created_at*`, `build_id`, `runtime_seconds`, `commit_sha_at_run`,
`git_dirty_at_run`, and `download_date`. Every other stable column is compared;
numeric values use `atol=1e-10`, `rtol=1e-8`, and nonnumeric values compare
exactly. The paper-table re-export is checked by rerunning it and requiring
identical hashes; when Git metadata is available, it also requires an empty diff.

## Extension Prerequisites

| Extension | Reproduction input |
| --- | --- |
| omega-I reporting | Author-held `results/official/draws/*.parquet` (five frozen draw tables), plus the official DB/results inputs. These files are not tracked. |
| LS-raw | Public UN SNA downloads through `scripts/16_download_un_sna_labor_share.py`, hash-checked extension snapshot, plus official DB/results inputs. |
| GMI microdata Peru v2 | Public ENAHO 2024 through `scripts/17_download_enaho_sumaria.py`, hash-checked extension snapshot, plus official DB/results inputs. |
| GMI microdata Chile | Public CASEN 2024 through `scripts/18_download_casen_2024.py`, hash-checked extension snapshot, plus official DB/results inputs. |
| designed table re-export | Tracked `reports/paper_tables/*.csv` only; no network or author-held input. |

`make reproduce-extensions` checks all author-held prerequisites before starting.
If any are absent, it lists their paths and exits with a clear blocked message
instead of failing inside an extension runner.

## What This Proves

- The canonical runtime starts from `python:3.12.4-slim` pinned at digest
  `sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85`.
- `requirements-lock.txt` contains 1,122 SHA-256 requirement hashes; its file hash
  at this audit is `cb03f694292ebefe612f475776b359505bd3e63b269879d285ecd66e84e6bf18`.
- Repeated deterministic and seeded-Monte-Carlo checks return identical objects.
- `verify.py` pairs rows by canonical keys and checks the versioned reference.
  Tier A uses `atol=1e-10`, `rtol=1e-8`; Tier B probability tolerance is
  `atol=0.02`, `rtol=1e-8`; Tier C is exact hashes; Tier D is qualitative verdict
  and rank-change validation, as registered in `REPRODUCIBILITY_PLAN.md`.
- `make verify-freeze` exposes the primary-specification hash, 15 protected
  tracked files, and every supersession link in one command.
- `make verify-extensions` recomputes the four numerical extensions in memory and
  verifies the fifth by idempotent export without changing official outputs.

## Non-Canonical Platforms

Linux and macOS may run the Python commands directly in a Python 3.12 environment,
but Docker is the supported reference. Windows PowerShell can use these direct
equivalents when GNU Make is absent:

```powershell
python reproducibility\verify_freeze.py
python reproducibility\verify_extensions.py
python -m pytest tests\test_determinism.py tests\test_determinism_mc.py -q
python -m pytest -q
python reproducibility\verify.py
```

Platform-local runs establish code behavior but do not replace the digest-pinned
Docker evidence for a release.

## What a Reviewer Can Verify Without Author-Held Folders

The inventory below comes from `git ls-files`, not from the working-directory
contents:

| Tracked area | Files |
| --- | ---: |
| `reports/` | 185 |
| `paper/tables/` | 27 |
| `reproducibility/reference/` | 33 |
| `reproducibility/snapshot/` | 10 |
| `scripts/` | 38 |
| `data/`, `db/`, `results/` | 0 each |

A checkout alone supports the complete freeze audit, inspection and hash checking
of committed reports/reference/tables/manifests, the designed-table idempotence
check, and the tests that do not consume runtime folders. The public UN SNA,
ENAHO, and CASEN inputs can be re-downloaded by their numbered scripts and checked
against recorded hashes without an account.

The full `verify-extensions` target cannot honestly run from a checkout alone:
the four numerical extensions consume the author-held DuckDB and official runtime
results, and omega-I additionally consumes the five frozen draw parquets. Full
Tier A/B regeneration likewise requires `data/`, `db/`, and `results/`. GRD must
be obtained by each reviewer through UNU-WIDER's registration process. The data
verdicts are closed in `DATA_AVAILABILITY.md`: Ookla is CC BY-NC-SA 4.0 and only
the derived `gap_index` is archived; the CASEN required-variable extract is
archivable under CC BY 4.0; and ENAHO is distributed as aggregates plus download
scripts, source URLs, and verification hashes rather than as microdata.
