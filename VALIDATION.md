# Release Validation

This document records the release-level verification of the public replication
package `v1.1.1-rc1`. It reports the final supported state only; reproduction
instructions are maintained separately in `REPRODUCING.md`.

## Validation Environment

- Source: a fresh extraction of the curated public ZIP.
- Runtime: Docker using `python:3.12.4-slim` pinned by digest.
- Dependencies: installed from `requirements-lock.txt` with
  `pip install --require-hashes`.
- Inputs: only files contained in the public ZIP.
- Network access: not required by the reproduction command.
- Runtime directories: empty `db/`, `results/` and `figures/` at start.

## Results

| Check | Result |
| --- | --- |
| Public bundle construction repeated twice | PASS; identical archive SHA-256 |
| Bundle manifest and archive safety | PASS; no unsafe paths, symlinks or executable payloads |
| Dependency lock | PASS; canonical LF SHA-256 `cb03f694292ebefe612f475776b359505bd3e63b269879d285ecd66e84e6bf18` |
| H* snapshot manifest | PASS; byte-level SHA-256 `b618e22af1847eb3a1a1a87ceb1d3194b4ec552335b3bc41e7c915f9157d4de1` |
| Pristine protected-file verification | PASS; 16 protected files and five amendment registries |
| Primary specification | PASS; SHA-256 `0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81` |
| Clean container test suite | PASS; 43 tests |
| `make reproduce-public` | PASS |
| Versioned result comparison | PASS; 30 of 30 files |
| Public extension verification | PASS; four public extension groups, 17 files, 242 stable columns and 6,790 numeric comparisons |
| Publication-table reexport | PASS; eight files byte-idempotent |
| ENAHO GMI verification | Expected skip; restricted row-level input not included |
| Non-H* numerical comparison | Exact equality across 597,683 compared values in 27 CSV files |
| H* outputs | PASS; 4,800 result rows and three manual-check rows |

The generated Monte Carlo table includes `prob_h_star_le_10` and
`prob_h_star_le_25`. The extended WPP parquet matches its registered manifest
hash:

`4282ee11722a20c3cef6c76b807e5c096b229eea9c0a2a3f22264a8361c397de`.

## Interpretation

The PASS result applies to the complete redistributable package. The separately
obtainable ENAHO extension is not required for the published public-path result
and is reported explicitly as outside the archive's redistribution scope.

The ZIP-level SHA-256 is distributed alongside the archive because an archive
cannot embed its own final checksum without changing that checksum.
