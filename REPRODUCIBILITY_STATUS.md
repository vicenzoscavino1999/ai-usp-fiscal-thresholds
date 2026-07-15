# Reproducibility Status

The public replication package is complete for the registered public scope. The
canonical command is `make reproduce-public`; detailed instructions are in
`REPRODUCING.md`, and the release verification matrix is in `VALIDATION.md`.

## Frozen Objects

- Official baseline snapshot: `v1.0.1-official-4c`.
- H* projection snapshot: `v1.1.0-official-4c`.
- Deterministic parameter set: `baseline-official-v2`.
- Uncertainty and diagnostics parameter set: `baseline-official-v3`.
- Primary specification SHA-256:
  `0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81`.
- Protected-file contract: 16 files plus five coherent amendment registries.

The H* snapshot extends the projection horizon required for the registered H*
calculation; it does not recalibrate or replace the official baseline snapshot.

## Verification Coverage

| Component | Status | Verification |
| --- | --- | --- |
| Deterministic baseline and inversions | Complete | Canonical-key reference comparison |
| Monte Carlo and convergence | Complete | Registered tolerances and seeded determinism tests |
| Diagnostics and robustness | Complete | Reference schemas, qualitative contracts and rank-change checks |
| H* extension | Complete | Result, manual-check and amendment-registry reference files |
| omega-I reporting | Complete | In-memory ranking recomputation |
| LS-raw extension | Complete | Parameter chain and 480-cell comparison |
| CASEN GMI extension | Complete | Validation, costs, parameter set and class comparison |
| Publication tables | Complete | Byte-idempotent designed reexport |
| ENAHO GMI extension | Optional restricted supplement | Requires separately obtained row-level input |

## Public and Restricted Boundary

The public archive contains all redistributable frozen inputs needed for the
baseline, H*, LS-raw and CASEN paths. ENAHO row-level microdata remain outside
the archive; the package includes their metadata, retrieval code, registered
hashes and aggregate outputs.

No external download is required for `make reproduce-public`.
