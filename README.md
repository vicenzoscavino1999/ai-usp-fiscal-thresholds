# AI-USP Fiscal Thresholds

This repository is the reproduction package for the AI-USP fiscal threshold
framework. It combines frozen country data, an audited calibration registry, a
certified deterministic engine, and archived reference outputs for the official
four-country baseline (`PER`, `CHL`, `COL`, `MEX`).

Current status: Phase A deterministic Tier A is operational and verified
against the archived reference. Tier B Monte Carlo and Tier D diagnostics are
treated as Phase B work for official claims, although review artifacts from the
Monte Carlo apparatus are archived for audit continuity.

## Requirements

- Python 3.12.x.
- Docker, for the canonical clean-run recipe.
- GNU Make, optional on Windows because direct Python commands are provided.
- Local frozen data under `data/`, local DuckDB under `db/`, and writable
  `results/`; these are intentionally not versioned.

Install locally:

```powershell
python -m pip install --upgrade pip
pip install --require-hashes -r requirements-lock.txt
pip install --no-deps -e .
```

## Canonical Docker Run

From the repository root in PowerShell:

```powershell
docker build -t ai-usp-fiscal-thresholds .
docker run --rm `
  -v "${PWD}\data:/app/data" `
  -v "${PWD}\db:/app/db" `
  -v "${PWD}\results:/app/results" `
  -v "${PWD}\reports:/app/reports" `
  ai-usp-fiscal-thresholds `
  sh -lc "make reproduce-deterministic && make verify"
```

## Local Reproduction

With Make:

```powershell
make reproduce-deterministic
make verify
```

Direct Windows recipe without Make:

```powershell
python reproducibility\run_all.py --tier A --run-label official --parameter-set-id baseline-official-v2 --dataset-version v1.0.1-official-4c
python reproducibility\verify.py
python -m pytest
```

The verification target compares current outputs in `results/official/` against
the archived reference in `reproducibility/reference/` using the schemas and
tolerances under `reproducibility/config/`.

## Folder Structure

- `src/ai_usp/`: certified deterministic model components.
- `scripts/`: data ingestion, anchor construction, calibration, and runners.
- `reproducibility/`: run harness, schemas, tolerances, and reference outputs.
- `reproducibility/reference/`: versioned official reference CSVs and hashes.
- `reproducibility/snapshot/`: versioned frozen snapshot manifests only.
- `reports/`: versioned audit reports, calibration exports, and summaries.
- `tests/`: unit, regression, schema, and verifier tests.
- `metadata/`: conventions and source registry notes.
- `paper/`: paper scaffold and references.
- `data/`, `db/`, `results/`, `figures/`: local, ignored runtime artifacts.

## Data Policy

The package is built around frozen snapshot manifests rather than redistributing
all raw inputs. `data/` is local and ignored. Microdata and manually downloaded
restricted files are not redistributed. GRD 2025 is registered as an author-held
manual source with the official UNU-WIDER citation and DOI; derived audit
contrasts are versioned where allowed. Ookla Speedtest raw data is treated under
its CC BY-NC license note: internal snapshot use is recorded, while public raw
archiving is deferred; derived gap-index outputs are archived. The official
snapshot version for Phase A is `v1.0.1-official-4c`.

## Governance

The official parameter set is `baseline-official-v2`. Rows requiring author
review were materialized as `author_approved` before official deterministic
results. The primary specification hash is stored in `PRIMARY_SPEC_HASH.txt`;
the pre-flight emits a warning if it differs from the checked-out plan 02.

Git policy from Phase A onward: commit at the close of each stage using
`etapa X: ...`; tag major milestones (`fase-A`, `fase-B`, `submission`);
push each closing-stage commit to `origin` together with its tags.
