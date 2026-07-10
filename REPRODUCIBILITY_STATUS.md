# Reproducibility Status

Operational status as of 2026-07-10. This note does **not** replace or amend the
frozen `REPRODUCIBILITY_PLAN.md`; it maps the implemented package to that plan.

## Current Frozen Objects

- Official baseline snapshot: `v1.0.1-official-4c`.
- H-star reporting extension snapshot: `v1.1.0-official-4c`; it does not replace
  the baseline snapshot.
- Deterministic official parameter set: `baseline-official-v2`.
- Uncertainty/diagnostic parameter set: `baseline-official-v3`.
- Extension sets: `robustness-lsraw-v1`, `robustness-gmimicro-per-v1`
  (preserved but superseded), `robustness-gmimicro-per-v2`, and
  `robustness-gmimicro-chl-v1`.

## Freeze Provenance

`PRIMARY_SPEC_HASH.txt` declares
`0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81`
for `02_ESD_AI_USP_v6.md`. The same value is obtained from the file on disk.
`reproducibility/protected_files_manifest.json` records 14 tracked official files
and their SHA-256 hashes.

The amendment chain is:

| Amendment ID | Supersedes |
| --- | --- |
| `Q0_h_star_post_baseline_extension` | none |
| `OMEGA_I_REPORTING_EXTENSION_2026_07_10` | none |
| `LS_RAW_VS_ADJUSTED_ROBUSTNESS_EXTENSION_2026_07_10` | none |
| `GMI_MICRODATA_STRONG_PER_EXTENSION_2026_07_10` | none |
| `GMI_MICRODATA_STRONG_PER_PIP_LINE_CORRECTION_2026_07_10` | `GMI_MICRODATA_STRONG_PER_EXTENSION_2026_07_10` |
| `GMI_MICRODATA_STRONG_CHL_EXTENSION_2026_07_10` | none |

Audit command:

```text
make verify-freeze
FREEZE VERIFY PASS: 14 protected files intact, spec hash intact, 5 amendment registries coherent
```

## Tier Status

| Tier | Operational status | Verification |
| --- | --- | --- |
| A | Complete: deterministic baseline, grid, inversions, historical plausibility and preliminary classification. | Strict reference comparison, `atol=1e-10`, `rtol=1e-8`. |
| B | Complete: independent and correlated Monte Carlo, convergence, drivers and final classification. | Registered Tier B tolerances; seeded determinism tests. |
| C | Frozen manifests operational; raw and runtime folders remain author-held. | Exact manifest/file hashes, no numeric tolerance. |
| D | Complete: placebo ICT, negative control, LOSO, channel/rent/leakage diagnostics and Sobol. | Qualitative verdict and rank-change contracts. |

## Extension Status

| Extension | Status | Verification scope |
| --- | --- | --- |
| omega-I sensitivity | Registered and committed | Full ranking recomputed from frozen author-held draws. |
| LS raw versus adjusted | Registered and committed | Parameter chain and 480-cell comparison recomputed. |
| GMI microdata Peru v2 | Registered correction; v1 retained and superseded | Validation, costs, parameter set and 40-cell comparison recomputed. |
| GMI microdata Chile | Registered and committed | Validation, costs, parameter set and 40-cell comparison recomputed. |
| designed paper-table re-export | Registered and committed | Three LaTeX tables rerun idempotently with empty Git diff. |

The captured aggregate verdict is:

```text
EXTENSIONS VERIFY PASS: 5 extensions, 17 committed files, 382 stable columns, 8680 numeric comparisons
```

The full extension verifier is intentionally absent from CI because it requires
untracked author-held DB/results/draw files. CI runs the cheap standalone freeze
audit, the existing fixture/reference checks, and the test suite; it does not
download large public microdata.
