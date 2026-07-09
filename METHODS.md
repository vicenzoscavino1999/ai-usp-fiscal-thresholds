# Methods

This package implements an accounting-simulation framework for asking whether
AI-induced fiscal space could cover universal or categorical social protection
costs in four Latin American countries. The Phase A implementation is not a
causal forecast. It is a disciplined threshold exercise: observed anchors and
registered parameter values are combined through pre-specified equations, then
checked against historical fiscal-capture plausibility and debt guardrails.

## Primary Mode: Channel-Based Frozen Weights

The official Phase A run uses the channel-based fiscal-conversion mode with
frozen 2024 anchors. For each country-policy-scenario-regime cell, the engine
computes:

1. an AI shock converted into nominal GDP-equivalent terms;
2. an adoption and productive-exposure translation factor;
3. an endpoint AI GDP level gain;
4. labor, capital, consumption, and AI-rent fiscal capture weights;
5. gross and effective fiscal space;
6. feasibility ratios against gross policy costs; and
7. threshold inversions and historical plausibility classes.

The frozen-weight convention means that the country anchor year is 2024 and the
endpoint is 2034. Structural quantities that are not explicitly in the scenario
path remain anchored to the declared 2024 calibration. This is conservative for
implementation reproducibility: the run avoids adding an unobserved transition
model for institutions, employment structure, or tax administration. It can be
favorable or unfavorable depending on the channel. In the documentation and
tables, the main declared favorable direction is that some future frictions or
policy erosion may be understated if they would worsen relative to the 2024
anchor.

## Endpoint Growth Convention

The ten-year endpoint gain is

```text
g_AI_level = (1 + phi_Y_nominal * T)^H - 1
```

with `H = 10` for 2024 to 2034. This is exact for the model's discrete
endpoint convention because `phi_Y_nominal * T` is the annual nominal
GDP-equivalent AI increment after domestic translation. The expression is the
compound level gain over the horizon, not an additive approximation. Using the
compound formula avoids a small downward approximation error when the annual
increment is positive. The remaining bias is therefore not from compounding, but
from the endpoint simplification: the package does not model year-by-year
feedback between growth, tax bases, eligibility, and political implementation.

## Productive Translation and Frontier Calibration

Domestic AI translation is bilinear in productive exposure and adoption:

```text
S_NDC = tilde(E_prod)^beta * tilde(q_prod)^gamma
T = min(1, S_NDC / S_frontier)
```

where `tilde(x) = epsilon + (1 - epsilon) x`. The floor is numerical and
prevents undefined operations at zero; the zero corner remains non-crossing by
construction. In the official frozen trajectory, `q_prod_t0 = q_use_target_adj`
and the intercept `mu_t0` is derived by logit inversion rather than freely
estimated. The primitive registered for adoption is `q_use_target`.

`S_frontier` is calibrated from the OECD-Eurostat benchmark set used in the
official run. The frontier exposure parameter `E_prod_frontier` is anchored to
ILO Working Paper 96 (Gmyrek, Berg and Bescond, 2023), which reports high-income
augmentation potential; the upper support is disciplined by ILO Working Paper
140 (2025), which refines the global occupational exposure index. This keeps
the numerator and denominator of `T` in the same measurement family as the LAC
exposure anchor used for domestic `E_prod`.

The LAC exposure fallback follows the World Bank-ILO evidence for Latin America
and the Caribbean, especially the finding that a limited share of jobs is at
automation risk while a larger share can be augmented if digital access is
available. In the official four-country run, `E_prod` is common across LAC
countries and marked as a fallback. Consequently, cross-country variation in
`T` comes from preparedness, adoption, informality, and the digital gap rather
than from measured country-specific occupational exposure.

## Fiscal Capture Weights

The engine constructs endpoint weights for labor, capital, and consumption
using the 2024 labor share and registered channel parameters. The labor-share
transition is logistic:

```text
LS_prime = logistic(logit(LS) + lambda_LS * pressure)
```

where pressure combines automation exposure, augmentation exposure, task
substitution, task complementarity, and residual skill/task terms. The endpoint
labor increment is `Delta_W = LS_prime * (1 + g_AI_level) - LS`. The residual
non-labor increment is `Delta_NLS = g_AI_level - Delta_W`. The taxable capital
base is a share of that residual, then reduced by domestic capture and ordinary
profit shifting. Consumption capture is derived from disposable labor, capital,
and residual-income flows, marginal propensities to consume, import leakage,
and the exempt consumption share. The resulting weights are:

```text
omega_L = Delta_W / g_AI_level
omega_K = Delta_capital_domestic / g_AI_level
omega_C = Delta_consumption_taxable / g_AI_level
```

When `g_AI_level <= 0`, all weights are zero and the draw or cell cannot cross.
This prevents the bilinear zero corner from creating an artificial positive
feasibility ratio.

## Regimes, AI Rents, and Lambda_AI

Fiscal regimes `r0` to `r4` modify effective tax rates, base broadening,
leakage, and AI-rent capture according to the registered parameter set.
The baseline `r0` has the AI-rent channel off. In the official calibration,
`lambda_AI` is interpreted as the subset of AI gains accruing to concentrated
AI rents that could in principle be taxed by an AI-rent instrument. This is
plausible because a material share of frontier AI value may accrue to model,
cloud, data, and platform providers rather than broad domestic labor income.
It is also uncertain. Therefore, the channel is inactive in `r0-r2`, and any
result that depends on active rent capture in `r3-r4` is labelled as conditional
or stress-related rather than used to claim robust feasibility.

## Digital Gap from Excluded Indicators

The official Gap is not residualized against the AI Preparedness Index. It is
constructed from indicators verified as excluded from the IMF AIPI component
list: ITU mobile/LTE coverage and Ookla fixed/mobile download speed. The
implementation records the exclusion check against the IMF AIPI note and sets
`aipi_overlap_flag = FALSE` in the source map. The gap index is a normalized
connectivity shortfall; it enters adoption ceilings and adoption friction, not
the fiscal-conversion equation directly.

This separation matters for double-counting. AIPI can discipline preparedness
and adoption, while the Gap captures a distinct digital-infrastructure
constraint. The pilot diagnostic with `Gap = 0` is retained only as historical
context and is not the official baseline.

## Policy Costs and Endpoint Convention

Policy costs are gross GDP shares at the 2034 endpoint. Pension and other
population-scaled policies use WPP age/sex projections where required. GMI uses
two versions: `GMI_ideal_aggregate` as the baseline lower-bound cost and
`GMI_loaded_aggregate` as the required companion for rankings. The ideal version
assumes perfect identification and no implementation load; it cannot alone
support an operational ranking claim.

## Historical Plausibility

Historical fiscal-capture distributions are built from frozen revenue and GDP
anchors. Positive historical MFC percentiles (`P50`, `P75`, `P90`) classify
required or realized fiscal capture as ordinary, moderate, demanding, or
outside support. Negative-capture shares are retained for historical reduced
form Monte Carlo diagnostics. GRD 2025 is included as a contrast source for
government revenue concepts; the official central/general comparison aligns
social-contribution treatment before interpretation.

## Snapshot and Hash Policy

Raw and intermediate data live outside Git under ignored folders. The versioned
package stores snapshot manifests, source metadata, reference outputs, schemas,
and hashes. The Phase A official dataset is `v1.0.1-official-4c`; it differs
from `v1.0.0-official-4c` only by registered GRD incorporation. `verify.py`
checks the current result files against `reproducibility/reference/`, validates
schemas, refuses missing/extra rows or columns, and verifies the frozen snapshot
manifest hash.

## Seed Policy

Randomness is centralized in `reproducibility/config/rng_policy.yaml`. Historical
bootstrap and Monte Carlo seeds are fixed. Monte Carlo sub-streams use
`numpy.random.SeedSequence.spawn` and PCG64 so cell-level draws are reproducible.
The Phase A official deterministic run does not consume Monte Carlo randomness;
Monte Carlo artifacts are archived for audit continuity and Phase B development.

## Core References

- Gmyrek, P., Berg, J., and Bescond, D. 2023. "Generative AI and jobs: A global
  analysis of potential effects on job quantity and quality." ILO Working Paper
  96. https://www.ilo.org/publications/generative-ai-and-jobs-global-analysis-potential-effects-job-quantity-and
- Gmyrek, P. et al. 2025. "Generative AI and Jobs: A Refined Global Index of
  Occupational Exposure." ILO Working Paper 140.
  https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure
- International Monetary Fund. "AI Preparedness Index: Methodology Note."
  https://www.imf.org/external/datamapper/AIPINote.pdf
- UNU-WIDER. 2025. "UNU-WIDER Government Revenue Dataset. Version 2025."
  https://doi.org/10.35188/UNU-WIDER/GRD-2025
- Gmyrek, P., Winkler, H., and Garganta, S. 2024. "Buffer or Bottleneck?
  Employment Exposure to Generative AI and the Digital Divide in Latin America."
  ILO Working Paper 121 / World Bank. https://doi.org/10.54394/TFZY768101
