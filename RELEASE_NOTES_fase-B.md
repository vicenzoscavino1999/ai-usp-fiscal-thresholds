# Draft Release Notes: fase-B

## Scope

Phase B release candidate for the AI-USP fiscal thresholds reproduction package.
This tag closes the deterministic official grid, Monte Carlo Tier B, robustness,
diagnostics/falsification, paper-table exports, and minimum publication
documentation.

## Included

- Official four-country deterministic Tier A reference.
- Monte Carlo independent and correlated modes for `baseline-official-v3`.
- Deterministic robustness Exp. 6 and review fixes.
- Tier D diagnostics: placebo ICT, negative controls, leave-one-source-out,
  channel ablation, no-rent capture, high leakage, Sobol/Saltelli.
- New Phase B informality adoption-only ablation for H3.
- Final H1-H5 hypothesis adjudication.
- Paper tables and appendices A-K as CSV and booktabs LaTeX.
- Vgross heatmaps by country.
- Digest-pinned Dockerfile, GitHub Actions smoke workflow, pre-commit
  large-file guard, and data-license policy.

## Key Result Notes

- H1: `MIXED`; broad high-cost gradient holds, but strict instrument ordering
  does not.
- H2: `NOT_TESTABLE`; country-specific `E_prod` is not available.
- H3: `MIXED`; adoption-only informal-ablation changes `q_bar` but not
  `q_prod` or `V` under the frozen target/intercept convention.
- H4: `HOLDS`; fiscal regimes materially affect feasibility.
- H5: `HOLDS`; extreme fiscal-capture requirements are not used for robust
  feasibility claims.
- D2 negative control: mechanical collapse occurs, but CHL GMI stress survives;
  CHL GMI remains conditional and caveated, not robust.

## Not Included

- Public Zenodo deposition.
- Public release visibility change.
- GMI microdata-strong variant.
- Country-specific productive-exposure estimates.

## Validation Before Tag

- `python -m pytest -q`
- `python reproducibility/verify.py`
- Docker build and `make reproduce-full` with local author-held `data/` and `db/`
