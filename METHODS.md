# Methods

This repository implements an explicit accounting-fiscal threshold model for
testing whether AI-induced effective fiscal space can cover social-protection
costs in Peru, Chile, Colombia, and Mexico. It is not a causal forecast. It is a
registered simulation and falsification package: observed anchors, approved
calibration values, deterministic mechanics, Monte Carlo uncertainty, and
diagnostics are kept as separate artifacts with hashes.

## 1. Explicit Engine, Not a Black Box

The model mechanics live in `src/ai_usp/`. Runners under `scripts/` only load
data, choose registered parameters, orchestrate grids, and write provenance.
This split is deliberate: anti-double-counting conventions, floors, debt
guardrails, historical classes, and threshold inversions are testable functions
rather than spreadsheet-side transformations.

## 2. AI Shock Conversion

Raw AI shocks never enter fiscal equations directly. Each scenario converts
`phi_raw` to nominal GDP-equivalent `phi_Y_nominal` through the registered
bridge `kappa` and `pi_AI_Y`. Low/mid are TFP-style inputs, high uses the paper's
LP-to-Y bridge, and stress is a GDP-equivalent benchmark. The high label is
source-disciplined, not guaranteed to be monotone in `phi_Y_nominal`.

## 3. Domestic Translation

AI gains are translated domestically through productive exposure and adoption:

```text
S_NDC = tilde(E_prod)^beta * tilde(q_prod)^gamma
T = min(1, S_NDC / S_frontier)
g_AI_level = (1 + phi_Y_nominal * T)^H - 1
```

`S_frontier` uses the OECD-Eurostat benchmark set. `E_prod_frontier` is anchored
to ILO Working Paper 96 high-income augmentation potential, with upper support
disciplined by ILO Working Paper 140. Domestic LAC `E_prod` is a common fallback,
so cross-country exposure differences are not identified in the official run.

## 4. Frozen Trajectory and Endpoint Growth

The official endpoint is 2034 from a 2024 anchor, so `H=10`. The frozen-anchor
convention keeps `q_prod_t0 = q_use_target_adj` and holds the anchor value in the
deterministic baseline. The compound expression above is exact for this endpoint
convention because the annual translated increment is constant inside the
cell. Bias from the frozen convention is reported separately: it avoids
unregistered transition dynamics but can understate diffusion in favorable
trajectories or omit future frictions.

## 5. Fiscal Channel Weights

The channel mode is frozen-weight, channel-based. Labor-share movement is
computed from automation, augmentation, task substitution/complementarity, and
skill/task terms. Capital is the non-labor residual adjusted by taxable-base and
domestic-capture shares. Consumption is derived from disposable labor, capital,
and rent flows, marginal propensities to consume, import leakage, and exempt
consumption. The resulting weights are `omega_L`, `omega_K_net`, and `omega_C`.

`lambda_AI` is the subset of AI gains assigned to concentrated AI rents. The
rent channel is inactive in `r0-r2`; claims depending on `r3-r4` rent capture are
conditional or stress-labelled.

## 6. Endpoint Policy Costs

Costs are gross GDP shares at the 2034 endpoint. Demographic policies use WPP
age/sex projections; Colombia's pension rule uses sex-specific ages and the
age-80 benefit schedule. GMI has ideal and loaded aggregate versions. The ideal
version is a lower-bound diagnostic and cannot alone support a ranking claim;
loaded GMI is the mandatory companion.

## 7. Channel-Based vs Historical Reduced Form

The primary fiscal conversion is channel-based. Historical reduced-form MFC is
only a labelled robustness/diagnostic mode. The two are never summed. Tests and
schemas enforce this exclusion.

## 8. Historical Fiscal Capture

Historical capture distributions retain positive and negative components. Main
plausibility classes compare realized or required `MFCgross` against positive
historical percentiles P50/P75/P90. Monte Carlo reduced-form diagnostics can use
the unconditional mixture with a negative-capture probability.

## 9. Debt Guardrail

Debt consistency is separate from the gross feasibility ratio. Inversions are
reported for `requirement_basis=baseline` and `debt_consistent`, with the debt
requirement adding the stabilizing-primary-balance shortfall where relevant.

## 10. Monte Carlo

Author-approved `bounded_PERT` parameters are sampled from scaled beta draws
with lambda=4. Derived quantities such as `q_prod`, `T`, and `g_AI_level` are
recomputed per draw; they are not sampled directly. The primary classification
uses only `MC_independent_baseline` with `prob_basis=all_draw`. Correlated modes
are robustness diagnostics. Rank dependence is implemented by factor and
pairwise structures while preserving marginal percentiles.

## 11. Final Tolerances

| Tier | Scope | Tolerance | Calibration evidence |
| --- | --- | --- | --- |
| A | deterministic floats | atol `1e-10`, rtol `1e-8`; exact `g_ai_level`, `xi`, endpoint | deterministic reruns must be byte-stable up to floating formatting |
| B | Monte Carlo probabilities and percentiles | atol `0.02`, rtol `1e-8`; exact draw counts | seed probes at M=5000 had max absolute probability differences `0.0186` and `0.0183029522`; tolerance set at 0.02 |
| C | snapshot/hash checks | exact hash match | `verify.py` compares dataset manifest hash and archived reference hash |
| D | diagnostics | qualitative verdict and rank-change checks | schemas require diagnostic tables; final claims use pass/fail plus documented limitations |

## 12. Reproducibility Tiers

Tier A covers deterministic baseline, scenario-regime grid, threshold inversion,
historical plausibility, and preliminary classification. Tier B adds Monte
Carlo, convergence, correlated dependence checks, and final classification.
Tier C is the frozen snapshot/hash layer. Tier D covers placebo ICT, negative
controls, leave-one-source-out, channel ablations, informal-adoption ablation,
and Sobol/Saltelli sensitivity.

## 13. Run Modes

`make reproduce-deterministic` runs Tier A. `make reproduce-full` runs Tier A+B,
deterministic robustness, Tier D diagnostics, Phase B closure exports, and
`verify.py`. `make run-diagnostics` runs diagnostics and closure exports only.
`build-from-frozen-dataset` rebuilds anchors from the frozen snapshot and is not
a paper-results shortcut.

## 14. Data and Licenses

The package versions manifests, metadata, derived audit outputs, and reference
tables. It does not redistribute all raw data. GRD is cited as UNU-WIDER GRD
2025. Ookla raw data is not redistributed because the source is CC BY-NC-SA 4.0;
the derived gap index is archived with attribution and license notes. Restricted
microdata and national-source manual files remain author-held.

## 15. Informality Mechanisms

Informality enters adoption through `q_bar` and logit inversion, and fiscal
capacity through observed effective tax rates. These are not symmetric
mechanisms. The Phase B adoption-only ablation removes `I` from `q_bar` and the
logit but leaves fiscal rates intact. Result: `max_abs_delta_v = 0` and zero
crossing changes, because frozen `q_use_target` and the derived intercept `mu`
hold `q_prod` fixed and `q_bar` is not binding. The fiscal side is not separable
without a counterfactual tax-rate model, so H3 is final `MIXED`, not confirmed.

## 16. GMI Versions and Ranking Rule

`GMI_ideal_aggregate` is the baseline lower-bound row, and
`GMI_loaded_aggregate` is the required companion. Any ranking must show both.
Ideal GMI can make a cost gradient look more favorable than an implementable
program; the bias ledger labels that direction explicitly.

## 17. Erosion Companion

For `r>=1`, behavioral erosion companions apply channel-specific
`epsilon_ero_j` with the restriction `epsilon_ero_j * tau_j < 1`. `r0` has
epsilon zero. Companions are reported so that regime-dependent feasibility is
not mistaken for a purely mechanical tax-rate increase.

## Core References

- Gmyrek, P., Berg, J., and Bescond, D. 2023. "Generative AI and jobs: A global
  analysis of potential effects on job quantity and quality." ILO Working Paper
  96.
- Gmyrek, P. et al. 2025. "Generative AI and Jobs: A Refined Global Index of
  Occupational Exposure." ILO Working Paper 140.
- International Monetary Fund. "AI Preparedness Index: Methodology Note."
- UNU-WIDER. 2025. "UNU-WIDER Government Revenue Dataset. Version 2025."
  https://doi.org/10.35188/UNU-WIDER/GRD-2025
- Gmyrek, P., Winkler, H., and Garganta, S. 2024. "Buffer or Bottleneck?
  Employment Exposure to Generative AI and the Digital Divide in Latin America."
  ILO Working Paper 121 / World Bank.
- Saisana, Saltelli, and Tarantola. 2005. "Uncertainty and sensitivity analysis
  techniques as tools for the quality assessment of composite indicators."
  JRSS-A 168(2).
- Hoyland, Moene, and Willumsen. 2012. "The tyranny of international index
  rankings." Journal of Development Economics 97(1).
- Gasparini and Tornarolli. 2007. CEDLAS Working Paper 46; 2009 follow-up on
  informality definitions in Latin America.
