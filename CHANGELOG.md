# Version 2.0.0 — 2026-11-15

This major version corresponds to the revised JPM manuscript. It extends the version 1.1.1 replication scope to the fiscal-receipt channel model, recurring-cost frontiers, transition financing, matched reconciliation and sensitivity analyses, and independently reconstructed ENAHO/CASEN cost comparisons. It includes the current Word manuscript and technical supplement, a pinned Docker environment, exact source inventories and a complete reproduction runner.

The scientific baseline is r9, commit `ec433684d0aeed36e99322d45c9752fdfcb7c4a1`, verified locally and in GitHub Actions. The national informal-employment selection and the comparable 24-country Eurostat enterprise-adoption benchmark are documented in `CALIBRATION_REVISION_R8.md` and `BENCHMARK_REVISION_R9.md`. Those corrections preserve four of 360 central non-disruptive B2 coverage cases. Chile's illustrative moderate r4 annual coverage occurs in year 9 and cumulative recovery in year 15 without replacement. These are conditional scenario results, not forecasts.

Packaging for this release changes the availability statements and publication material; it does not change equations, input snapshots, seeds, scientific reference outputs, numerical tolerances, tables or the figure relative to r9. The NumPy runtime restriction introduced in r9 is retained to make exact derived hashes portable across processors.

The original survey records remain excluded. Acquisition checks reject provider files that differ from the recorded version. A provider-access failure is separate from a numerical reproduction failure. Final verification reports identify whether original files were downloaded afresh or supplied from the frozen archive.

Earlier deposits remain available through the concept DOI. Version 1.1.1 is preserved at https://doi.org/10.5281/zenodo.21381145; this version is identified by https://doi.org/10.5281/zenodo.24257720.
