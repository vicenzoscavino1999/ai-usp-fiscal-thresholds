# Calibration revision r8: national informality

The national informality anchor now selects ILOSTAT indicator `EMP_NIFL_SEX_AGE_RT`, both sexes (`SEX_T`), and ages 15 years and above (`AGE_AGGREGATE_YGE15`) before selecting the latest observation up to 2024. All four frozen national observations are from 2024. Missing cells, invalid values and duplicate observations in the selected year stop the build.

The r7 selector did not restrict age. Its last-row selection among observations sharing a year depended on row order. The r7 reference calibration used ages 40–44 for Peru and Mexico, while Chile and Colombia already matched ages 15+. This revision corrects that population mismatch using the same frozen source file; it does not replace the raw data.

| Country | r7 reference informal employment (%) | r8, both sexes aged 15+ (%) |
| --- | ---: | ---: |
| Peru | 67.468 | 71.373 |
| Mexico | 50.592 | 56.407 |
| Chile | 27.458 | 27.458 |
| Colombia | 56.143 | 56.143 |

## Transmission to the model

For Peru and Mexico, the two informality anchors, the adoption ceiling and the derived logit intercept change. Eight central parameter values and twelve support endpoints change in the 457-row parameter register. The central ceiling is `q_bar = 1 - 0.5 I - 0.5 Gap`; the logit intercept is recalibrated to the same registered adoption target. Peru's ceiling changes from 0.5301193837172034 to 0.5105943837172033, and Mexico's from 0.5714239342683678 to 0.5423489342683678. Their corresponding intercepts change from −1.3541658538070795 to −1.286978815620956 and from −1.4300813603093334 to −1.334455836409645.

The registered adoption targets remain below the revised ceilings throughout the full rectangular primitive supports. At the adverse support endpoints, the minimum margin between the ceiling, less epsilon, and the maximum target is 0.0545791494 for Peru and 0.0902315943 for Mexico. It is also positive for Chile and Colombia. Thus the clipping operation never changes productive adoption in these registered scenarios. The corrected informality draws have the same rank ordering; their level shifts are 0.03905 and 0.05815, up to floating-point precision.

One operational inverse changes its feasibility classification: Mexico, disruptive stress, r0, pension, B1, coefficient vertex v2, recurring author costs. Required one-step adoption is approximately 0.5593956765, above the revised ceiling less epsilon, 0.5423479343. Its `q_use_within_ceiling` flag changes from true to false. This is a substantive calibration correction, not a numerical tolerance adjustment.

## Reconstructed results and reference reconciliation

The impact reconstruction retained the r7 reference outputs during all calculations. Of 77 core comparisons, 74 remained within their existing contracts; three differed as expected: the parameter register, forty country/scenario/regime ceiling entries, and the single inverse flag. Of 88 extension comparisons, 83 remained within their existing contracts. The five affected extension artifacts contain the corrected informality and ceiling values in the H3 adoption comparison, three independent-draw hash inventories, and the corresponding marginal-preservation hashes.

Direct calculations checked the new central values and supports. An independent PERT and seed-stream reconstruction matched the old and new informality vectors and their rank-preservation hashes for all four countries and three seeds. Only these eight explained reference artifacts were updated. Runtime durations retain their existing exclusions; numerical tolerances, comparison schemas, seeds and frozen raw snapshots are unchanged.

The fiscal frontiers, financing paths, Monte Carlo outcome frequencies, convergence and dependence summaries remain within the existing contracts. The 164 document cells and Figure 1 retain their values. The manuscript is unchanged. The supplement adds the exact informality population definition and remains 16 pages in Microsoft Word. ENAHO/CASEN were reconstructed separately from their original files and preserve the reported cost differences of −7.734% and +0.387%.

These comparisons establish the scope of the calibration correction. A formal reproduction of this candidate still requires a fresh run ending in `run_logs/COMPARISON_COMPLETE.json` with `status: PASS`, followed by the full test suite. The impact run itself correctly reported differences against r7 and is not relabelled as PASS. Local and hosted evidence are recorded by the CI runner; publication and editorial submission remain separate steps.
