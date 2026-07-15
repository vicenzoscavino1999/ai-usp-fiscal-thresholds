# Release Notes — v1.1.1-rc1

**Related Zenodo record:** DOI [10.5281/zenodo.21348535](https://doi.org/10.5281/zenodo.21348535)

## Scope

This release candidate provides the complete public replication path for the
AI-USP fiscal-threshold framework: deterministic results, Monte Carlo analysis,
robustness specifications, diagnostics, H*, publication tables and automated
verification.

## Included

- Four-country official baseline snapshot and model inputs.
- WPP 2024 medium-variant projection through 2050 for H*.
- Independent and correlated Monte Carlo modes and convergence diagnostics.
- Deterministic robustness, placebo and falsification specifications.
- H* results, manual-check inputs and registered amendment metadata.
- Public omega-I, UN SNA labor-share and CASEN extension inputs.
- CSV and LaTeX publication tables with idempotent reexport checks.
- Digest-pinned Docker environment and hash-locked Python dependencies.
- Per-file bundle manifest and archive-safety verifier.

## Restricted Supplement

The public archive excludes ENAHO row-level microdata pending an unambiguous
redistribution basis for the exact required-variable extract. Reviewers may
obtain the source independently and run the registered restricted verification.

## Verification

The supported validation commands are:

```text
make reproduce-public
python reproducibility/verify.py
python reproducibility/verify_extensions.py
python -m pytest -q
```

The complete release matrix and scope notes are provided in `VALIDATION.md`.
