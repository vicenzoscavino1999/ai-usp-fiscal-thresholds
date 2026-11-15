# Benchmark population correction r9

The 2024 adoption benchmark now selects Eurostat E_AI_TANY, GE10, C10-S951_X_K, PC_ENT and annual frequency. Each of the same 24 registered economies contributes one observation. The prior extractor selected country and year but averaged different indicators, size classes and denominators. Its 12,737 rows did not represent the declared enterprise adoption population.

The country set, anchor year, frozen source files, scenario definitions, equations, seeds and numeric tolerances are retained. Missing or duplicate country observations, invalid percentages and ambiguous AIPI anchors are rejected. AIPI is selected uniquely at the latest year up to 2024; the frozen source remains 2023. Adoption and AIPI means give equal weight to each country. They are calibration proxies, not observations of Latin American adoption or a weighted EU aggregate.

Benchmark rows are sorted by country during construction, database extraction and use. Scalar means use compensated summation (`math.fsum`). The transformation retains its arithmetic-mean definition. Both the current fiscal model and the legacy comparison use the same corrected population, so the decomposition continues to isolate accounting changes.

Unit checks exercise missing dimensions, wrong-population distractors, duplicate and invalid cells, the frozen country observations, and exact invariance of all country/scenario draw outputs under twenty benchmark permutations. The latter covers constant and varying smoothing/exponent arrays in both fiscal runners.

The impact run retained the r8 references until calibration, draw hashes, the 6.4 million matched evaluations, 49,896 financing paths and current document cells had been checked independently. Reconciliation updates 117 of 165 registered reference artifacts and preserves 48. The frontier schema now requires 24 rows with a unique country/year key; numerical tolerances are unchanged.

The four central non-stress B2 crossings remain. For Chile moderate r4 ideal GMI, annual B2 still begins in year 9, while recovery without replacement moves from year 14 to year 15. The matched Chile moderate r0 B2 frequency is 26.438 percent, versus 27.174 under r8. The PIT allocation extremes of zero and 30 percent preserve all 480 central classifications; assigning all PIT to non-labour income removes one moderate r1 crossing. Updated text, tables and the transition figure report these results.

Generation guards compare independently reconstructed accounting endpoints and coverage identities instead of embedding the previous calibration's numerical outcomes. The historical reference files retain the before/after comparison. This source candidate requires a fresh complete local and hosted reproduction; runtime reports provide that evidence separately from public deposit and editorial submission.

Source definition: https://ec.europa.eu/eurostat/web/products-eurostat-news/w/ddn-20250123-3

## Numeric environment

A paired local/hosted diagnostic isolated NumPy X86_V4 dispatch as the cause of last-bit differences: default hosted calculation reproduced the failing capture hashes, while disabling X86_V4 made all twelve growth/capture arrays (three seeds, four arrays per seed) byte-identical to the local references. The pinned image and reproduction entry points now set NPY_DISABLE_CPU_FEATURES=X86_V4 before import. CI records and checks the effective dispatch configuration. No reference output, scientific equation, exact-hash requirement or numeric tolerance changes for this environment correction.
