[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Culture = [System.Globalization.CultureInfo]::InvariantCulture
$CleanRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $CleanRoot '..\..')).Path
$ReportsRoot = Join-Path $RepoRoot 'reports'
$TablesRoot = Join-Path $CleanRoot 'tables'
$FiguresRoot = Join-Path $CleanRoot 'figures'
$LedgerPath = Join-Path $CleanRoot 'technical\numeric_ledger.csv'

New-Item -ItemType Directory -Force -Path $TablesRoot, $FiguresRoot | Out-Null

function Import-ReportCsv {
  param([Parameter(Mandatory)][string]$RelativePath)
  $path = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing frozen input: $RelativePath"
  }
  return @(Import-Csv -LiteralPath $path)
}

function Get-UniqueRow {
  param(
    [Parameter(Mandatory)][object[]]$Rows,
    [Parameter(Mandatory)][scriptblock]$Filter,
    [Parameter(Mandatory)][string]$Description
  )
  $hits = @($Rows | Where-Object $Filter)
  if ($hits.Count -ne 1) {
    throw "Expected one row for $Description; found $($hits.Count)."
  }
  return $hits[0]
}

function Format-Number {
  param(
    [Parameter(Mandatory)][double]$Value,
    [string]$Pattern = '0.00'
  )
  return $Value.ToString($Pattern, $Culture)
}

function Write-Utf8File {
  param(
    [Parameter(Mandatory)][string]$Path,
    [Parameter(Mandatory)][string[]]$Lines
  )
  $encoding = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText(
    $Path,
    (($Lines -join [Environment]::NewLine) + [Environment]::NewLine),
    $encoding
  )
}

$LedgerRows = [System.Collections.Generic.List[object]]::new()
function Add-LedgerRow {
  param(
    [Parameter(Mandatory)][string]$ClaimId,
    [Parameter(Mandatory)][string]$ManuscriptValue,
    [Parameter(Mandatory)][string]$SourceCsv,
    [Parameter(Mandatory)][string]$Filters,
    [Parameter(Mandatory)][string]$SourceColumns,
    [Parameter(Mandatory)][string]$Notes
  )
  $LedgerRows.Add([pscustomobject][ordered]@{
      section = '5'
      claim_id = $ClaimId
      manuscript_value = $ManuscriptValue
      source_csv = $SourceCsv
      filters = $Filters
      source_columns = $SourceColumns
      verification_status = 'verified'
      notes = $Notes
    }) | Out-Null
}

# Freeze checks: this script formats published outputs; it never runs the model.
$specPath = Join-Path $RepoRoot '02_ESD_AI_USP_v6.md'
$specExpected = '0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81'
$specActual = (Get-FileHash -Algorithm SHA256 -LiteralPath $specPath).Hash.ToLowerInvariant()
if ($specActual -ne $specExpected) {
  throw "Frozen specification hash mismatch: $specActual"
}

$Costs = Import-ReportCsv 'reports\paper_tables\table2_policy_costs.csv'
$VGrid = Import-ReportCsv 'reports\paper_tables\table4_vgross_baseline.csv'
$ThresholdCompact = Import-ReportCsv 'reports\paper_tables\table5_threshold_inversion.csv'
$ThresholdFull = Import-ReportCsv 'reports\threshold_inversion_result_baseline-official-v2.csv'
$MonteCarlo = Import-ReportCsv 'reports\monte_carlo_result_baseline-official-v3.csv'
$HStar = Import-ReportCsv 'reports\h_star_result_baseline-official-v3.csv'
$Placebo = Import-ReportCsv 'reports\diagnostic_placebo_ict_result_baseline-official-v3.csv'
$NegativeControl = Import-ReportCsv 'reports\diagnostic_negative_control_result_baseline-official-v3.csv'
$ChannelAblation = Import-ReportCsv 'reports\diagnostic_channel_ablation_result_baseline-official-v3.csv'
$Loso = Import-ReportCsv 'reports\diagnostic_loso_result_baseline-official-v3.csv'
$ValueAssignments = Import-ReportCsv 'reports\value_assignment_table_baseline-official-v3.csv'
$PerMicro = Import-ReportCsv 'reports\gmimicro_cost_comparison_baseline-official-v3.csv'
$ChlMicro = Import-ReportCsv 'reports\gmimicro_chl_cost_comparison_baseline-official-v3.csv'

if ($Costs.Count -ne 24 -or $VGrid.Count -ne 480) {
  throw "Unexpected frozen table dimensions: costs=$($Costs.Count), V-grid=$($VGrid.Count)."
}

# The v3 compact threshold table is the frozen paper export of the xi=.10 cut.
# Its omitted translation and AI-rent fields are recovered from the matching
# official full inversion CSV only after a key-by-key equality check.
$ThresholdXi10 = @($ThresholdFull | Where-Object { $_.xi -eq '0.1' })
if ($ThresholdXi10.Count -ne 960 -or $ThresholdCompact.Count -ne 960) {
  throw "Unexpected xi=.10 inversion dimensions."
}
$thresholdIndex = @{}
foreach ($row in $ThresholdXi10) {
  $key = @($row.country_id, $row.policy_variant_id, $row.scenario_id,
    $row.regime_id, $row.requirement_basis) -join '|'
  if ($thresholdIndex.ContainsKey($key)) { throw "Duplicate threshold key: $key" }
  $thresholdIndex[$key] = $row
}
foreach ($row in $ThresholdCompact) {
  $key = @($row.country_id, $row.policy_variant_id, $row.scenario_id,
    $row.regime_id, $row.requirement_basis) -join '|'
  if (-not $thresholdIndex.ContainsKey($key)) { throw "Missing full threshold key: $key" }
  $full = $thresholdIndex[$key]
  if ([math]::Abs([double]$row.g_ai_required - [double]$full.g_ai_required) -gt 1e-12 -or
      [math]::Abs([double]$row.mfc_required_gross - [double]$full.mfc_required_gross) -gt 1e-12) {
    throw "Threshold mismatch at $key"
  }
}

# Reuse the already generated frozen figure, after checking its exact hashes.
$figureFiles = @(
  @{ Name = 'headline_feasibility.pdf'; Hash = '84bbdb44bd0a5989511e381f73b8ff2cd7c78d50406bd1ef056b296c472647d6' },
  @{ Name = 'headline_feasibility.png'; Hash = '45adcaaf69c0935d8464e1f8e0d7dfc01ce7a0997c2ae750d0e671cf4576f1ed' }
)
foreach ($figure in $figureFiles) {
  $source = Join-Path $RepoRoot ('figures\' + $figure.Name)
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
  if ($actual -ne $figure.Hash) { throw "Frozen figure hash mismatch: $($figure.Name)" }
  Copy-Item -LiteralPath $source -Destination (Join-Path $FiguresRoot $figure.Name) -Force
}

# Table 5.1: comparable policy costs.
$countryOrder = @('CHL', 'COL', 'MEX', 'PER')
$costRows = @(
  @{ Id = 'PEN'; Label = 'Social pension (PEN)' },
  @{ Id = 'MUT'; Label = 'Minimum universal transfer (MUT)' },
  @{ Id = 'GMI:GMI_ideal_aggregate'; Label = 'GMI, ideal targeting' },
  @{ Id = 'GMI:GMI_loaded_aggregate'; Label = 'GMI, loaded targeting' },
  @{ Id = 'PBI'; Label = 'Partial basic income (PBI)' },
  @{ Id = 'UBI'; Label = 'Full UBI benchmark' }
)
$costTex = [System.Collections.Generic.List[string]]::new()
$costTex.Add('\begin{table}[H]') | Out-Null
$costTex.Add('\centering') | Out-Null
$costTex.Add('\small') | Out-Null
$costTex.Add('\begin{singlespace}') | Out-Null
$costTex.Add('\caption{Comparable gross policy costs (percent of endpoint GDP)}') | Out-Null
$costTex.Add('\label{tab:costs_results_clean}') | Out-Null
$costTex.Add('\begin{tabular}{@{}lrrrr@{}}') | Out-Null
$costTex.Add('\toprule') | Out-Null
$costTex.Add('Instrument & Chile & Colombia & Mexico & Peru \\') | Out-Null
$costTex.Add('\midrule') | Out-Null
foreach ($definition in $costRows) {
  $values = [System.Collections.Generic.List[string]]::new()
  foreach ($country in $countryOrder) {
    $variant = $definition.Id
    $row = Get-UniqueRow $Costs {
      $_.country_id -eq $country -and $_.policy_variant_id -eq $variant
    } "cost $country/$variant"
    $display = Format-Number (100.0 * [double]$row.cost_gross_gdp)
    $values.Add($display) | Out-Null
    $claimVariant = ($variant -replace '[^A-Za-z0-9]+', '_').Trim('_')
    Add-LedgerRow "cost_${country}_${claimVariant}" "$display percent of GDP" `
      'reports/paper_tables/table2_policy_costs.csv' `
      "country_id=$country AND policy_variant_id=$variant" `
      'cost_gross_gdp;cost_net_gdp;endpoint_cost_rule' `
      "Table value is 100*cost_gross_gdp, rounded to two decimals; raw=$($row.cost_gross_gdp)."
  }
  $costTex.Add(($definition.Label + ' & ' + ($values -join ' & ') + ' \\')) | Out-Null
}
$costTex.Add('\bottomrule') | Out-Null
$costTex.Add('\end{tabular}') | Out-Null
$costTex.Add('\begin{minipage}{0.94\textwidth}\footnotesize') | Out-Null
$costTex.Add('\emph{Note:} GMI costs are fixed aggregate endpoint costs; demographic instruments use the fixed endpoint eligible-share rule. Gross and net columns coincide because the primary comparison credits no existing-spending offset.') | Out-Null
$costTex.Add('\end{minipage}') | Out-Null
$costTex.Add('\end{singlespace}') | Out-Null
$costTex.Add('\end{table}') | Out-Null
Write-Utf8File (Join-Path $TablesRoot '05_costs.tex') $costTex.ToArray()

# GMI micro-validation values used in the cost discussion.
$perPrimary = @($PerMicro | Where-Object { $_.primary_variant -eq 'True' })
$chlPrimary = @($ChlMicro | Where-Object { $_.primary_variant -eq 'True' })
if ($perPrimary.Count -ne 2 -or $chlPrimary.Count -ne 2) { throw 'Unexpected primary GMI micro rows.' }
$perDifference = [double]$perPrimary[0].difference_percent_vs_official
$chlDifference = [double]$chlPrimary[0].difference_percent_vs_official
Add-LedgerRow 'micro_validation_PER' '-7.73 percent relative to aggregate GMI cost' `
  'reports/gmimicro_cost_comparison_baseline-official-v3.csv' `
  'country_id=PER AND primary_variant=True' `
  'difference_percent_vs_official;cost_micro_gdp;cost_official_aggregate_gdp' `
  "Both ideal and loaded primary rows have the same percentage difference; raw=$perDifference."
Add-LedgerRow 'micro_validation_CHL' '+0.39 percent relative to aggregate GMI cost' `
  'reports/gmimicro_chl_cost_comparison_baseline-official-v3.csv' `
  'country_id=CHL AND primary_variant=True' `
  'difference_percent_vs_official;cost_micro_gdp;cost_official_aggregate_gdp' `
  "Both ideal and loaded primary rows have the same percentage difference; raw=$chlDifference."

# Heatmap ledger: all 96 printed r0 values map one-to-one to table4.
$heatmapRows = @($VGrid | Where-Object { $_.regime_id -eq 'r0' })
if ($heatmapRows.Count -ne 96) { throw "Expected 96 r0 heatmap cells; found $($heatmapRows.Count)." }
foreach ($row in $heatmapRows) {
  $raw = [double]$row.v_gross
  $display = if ([math]::Abs($raw) -lt 0.005) { '0.00' } else { Format-Number $raw }
  $variant = ($row.policy_variant_id -replace '[^A-Za-z0-9]+', '_').Trim('_')
  Add-LedgerRow "heatmap_r0_$($row.country_id)_${variant}_$($row.scenario_id)" $display `
    'reports/paper_tables/table4_vgross_baseline.csv' `
    "country_id=$($row.country_id) AND policy_variant_id=$($row.policy_variant_id) AND scenario_id=$($row.scenario_id) AND regime_id=r0" `
    'v_gross;crosses_v1;cell_result_class' `
    "Frozen figure prints v_gross to two decimals; raw=$($row.v_gross)."
}
Add-LedgerRow 'heatmap_categorical_boundaries' 'V<0; 0--0.5; 0.5--1; 1--1.10; V>=1.10' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'regime_id=r0; frozen display bins applied to v_gross' `
  'v_gross;crosses_v1' `
  'Categorical display boundaries are fixed in scripts/make_headline_figure.py; the black outline marks V>=1.'

# Table 5.2: deterministic outcomes and debt classes.
$moderate = @($VGrid | Where-Object { $_.scenario_id -in @('low', 'mid', 'high') })
$moderateCrosses = @($moderate | Where-Object { $_.crosses_v1 -eq 'True' })
if ($moderate.Count -ne 360 -or $moderateCrosses.Count -ne 0) {
  throw 'Moderate-support crossing invariant failed.'
}
$moderateMax = $moderate | Sort-Object { [double]$_.v_gross } -Descending | Select-Object -First 1
$chlIdealR0 = Get-UniqueRow $VGrid { $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_ideal_aggregate' -and $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r0' } 'CHL GMI ideal stress r0'
$chlLoadedR0 = Get-UniqueRow $VGrid { $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_loaded_aggregate' -and $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r0' } 'CHL GMI loaded stress r0'
$perPenStress = @($VGrid | Where-Object { $_.country_id -eq 'PER' -and $_.policy_variant_id -eq 'PEN' -and $_.scenario_id -eq 'stress' })
$colBest = $VGrid | Where-Object { $_.country_id -eq 'COL' } | Sort-Object { [double]$_.v_gross } -Descending | Select-Object -First 1
$mexBest = $VGrid | Where-Object { $_.country_id -eq 'MEX' } | Sort-Object { [double]$_.v_gross } -Descending | Select-Object -First 1
$perMin = ($perPenStress | Measure-Object -Property v_gross -Minimum).Minimum
$perMax = ($perPenStress | Measure-Object -Property v_gross -Maximum).Maximum

$detTex = [System.Collections.Generic.List[string]]::new()
$detTex.Add('\begin{table}[H]') | Out-Null
$detTex.Add('\centering') | Out-Null
$detTex.Add('\small') | Out-Null
$detTex.Add('\begin{singlespace}') | Out-Null
$detTex.Add('\caption{Selected deterministic outcomes and the debt guardrail}') | Out-Null
$detTex.Add('\label{tab:deterministic_results_clean}') | Out-Null
$detTex.Add('\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.31\textwidth}>{\raggedright\arraybackslash}p{0.16\textwidth}r >{\raggedright\arraybackslash}p{0.34\textwidth}@{}}') | Out-Null
$detTex.Add('\toprule') | Out-Null
$detTex.Add('Scope or cell & Reported regime & $V^{gross}$ & Result class \\') | Out-Null
$detTex.Add('\midrule') | Out-Null
$moderateMaxDisplay = Format-Number -Value ([double]$moderateMax.v_gross) -Pattern '0.000'
$chlIdealR0Display = Format-Number -Value ([double]$chlIdealR0.v_gross)
$chlLoadedR0Display = Format-Number -Value ([double]$chlLoadedR0.v_gross)
$perMinDisplay = Format-Number -Value ([double]$perMin)
$perMaxDisplay = Format-Number -Value ([double]$perMax)
$colBestDisplay = Format-Number -Value ([double]$colBest.v_gross)
$mexBestDisplay = Format-Number -Value ([double]$mexBest.v_gross)
$detTex.Add(('All low/mid/high cells & Best of 360 cells & {0} & No accounting crossing \\' -f $moderateMaxDisplay)) | Out-Null
$detTex.Add(('Chile, GMI ideal, stress & r0 & {0} & Feasible, including debt guardrail \\' -f $chlIdealR0Display)) | Out-Null
$detTex.Add(('Chile, GMI loaded, stress & r0 & {0} & Feasible, including debt guardrail \\' -f $chlLoadedR0Display)) | Out-Null
$detTex.Add(('Peru, social pension, stress & r0--r4 & {0}--{1} & Accounting crossing; debt guardrail fails \\' -f $perMinDisplay, $perMaxDisplay)) | Out-Null
$detTex.Add(('Colombia, best cell (PEN, stress) & r4 & {0} & No accounting crossing \\' -f $colBestDisplay)) | Out-Null
$detTex.Add(('Mexico, best cell (GMI ideal, stress) & r4 & {0} & No accounting crossing \\' -f $mexBestDisplay)) | Out-Null
$detTex.Add('\bottomrule') | Out-Null
$detTex.Add('\end{tabular}') | Out-Null
$detTex.Add('\begin{minipage}{0.94\textwidth}\footnotesize') | Out-Null
$detTex.Add('\emph{Note:} Accounting crossings use the structural threshold $V\geq1$; Figure~\ref{fig:headline_feasibility_clean} separately identifies cells that also reach $V\geq1.10$. Stress is a diagnostic scenario, not a forecast.') | Out-Null
$detTex.Add('\end{minipage}') | Out-Null
$detTex.Add('\end{singlespace}') | Out-Null
$detTex.Add('\end{table}') | Out-Null
Write-Utf8File (Join-Path $TablesRoot '05_deterministic.tex') $detTex.ToArray()

Add-LedgerRow 'moderate_grid_crossings' '0 of 360 low/mid/high cells cross' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'scenario_id in {low,mid,high}' `
  'crosses_v1;cell_result_class' `
  'All 360 filtered rows have crosses_v1=False and cell_result_class=not_feasible.'
Add-LedgerRow 'section5_prudential_margin' 'xi=0.10 (10 percent)' `
  'reports/threshold_inversion_result_baseline-official-v2.csv; reports/h_star_result_baseline-official-v3.csv' `
  'xi=0.1' `
  'xi;threshold_value' `
  'The inversion and persistence panels report the 10-percent prudential margin; deterministic structural crossings use V>=1.'
Add-LedgerRow 'moderate_v_max' '0.177' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'scenario_id in {low,mid,high}; maximum v_gross' `
  'country_id;policy_variant_id;scenario_id;regime_id;v_gross' `
  "Raw maximum=$($moderateMax.v_gross), PER/PEN/mid/r4."
Add-LedgerRow 'per_pen_stress_range' '1.02--1.42' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'country_id=PER AND policy_variant_id=PEN AND scenario_id=stress AND regime_id in {r0,...,r4}' `
  'v_gross;crosses_v1;cell_result_class' `
  "Raw min=$perMin; raw max=$perMax; every row is accounting_feasible_debt_failed."
Add-LedgerRow 'per_pen_stress_buffer' 'r2 and r4 reach V>=1.10; r0, r1, and r3 do not' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'country_id=PER AND policy_variant_id=PEN AND scenario_id=stress; compare v_gross with 1.10 by regime_id' `
  'regime_id;v_gross;crosses_v1;cell_result_class' `
  'The 10-percent prudential comparison is reported separately from the structural crosses_v1 flag.'
Add-LedgerRow 'col_best_cell' '0.91' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'country_id=COL; maximum v_gross over grid' `
  'policy_variant_id;scenario_id;regime_id;v_gross;cell_result_class' `
  "Raw=$($colBest.v_gross), PEN/stress/r4, not_feasible."
Add-LedgerRow 'mex_best_cell' '0.80' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'country_id=MEX; maximum v_gross over grid' `
  'policy_variant_id;scenario_id;regime_id;v_gross;cell_result_class' `
  "Raw=$($mexBest.v_gross), GMI ideal/stress/r4, not_feasible."
$chlIdealR4 = Get-UniqueRow $VGrid { $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_ideal_aggregate' -and $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r4' } 'CHL GMI ideal stress r4'
$chlLoadedR4 = Get-UniqueRow $VGrid { $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_loaded_aggregate' -and $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r4' } 'CHL GMI loaded stress r4'
Add-LedgerRow 'chl_gmi_stress_r4' 'GMI ideal 5.80; GMI loaded 3.87' `
  'reports/paper_tables/table4_vgross_baseline.csv' `
  'country_id=CHL AND scenario_id=stress AND regime_id=r4 AND policy_variant_id in {GMI ideal,GMI loaded}' `
  'v_gross;crosses_v1;cell_result_class' `
  "Raw ideal=$($chlIdealR4.v_gross); raw loaded=$($chlLoadedR4.v_gross); both feasible_cell."

# Monte Carlo summaries for Panel A.
$mcPrimaryModerate = @($MonteCarlo | Where-Object {
    $_.mc_mode -eq 'MC_independent_baseline' -and $_.prob_basis -eq 'all_draw' -and
    $_.scenario_id -in @('low', 'mid', 'high')
  })
$mcPrimaryMax = $mcPrimaryModerate | Sort-Object { [double]$_.prob_v_ge_1_00 } -Descending | Select-Object -First 1
$mcFactorModerate = @($MonteCarlo | Where-Object {
    $_.mc_mode -like 'MC_factor*' -and $_.prob_basis -eq 'all_draw' -and
    $_.scenario_id -in @('low', 'mid', 'high')
  })
$mcFactorMax = $mcFactorModerate | Sort-Object { [double]$_.prob_v_ge_1_00 } -Descending | Select-Object -First 1
$histIdeal = @($MonteCarlo | Where-Object {
    $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_ideal_aggregate' -and
    $_.scenario_id -eq 'mid' -and $_.regime_id -eq 'r0' -and
    $_.mc_mode -like 'historical_reduced_form*' -and $_.prob_basis -eq 'all_draw'
  })
$histLoaded = @($MonteCarlo | Where-Object {
    $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_loaded_aggregate' -and
    $_.scenario_id -eq 'mid' -and $_.regime_id -eq 'r0' -and
    $_.mc_mode -like 'historical_reduced_form*' -and $_.prob_basis -eq 'all_draw'
  })
$chlStressMc = @($MonteCarlo | Where-Object {
    $_.country_id -eq 'CHL' -and $_.policy_variant_id -like 'GMI*' -and
    $_.scenario_id -eq 'stress' -and $_.mc_mode -eq 'MC_independent_baseline' -and
    $_.prob_basis -eq 'all_draw'
  })
$perStressMc = @($MonteCarlo | Where-Object {
    $_.country_id -eq 'PER' -and $_.policy_variant_id -eq 'PEN' -and
    $_.scenario_id -eq 'stress' -and $_.mc_mode -eq 'MC_independent_baseline' -and
    $_.prob_basis -eq 'all_draw'
  })
if ($histIdeal.Count -ne 4 -or $histLoaded.Count -ne 4 -or $chlStressMc.Count -ne 10 -or $perStressMc.Count -ne 5) {
  throw 'Unexpected Monte Carlo summary dimensions.'
}
function Percent-Range {
  param([object[]]$Rows, [string]$Property)
  $minimum = ($Rows | Measure-Object -Property $Property -Minimum).Minimum
  $maximum = ($Rows | Measure-Object -Property $Property -Maximum).Maximum
  return @((Format-Number (100.0 * [double]$minimum)), (Format-Number (100.0 * [double]$maximum)))
}
$histIdealRange = Percent-Range $histIdeal 'prob_v_ge_1_00'
$histLoadedRange = Percent-Range $histLoaded 'prob_v_ge_1_00'
$chlStressRange = Percent-Range $chlStressMc 'prob_v_ge_1_00'
$perStressAccounting = Percent-Range $perStressMc 'prob_v_ge_1_00'
$perStressDebt = Percent-Range $perStressMc 'prob_debt_consistent_1_00'

# Inversion rows for Panel B.
$inversionDefinitions = @(
  @{ Country = 'CHL'; Variant = 'GMI:GMI_ideal_aggregate'; Label = 'Chile, GMI ideal' },
  @{ Country = 'PER'; Variant = 'PEN'; Label = 'Peru, social pension' },
  @{ Country = 'COL'; Variant = 'PEN'; Label = 'Colombia, social pension' },
  @{ Country = 'MEX'; Variant = 'GMI:GMI_ideal_aggregate'; Label = 'Mexico, GMI ideal' },
  @{ Country = 'MEX'; Variant = 'GMI:GMI_loaded_aggregate'; Label = 'Mexico, GMI loaded' }
)
$inversionRows = [System.Collections.Generic.List[object]]::new()
foreach ($definition in $inversionDefinitions) {
  $country = $definition.Country
  $variant = $definition.Variant
  $row = Get-UniqueRow $ThresholdXi10 {
    $_.country_id -eq $country -and $_.policy_variant_id -eq $variant -and
    $_.scenario_id -eq 'mid' -and $_.regime_id -eq 'r4' -and
    $_.requirement_basis -eq 'baseline'
  } "mid r4 inversion $country/$variant"
  $inversionRows.Add([pscustomobject]@{ Definition = $definition; Row = $row }) | Out-Null
  $claimVariant = ($variant -replace '[^A-Za-z0-9]+', '_').Trim('_')
  Add-LedgerRow "inversion_mid_r4_${country}_${claimVariant}" `
    (('g*= {0} percent; MFC*= {1} percent; Treq={2}; tauAIreq={3} percent' -f
        (Format-Number (100.0 * [double]$row.g_ai_required)),
        (Format-Number (100.0 * [double]$row.mfc_required_gross)),
        (Format-Number ([double]$row.t_required_H)),
        (Format-Number (100.0 * [double]$row.tau_ai_required)))) `
    'reports/threshold_inversion_result_baseline-official-v2.csv; reports/paper_tables/table5_threshold_inversion.csv' `
    "country_id=$country AND policy_variant_id=$variant AND scenario_id=mid AND regime_id=r4 AND requirement_basis=baseline AND xi=0.1" `
    'g_ai_required;mfc_required_gross;t_required_H;tau_ai_required' `
    'The compact frozen paper table matches g_ai_required and mfc_required_gross exactly; the full official inversion CSV supplies the two omitted diagnostic columns.'
}
$midThresholds = @($ThresholdXi10 | Where-Object { $_.scenario_id -eq 'mid' })
$minT = $midThresholds | Sort-Object { [double]$_.t_required_H } | Select-Object -First 1
$midBaselineTau = @($ThresholdXi10 | Where-Object {
    $_.scenario_id -eq 'mid' -and $_.requirement_basis -eq 'baseline' -and $_.tau_ai_required -ne ''
  })
$minTau = $midBaselineTau | Sort-Object { [double]$_.tau_ai_required } | Select-Object -First 1
$tauBound = Get-UniqueRow $ValueAssignments { $_.name -eq 'tau_AI_eff_r4' } 'specified r4 AI-rent rate'
$tauRatio = [double]$minTau.tau_ai_required / [double]$tauBound.high_value
Add-LedgerRow 'translation_requirement_min_mid' '1.0941' `
  'reports/threshold_inversion_result_baseline-official-v2.csv' `
  'xi=0.1 AND scenario_id=mid; minimum t_required_H across baseline and debt_consistent' `
  't_required_H;country_id;policy_variant_id;regime_id;requirement_basis' `
  "Raw=$($minT.t_required_H), CHL/GMI ideal/r4; every filtered row exceeds one."
Add-LedgerRow 'ai_rent_requirement_min_mid' '202.46 percent' `
  'reports/threshold_inversion_result_baseline-official-v2.csv' `
  'xi=0.1 AND scenario_id=mid AND requirement_basis=baseline AND tau_ai_required nonmissing; minimum' `
  'tau_ai_required;country_id;policy_variant_id;regime_id' `
  "Raw rate=$($minTau.tau_ai_required), CHL/GMI ideal/r4."
Add-LedgerRow 'ai_rent_specified_upper' '15 percent' `
  'reports/value_assignment_table_baseline-official-v3.csv' `
  'name=tau_AI_eff_r4' `
  'high_value;baseline_value;low_value;regime_code' `
  "Raw high_value=$($tauBound.high_value)."
Add-LedgerRow 'ai_rent_requirement_ratio' '13.50 times the specified upper support' `
  'reports/threshold_inversion_result_baseline-official-v2.csv; reports/value_assignment_table_baseline-official-v3.csv' `
  'minimum mid baseline tau_ai_required divided by high_value where name=tau_AI_eff_r4' `
  'tau_ai_required;high_value' `
  "Raw ratio=$tauRatio."

# H-star rows for Panel C.
function Get-HStarRows {
  param([string]$Country, [string]$Variant, [string]$Basis)
  return @($HStar | Where-Object {
      $_.country_id -eq $Country -and $_.policy_variant_id -eq $Variant -and
      $_.scenario_id -eq 'stress' -and $_.xi -eq '0.1' -and
      $_.requirement_basis -eq $Basis
    })
}
$hChl = Get-HStarRows 'CHL' 'GMI:GMI_ideal_aggregate' 'baseline'
$hChlDebt = Get-HStarRows 'CHL' 'GMI:GMI_ideal_aggregate' 'debt_consistent'
$hPer = Get-HStarRows 'PER' 'PEN' 'baseline'
$hPerDebt = Get-HStarRows 'PER' 'PEN' 'debt_consistent'
$hCol = Get-HStarRows 'COL' 'PEN' 'baseline'
$hColDebt = Get-HStarRows 'COL' 'PEN' 'debt_consistent'
$hMexIdeal = Get-HStarRows 'MEX' 'GMI:GMI_ideal_aggregate' 'baseline'
$hMexIdealDebt = Get-HStarRows 'MEX' 'GMI:GMI_ideal_aggregate' 'debt_consistent'
$hMexLoaded = Get-HStarRows 'MEX' 'GMI:GMI_loaded_aggregate' 'baseline'
$hMexLoadedDebt = Get-HStarRows 'MEX' 'GMI:GMI_loaded_aggregate' 'debt_consistent'
foreach ($set in @($hChl, $hChlDebt, $hPer, $hPerDebt, $hCol, $hColDebt, $hMexIdeal, $hMexIdealDebt, $hMexLoaded, $hMexLoadedDebt)) {
  if ($set.Count -ne 5) { throw 'Unexpected H-star regime count.' }
}
function HRange {
  param([object[]]$Rows)
  $finite = @($Rows | Where-Object { $_.h_star -ne '' })
  if ($finite.Count -eq 0) {
    if (@($Rows | Where-Object { $_.h_star_status -ne 'censored_beyond_defensible_horizon' }).Count -gt 0) {
      throw 'Unexpected non-finite H-star status.'
    }
    return '>25'
  }
  $min = [int][double](($finite | Measure-Object -Property h_star -Minimum).Minimum)
  $max = [int][double](($finite | Measure-Object -Property h_star -Maximum).Maximum)
  if ($min -eq $max) { return "$min" }
  return "$min--$max"
}
$hPerRange = HRange $hPer
$hPerDebtRange = HRange $hPerDebt
$hColRange = HRange $hCol
$hColDebtRange = HRange $hColDebt
$hMexIdealRange = HRange $hMexIdeal
$hMexIdealDebtRange = HRange $hMexIdealDebt
$hMexLoadedRange = HRange $hMexLoaded
$hMexLoadedDebtRange = HRange $hMexLoadedDebt
$hChlR0 = Get-UniqueRow $hChl { $_.regime_id -eq 'r0' } 'CHL Hstar r0'
$hChlR4 = Get-UniqueRow $hChl { $_.regime_id -eq 'r4' } 'CHL Hstar r4'

$comboTex = [System.Collections.Generic.List[string]]::new()
$comboTex.Add('\begin{table}[H]') | Out-Null
$comboTex.Add('\centering') | Out-Null
$comboTex.Add('\footnotesize') | Out-Null
$comboTex.Add('\begin{singlespace}') | Out-Null
$comboTex.Add('\caption{Crossing frequencies, threshold requirements, and persistence horizons}') | Out-Null
$comboTex.Add('\label{tab:frequency_threshold_hstar_clean}') | Out-Null
$comboTex.Add('\textit{Panel A. Model-implied crossing frequencies across calibrated draws}\\[0.2em]') | Out-Null
$comboTex.Add('\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.48\textwidth}rr@{}}') | Out-Null
$comboTex.Add('\toprule') | Out-Null
$comboTex.Add('Mode and cell & Accounting (\%) & Debt-consistent (\%) \\') | Out-Null
$comboTex.Add('\midrule') | Out-Null
$comboTex.Add(('Primary channel MC, maximum over low/mid/high & {0} & {0} \\' -f (Format-Number (100.0 * [double]$mcPrimaryMax.prob_v_ge_1_00)))) | Out-Null
$comboTex.Add(('Factor-dependence modes, maximum over low/mid/high & {0} & {0} \\' -f (Format-Number (100.0 * [double]$mcFactorMax.prob_v_ge_1_00)))) | Out-Null
$comboTex.Add(('Historical reduced form, Chile GMI ideal, mid r0 & {0}--{1} & {0}--{1} \\' -f $histIdealRange[0], $histIdealRange[1])) | Out-Null
$comboTex.Add(('Historical reduced form, Chile GMI loaded, mid r0 & {0}--{1} & {0}--{1} \\' -f $histLoadedRange[0], $histLoadedRange[1])) | Out-Null
$comboTex.Add(('Primary channel MC, Chile GMI, stress r0--r4 & {0}--{1} & {0}--{1} \\' -f $chlStressRange[0], $chlStressRange[1])) | Out-Null
$comboTex.Add(('Primary channel MC, Peru PEN, stress r0--r4 & {0}--{1} & {2}--{3} \\' -f $perStressAccounting[0], $perStressAccounting[1], $perStressDebt[0], $perStressDebt[1])) | Out-Null
$comboTex.Add('\bottomrule') | Out-Null
$comboTex.Add('\end{tabular}') | Out-Null
$comboTex.Add('\\[0.7em]\textit{Panel B. Buffered mid-scenario inversions under r4}\\[0.2em]') | Out-Null
$comboTex.Add('\begin{tabular}{@{}lrrrr@{}}') | Out-Null
$comboTex.Add('\toprule') | Out-Null
$comboTex.Add('Country and instrument & $g^{AI,*}$ (\%) & $MFC^{gross,*}$ (\%) & $T^{req,H}$ & $\tau^{AI,req}$ (\%) \\') | Out-Null
$comboTex.Add('\midrule') | Out-Null
foreach ($item in $inversionRows) {
  $row = $item.Row
  $comboTex.Add(('{0} & {1} & {2} & {3} & {4} \\' -f
      $item.Definition.Label,
      (Format-Number (100.0 * [double]$row.g_ai_required)),
      (Format-Number (100.0 * [double]$row.mfc_required_gross)),
      (Format-Number ([double]$row.t_required_H)),
      (Format-Number (100.0 * [double]$row.tau_ai_required)))) | Out-Null
}
$comboTex.Add('\bottomrule') | Out-Null
$comboTex.Add('\end{tabular}') | Out-Null
$comboTex.Add('\\[0.7em]\textit{Panel C. Required persistence $H^*$ under stress, $\xi=0.10$}\\[0.2em]') | Out-Null
$comboTex.Add('\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.47\textwidth}rr@{}}') | Out-Null
$comboTex.Add('\toprule') | Out-Null
$comboTex.Add('Country and instrument & Accounting $H^*$ & Debt-consistent $H^*$ \\') | Out-Null
$comboTex.Add('\midrule') | Out-Null
$comboTex.Add(('Chile, GMI ideal (r0 / r4) & {0} / {1} & {0} / {1} \\' -f ([int][double]$hChlR0.h_star), ([int][double]$hChlR4.h_star))) | Out-Null
$comboTex.Add(('Peru, social pension (r0--r4) & {0} & {1} \\' -f $hPerRange, $hPerDebtRange)) | Out-Null
$comboTex.Add(('Colombia, social pension (r0--r4) & {0} & {1} \\' -f $hColRange, $hColDebtRange)) | Out-Null
$comboTex.Add(('Mexico, GMI ideal (r0--r4) & {0} & {1} \\' -f $hMexIdealRange, $hMexIdealDebtRange)) | Out-Null
$comboTex.Add(('Mexico, GMI loaded (r0--r4) & {0} & {1} \\' -f $hMexLoadedRange, $hMexLoadedDebtRange)) | Out-Null
$comboTex.Add('\bottomrule') | Out-Null
$comboTex.Add('\end{tabular}') | Out-Null
$comboTex.Add('\begin{minipage}{0.94\textwidth}\footnotesize') | Out-Null
$comboTex.Add('\emph{Note:} Frequencies use \texttt{prob\_basis=all\_draw}. Historical reduced-form modes are alternative capture specifications available only under r0. Panel B reports accounting inversions at $\xi=0.10$; $g^{AI,*}$ is an accumulated gain. $H^*$ is a post-baseline derived extension and is censored after 25 years.') | Out-Null
$comboTex.Add('\end{minipage}') | Out-Null
$comboTex.Add('\end{singlespace}') | Out-Null
$comboTex.Add('\end{table}') | Out-Null
Write-Utf8File (Join-Path $TablesRoot '05_frequency_threshold_hstar.tex') $comboTex.ToArray()

Add-LedgerRow 'mc_primary_moderate_max' '2.36 percent' `
  'reports/monte_carlo_result_baseline-official-v3.csv' `
  'mc_mode=MC_independent_baseline AND prob_basis=all_draw AND scenario_id in {low,mid,high}; maximum prob_v_ge_1_00' `
  'country_id;policy_variant_id;scenario_id;regime_id;prob_v_ge_1_00;prob_debt_consistent_1_00' `
  'CHL/GMI ideal/mid/r4; the debt probability is identical because Chile has no positive primary-balance correction.'
Add-LedgerRow 'mc_factor_moderate_max' '4.44 percent' `
  'reports/monte_carlo_result_baseline-official-v3.csv' `
  'mc_mode like MC_factor* AND prob_basis=all_draw AND scenario_id in {low,mid,high}; maximum prob_v_ge_1_00' `
  'country_id;policy_variant_id;scenario_id;regime_id;mc_mode;prob_v_ge_1_00' `
  'CHL/GMI ideal/mid/r4 under MC_factor_rho07.'
Add-LedgerRow 'mc_historical_chl_gmi_mid' `
  "GMI ideal $($histIdealRange[0])--$($histIdealRange[1]) percent; loaded $($histLoadedRange[0])--$($histLoadedRange[1]) percent" `
  'reports/monte_carlo_result_baseline-official-v3.csv' `
  'country_id=CHL AND scenario_id=mid AND regime_id=r0 AND mc_mode like historical_reduced_form* AND prob_basis=all_draw; split by GMI variant' `
  'policy_variant_id;mc_mode;prob_v_ge_1_00' `
  'Ranges span mixture/positive and tax/total-revenue historical capture modes.'
Add-LedgerRow 'mc_chl_gmi_stress' "$($chlStressRange[0])--$($chlStressRange[1]) percent" `
  'reports/monte_carlo_result_baseline-official-v3.csv' `
  'country_id=CHL AND policy_variant_id like GMI* AND scenario_id=stress AND regime_id in {r0,...,r4} AND mc_mode=MC_independent_baseline AND prob_basis=all_draw' `
  'prob_v_ge_1_00;prob_debt_consistent_1_00' `
  'Range combines ideal and loaded GMI variants; accounting and debt-consistent frequencies coincide.'
Add-LedgerRow 'mc_per_pen_stress' `
  "accounting $($perStressAccounting[0])--$($perStressAccounting[1]) percent; debt $($perStressDebt[0])--$($perStressDebt[1]) percent" `
  'reports/monte_carlo_result_baseline-official-v3.csv' `
  'country_id=PER AND policy_variant_id=PEN AND scenario_id=stress AND regime_id in {r0,...,r4} AND mc_mode=MC_independent_baseline AND prob_basis=all_draw' `
  'regime_id;prob_v_ge_1_00;prob_debt_consistent_1_00' `
  'The debt maximum is 0.0248 under r4, not below one percent.'
Add-LedgerRow 'hstar_chl_gmi_ideal' 'r0=6 years; r4=5 years; debt same' `
  'reports/h_star_result_baseline-official-v3.csv' `
  'country_id=CHL AND policy_variant_id=GMI:GMI_ideal_aggregate AND scenario_id=stress AND xi=0.1 AND regime_id in {r0,r4}' `
  'regime_id;requirement_basis;h_star;h_star_status;h_star_reporting_cap' `
  'All cited rows cross within the 25-year cap.'
Add-LedgerRow 'hstar_per_pen' "accounting $hPerRange years; debt $hPerDebtRange years" `
  'reports/h_star_result_baseline-official-v3.csv' `
  'country_id=PER AND policy_variant_id=PEN AND scenario_id=stress AND xi=0.1 AND regime_id in {r0,...,r4}' `
  'regime_id;requirement_basis;h_star;h_star_status' `
  'All cited rows cross within the cap.'
Add-LedgerRow 'hstar_col_pen' "accounting $hColRange years; debt >25 years" `
  'reports/h_star_result_baseline-official-v3.csv' `
  'country_id=COL AND policy_variant_id=PEN AND scenario_id=stress AND xi=0.1 AND regime_id in {r0,...,r4}' `
  'regime_id;requirement_basis;h_star;h_star_status;h_star_reporting_cap' `
  'Every debt-consistent counterpart is censored_beyond_defensible_horizon at the 25-year cap.'
Add-LedgerRow 'hstar_mex_gmi' `
  "ideal accounting $hMexIdealRange years; loaded accounting $hMexLoadedRange years; debt >25 years" `
  'reports/h_star_result_baseline-official-v3.csv' `
  'country_id=MEX AND policy_variant_id in {GMI ideal,GMI loaded} AND scenario_id=stress AND xi=0.1 AND regime_id in {r0,...,r4}' `
  'policy_variant_id;regime_id;requirement_basis;h_star;h_star_status;h_star_reporting_cap' `
  'Every debt-consistent counterpart is censored_beyond_defensible_horizon at the 25-year cap.'

# Table 5.4: diagnostic and robustness results.
$placeboCrosses = @($Placebo | Where-Object { $_.placebo_cell_class -ne 'not_feasible' })
$placeboMax = $Placebo | Sort-Object { [double]$_.v_placebo } -Descending | Select-Object -First 1
$baselineCrossCount = @($NegativeControl | Where-Object { $_.baseline_crosses_v1 -eq 'True' }).Count
$negativeCrossCount = @($NegativeControl | Where-Object { $_.negative_control_crosses_v1 -eq 'True' }).Count
$collapseRatios = @($NegativeControl.collapse_ratio | Sort-Object -Unique)
$losoPass = @($Loso | Where-Object { $_.status -eq 'PASS' })
$losoUnavailable = @($Loso | Where-Object { $_.status -eq 'not_available' })
if ($Placebo.Count -ne 120 -or $placeboCrosses.Count -ne 0 -or
    $baselineCrossCount -ne 15 -or $negativeCrossCount -ne 6 -or
    $collapseRatios.Count -ne 1 -or
    $losoPass.Count -ne 3 -or $losoUnavailable.Count -ne 3) {
  throw 'Diagnostic summary invariant failed.'
}
$chlAblation = @($ChannelAblation | Where-Object {
    $_.country_id -eq 'CHL' -and $_.policy_variant_id -eq 'GMI:GMI_ideal_aggregate' -and
    $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r0'
  })
$perAblation = @($ChannelAblation | Where-Object {
    $_.country_id -eq 'PER' -and $_.policy_variant_id -eq 'PEN' -and
    $_.scenario_id -eq 'stress' -and $_.regime_id -eq 'r4'
  })
if ($chlAblation.Count -ne 4 -or $perAblation.Count -ne 4) { throw 'Unexpected channel-ablation rows.' }

$diagTex = [System.Collections.Generic.List[string]]::new()
$diagTex.Add('\begin{table}[H]') | Out-Null
$diagTex.Add('\centering') | Out-Null
$diagTex.Add('\footnotesize') | Out-Null
$diagTex.Add('\begin{singlespace}') | Out-Null
$diagTex.Add('\caption{Diagnostic and robustness results}') | Out-Null
$diagTex.Add('\label{tab:diagnostics_clean}') | Out-Null
$diagTex.Add('\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.25\textwidth}>{\raggedright\arraybackslash}p{0.67\textwidth}@{}}') | Out-Null
$diagTex.Add('\toprule') | Out-Null
$diagTex.Add('Exercise & Result \\') | Out-Null
$diagTex.Add('\midrule') | Out-Null
$diagTex.Add(('ICT temporal placebo & No crossing in 120 cells; maximum $V^{{placebo}}={0}$. \\' -f (Format-Number ([double]$placeboMax.v_placebo) '0.000'))) | Out-Null
$diagTex.Add(('Reduced-form exposure-rescaling diagnostic & {0} of {1} structural crossings survive after multiplication by {2}; the diagnostic does not clear the crossing criterion. \\' -f $negativeCrossCount, $baselineCrossCount, (Format-Number -Value ([double]$collapseRatios[0]) -Pattern '0.000'))) | Out-Null
$diagTex.Add('Channel ablation & Chile GMI ideal remains above one after any single channel is removed; Peru PEN falls below one without labor or consumption but not without capital or AI rents. \\') | Out-Null
$diagTex.Add(('Leave-one-source-out & The {0} available OECD--GRD substitutions preserve class and rank; {1} core-source exclusions are unavailable in the archived inputs. \\' -f $losoPass.Count, $losoUnavailable.Count)) | Out-Null
$diagTex.Add('\bottomrule') | Out-Null
$diagTex.Add('\end{tabular}') | Out-Null
$diagTex.Add('\begin{minipage}{0.94\textwidth}\footnotesize') | Out-Null
$diagTex.Add('\emph{Note:} Channel-ablation values use the diagnostic recomputation with the behavioral-erosion companion.') | Out-Null
$diagTex.Add('\end{minipage}') | Out-Null
$diagTex.Add('\end{singlespace}') | Out-Null
$diagTex.Add('\end{table}') | Out-Null
Write-Utf8File (Join-Path $TablesRoot '05_diagnostics.tex') $diagTex.ToArray()

Add-LedgerRow 'ict_placebo_result' '0 of 120 crossings; maximum V=0.750' `
  'reports/diagnostic_placebo_ict_result_baseline-official-v3.csv' `
  'scenario_id=placebo_ict_mid; all countries, policies, and regimes' `
  'placebo_cell_class;v_placebo;country_id;policy_variant_id' `
  "All rows are not_feasible; raw maximum=$($placeboMax.v_placebo), PER/PEN."
Add-LedgerRow 'negative_control_result' '9 of 15 crossings disappear; 6 survive; multiplier 0.318; diagnostic does not clear the crossing criterion' `
  'reports/diagnostic_negative_control_result_baseline-official-v3.csv' `
  'full diagnostic grid' `
  'baseline_crosses_v1;negative_control_crosses_v1;collapse_ratio' `
  "Raw multiplier=$($collapseRatios[0]); the implemented exposure-rescaling formula is V_negative_control=V_baseline*collapse_ratio."
Add-LedgerRow 'loso_result' '3 evaluated substitutions preserve class/rank; 3 unavailable' `
  'reports/diagnostic_loso_result_baseline-official-v3.csv' `
  'status in {PASS,not_available}' `
  'status;baseline_class;alternative_class;rank_change;alternative_source' `
  'All three evaluated rows are OECD-to-GRD substitutions with rank_change=0.'
# Replace only section 5 rows in the shared ledger; approved section 4 rows remain byte-equivalent in content.
$existingLedger = @(Import-Csv -LiteralPath $LedgerPath | Where-Object { $_.section -ne '5' })
$combinedLedger = @($existingLedger) + @($LedgerRows.ToArray())
$ledgerCsv = @($combinedLedger | ConvertTo-Csv -NoTypeInformation)
Write-Utf8File $LedgerPath $ledgerCsv

Write-Output ("Generated four tables, copied the frozen heatmap, and wrote {0} section-5 ledger rows." -f $LedgerRows.Count)
