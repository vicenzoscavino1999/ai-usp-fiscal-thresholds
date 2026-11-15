# Continuous integration

The public workflow `.github/workflows/reproduction.yml` has two explicitly named scopes.

1. **Package integrity** runs on pushes and pull requests. It creates a clean copy from the source manifest, checks source hashes, rights coverage, document identities and the unchanged scientific baseline, and executes package and calibration-selection tests. This job does not claim a complete model reproduction.
2. **Complete reproduction** runs when manually requested with `complete=true`. It uses `ci/run_ci.py`, builds the pinned Docker environment, acquires the exact original survey files, creates a clean source copy, executes the complete study offline and runs all tests. A fresh provider download must match the frozen hashes. A missing or unavailable provider file stops the job and is not recorded as scientific PASS.

For the same complete process locally, provide the original files outside the package:

```powershell
python ci/run_ci.py --workdir 'D:\replicacion\ci-2.0.0' --raw-root 'D:\replicacion\encuestas'
```

The work directory must be new. If `--raw-root` is omitted, originals are downloaded from the providers. `CI_RESULT.json` identifies the execution environment, source-manifest hash and raw-input acquisition mode. On 2026-11-15, the CASEN endpoint returned a server error from the local access check; the exact retained originals remain necessary when the provider is unavailable.

The reference scientific run r9 passed locally and on GitHub Actions: 39 stages, 77 core files, 88 extension files, four survey tables, 164 document cells, an exact figure and 151 tests. Final release verification is supplied separately with the source-manifest hash so that later documentation does not create circular source checksums. See `release/VERIFICATION.md`.

The workflow permits a frozen-input transport tag only in a private repository, with an explicit repository-visibility guard. It verifies both original hashes before execution. Public repositories cannot use that transport mode. The temporary private transport is removed after evidence retrieval. Original records are excluded from all uploaded verification artifacts.

Actions are pinned to commits. The scientific container runs without network access, with original files mounted read-only. `ci/check_numeric_runtime.py` validates NumPy 2.5.1 with `NPY_DISABLE_CPU_FEATURES=X86_V4`; this retains the exact numerical checks across processors. `NUMERIC_RUNTIME.json` records the effective configuration. No numerical tolerance is relaxed.
