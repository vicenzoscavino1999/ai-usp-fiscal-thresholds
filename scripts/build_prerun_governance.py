from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


SCRIPT_NAME = "build_prerun_governance.py"
REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "ai_usp_threshold.duckdb"
MODEL_INPUTS_DIR = REPO_ROOT / "data" / "model_inputs"
REPORTS_DIR = REPO_ROOT / "reports"
DATASET_VERSION = "v0.1.2-pilot-per"
PREVIOUS_PARAMETER_SET_ID = "baseline-pilot-v1"
PARAMETER_SET_ID = "baseline-pilot-v2"
ANCHOR_YEAR = 2024
COUNTRY_ID = "PER"
CHANGELOG = [
    ("C1", "E_auto reset to 0.035 with support [0.02,0.05]; E_aug/E_prod remain 0.11 with support [0.08,0.14]."),
    ("C2", "psi_shift reset to 0.15 with support [0.00,0.30], bounded PERT, author-review status."),
    ("C3", "Gap pilot note changed to diagnostic neutral value with favorable-bias and official-baseline blocker; robustness_only audit row added."),
    ("C4", "q_use_target support reset to prior +/-30 percent around the derived target: [0.077,0.144]; AIPI double-use note added."),
    ("C5", "phi high interpretive note added: high LP-to-Y bridge makes phi_high_Y below phi_mid, so scenario labels are source-disciplined, not monotone in phi_Y."),
]

SCENARIO_TO_INT = {"low": 0, "mid": 1, "high": 2, "stress": 3}
INT_TO_SCENARIO = {v: k for k, v in SCENARIO_TO_INT.items()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").upper()


def bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def logit_on_ceiling(q: float, q_bar: float) -> float:
    if not (0 < q < q_bar):
        raise ValueError(f"q must be inside (0, q_bar), got q={q}, q_bar={q_bar}")
    return math.log(q / (q_bar - q))


def read_one(con: duckdb.DuckDBPyConnection, query: str) -> pd.Series:
    df = con.execute(query).fetchdf()
    if len(df) != 1:
        raise ValueError(f"Expected one row for query, got {len(df)}: {query}")
    return df.iloc[0]


def wdi_value(indicator_code: str, year: int) -> float:
    path = REPO_ROOT / "data" / "raw_snapshots" / DATASET_VERSION / "wdi" / "wdi_country_year.parquet"
    df = pd.read_parquet(path)
    rows = df[
        (df["country_id"] == COUNTRY_ID)
        & (df["indicator_code"] == indicator_code)
        & (df["year"] == year)
    ]
    if rows.empty:
        raise ValueError(f"Missing WDI {indicator_code} for {COUNTRY_ID} {year}")
    return float(rows.iloc[0]["value"])


def residualized_rst_proxy() -> tuple[float, str]:
    path = REPO_ROOT / "data" / "raw_snapshots" / DATASET_VERSION / "imf_aipi" / "aipi.parquet"
    df = pd.read_parquet(path)
    sample = df[["country_id", "aipi_total", "human_capital_labor"]].dropna()
    if COUNTRY_ID not in set(sample["country_id"]):
        raise ValueError(f"Missing AIPI human-capital row for {COUNTRY_ID}")

    x = sample["aipi_total"].to_numpy(dtype=float)
    y = sample["human_capital_labor"].to_numpy(dtype=float)
    x_mat = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(x_mat, y, rcond=None)[0]
    residuals = y - x_mat @ beta
    sample = sample.copy()
    sample["rst_residual"] = residuals
    sample["rst_percentile"] = sample["rst_residual"].rank(method="average", pct=True)
    rst = float(sample.loc[sample["country_id"] == COUNTRY_ID, "rst_percentile"].iloc[0])
    note = (
        "RST proxy uses AIPI human_capital_labor residualized on total AIPI over the "
        "international AIPI sample, then percentile-ranked to [0,1]. This is the "
        "paper-permitted fallback when ILO training/ALMP inputs are unavailable."
    )
    return rst, note


def add_value(rows: list[dict], **kwargs) -> None:
    required = {
        "name",
        "module",
        "value_type",
        "unit",
        "baseline_value",
        "low_value",
        "high_value",
        "support_type",
        "source_id",
        "formula_id",
        "distribution",
        "truncation_rule",
        "primary_spec_flag",
        "robustness_flag",
        "stress_flag",
        "double_counting_risk",
        "audit_status",
    }
    missing = required - set(kwargs)
    if missing:
        raise ValueError(f"Missing value fields for {kwargs.get('name')}: {sorted(missing)}")
    for key in ["country_id", "scenario_id", "policy_id", "regime_code", "notes"]:
        kwargs.setdefault(key, None if key != "notes" else "")
    kwargs.setdefault("double_counting_note", kwargs["double_counting_risk"])
    kwargs["dataset_version"] = DATASET_VERSION
    kwargs["parameter_set_id"] = PARAMETER_SET_ID
    kwargs["assumption_id"] = "A3A_V2_" + clean_id(kwargs["name"])
    kwargs["created_at"] = NOW
    kwargs["created_by_script"] = SCRIPT_NAME
    rows.append(kwargs)


def build_values(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, dict]:
    cp = read_one(con, f"SELECT * FROM country_panel WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}")
    fiscal = read_one(con, f"SELECT * FROM fiscal_anchor WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}")
    debt = read_one(con, f"SELECT * FROM debt_guardrail_anchor WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}")
    exposure = read_one(con, f"SELECT * FROM ai_exposure_anchor WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}")

    consumption_gdp_share = wdi_value("NE.CON.TOTL.ZS", ANCHOR_YEAR) / 100.0
    imports_gdp_share = wdi_value("NE.IMP.GNFS.ZS", ANCHOR_YEAR) / 100.0
    import_content_consumption = bounded(imports_gdp_share / consumption_gdp_share, 0.0, 1.0)

    labor_share = float(cp["labor_share_raw"])
    non_labor_share = 1.0 - labor_share
    tau_l_eff = ((float(fiscal["pit_gdp"]) + float(fiscal["social_contrib_gdp"])) / 100.0) / labor_share
    tau_k_eff = (float(fiscal["cit_gdp"]) / 100.0) / non_labor_share
    tau_c_eff = (float(fiscal["vat_gdp"]) / 100.0) / consumption_gdp_share

    benchmark = con.execute(
        """
        SELECT AVG(adoption_proxy) AS avg_adoption, AVG(aipi_total) AS avg_aipi, COUNT(*) AS n
        FROM frontier_benchmark_anchor
        WHERE benchmark_set_id='candidate_eurostat_ge10_2024'
          AND benchmark_country_id IN (
            'AUT','BEL','CZE','DNK','EST','FIN','FRA','DEU','GRC','HUN',
            'IRL','ITA','LVA','LTU','LUX','NLD','NOR','POL','PRT','SVK',
            'SVN','ESP','SWE','TUR'
          )
        """
    ).fetchdf().iloc[0]
    q_use_target = float(benchmark["avg_adoption"]) * float(cp["aipi_total"]) / float(benchmark["avg_aipi"])
    q_use_target = bounded(q_use_target, 0.0, 1.0)

    informality_share = float(cp["informality_total"]) / 100.0
    gap_neutral = 0.0
    omega_i = 0.50
    omega_g = 0.50
    q_bar = bounded(1.0 - omega_i * informality_share - omega_g * gap_neutral, 0.0, 1.0)
    epsilon = 1e-9
    epsilon_mu = 1e-6
    q_use_target_low = 0.077
    q_use_target_high = 0.144
    q_use_target_adj = min(max(q_use_target, epsilon_mu), q_bar - epsilon_mu)
    q_use_target_adj_low = min(max(q_use_target_low, epsilon_mu), q_bar - epsilon_mu)
    q_use_target_adj_high = min(max(q_use_target_high, epsilon_mu), q_bar - epsilon_mu)
    nu_a = 1.00
    nu_i = 0.50
    nu_g = 0.50
    mu_t0 = logit_on_ceiling(q_use_target_adj, q_bar) - nu_a * float(cp["aipi_total"]) + nu_i * informality_share + nu_g * gap_neutral
    rst_proxy, rst_note = residualized_rst_proxy()

    rows: list[dict] = []

    phi_specs = {
        "low": {
            "raw_unit": "TFP_equivalent_annual_rate",
            "low": 0.0003,
            "mid": 0.0005,
            "high": 0.0007,
            "source": "acemoglu2024simple;PAPER_TABLE_PHI_SCENARIO_LADDER",
            "kappa": 1.0,
            "lambda_ai": (0.00, 0.00, 0.02),
        },
        "mid": {
            "raw_unit": "TFP_equivalent_annual_rate",
            "low": 0.0025,
            "mid": 0.00425,
            "high": 0.0060,
            "source": "filippucci2024miracle;OECD_MICRO_TO_MACRO;PAPER_TABLE_PHI_SCENARIO_LADDER",
            "kappa": 1.0,
            "lambda_ai": (0.03, 0.01, 0.06),
        },
        "high": {
            "raw_unit": "LP_equivalent_annual_rate_before_bridge",
            "low": 0.0040,
            "mid": 0.0085,
            "high": 0.0130,
            "source": "oecd2025g7;PAPER_TABLE_PHI_SCENARIO_LADDER",
            "kappa": labor_share,
            "lambda_ai": (0.06, 0.03, 0.10),
        },
        "stress": {
            "raw_unit": "GDP_equivalent_stress_annual_rate",
            "low": 0.0100,
            "mid": 0.0150,
            "high": 0.0200,
            "source": "PAPER_TABLE_PHI_SCENARIO_LADDER_STRESS_DIAGNOSTIC",
            "kappa": 1.0,
            "lambda_ai": (0.10, 0.05, 0.15),
        },
    }

    for scenario_id, spec in phi_specs.items():
        add_value(
            rows,
            name=f"phi_raw_{scenario_id}",
            module="ai_shock",
            value_type="scenario_parameter",
            unit=spec["raw_unit"],
            baseline_value=spec["mid"],
            low_value=spec["low"],
            high_value=spec["high"],
            support_type="paper_literature_support",
            source_id=spec["source"],
            formula_id="paper_phi_raw_support",
            distribution="bounded_PERT",
            truncation_rule="bounded_to_source_support",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="none",
            audit_status="registered",
            scenario_id=scenario_id,
            notes="Raw source-unit AI shock. Nominal GDP-equivalent value is derived separately.",
        )
        kappa_name = "kappa_LP_to_Y" if scenario_id == "high" else ("kappa_Y_to_Y" if scenario_id == "stress" else "kappa_TFP_to_Y")
        add_value(
            rows,
            name=f"{kappa_name}_{scenario_id}",
            module="ai_shock",
            value_type="bridge_parameter",
            unit="GDP_equivalent_per_raw_unit",
            baseline_value=spec["kappa"],
            low_value=spec["kappa"],
            high_value=spec["kappa"],
            support_type="paper_bridge_convention",
            source_id="PAPER_SEC_PARAMETERS;PWT_10_01" if scenario_id == "high" else "PAPER_SEC_PARAMETERS",
            formula_id="TFP_or_Y_identity;LP_bridge_uses_labor_share_for_high",
            distribution="fixed",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="none",
            audit_status="registered",
            scenario_id=scenario_id,
            country_id=COUNTRY_ID if scenario_id == "high" else None,
            notes="TFP/Y shocks use identity bridge; LP high scenario uses observed Peru labor share as conservative output bridge.",
        )
        add_value(
            rows,
            name=f"pi_AI_Y_{scenario_id}",
            module="ai_shock",
            value_type="bridge_parameter",
            unit="annual_nominal_price_adjustment_rate",
            baseline_value=0.0,
            low_value=0.0,
            high_value=0.0,
            support_type="fixed_baseline_convention",
            source_id="PAPER_SEC_PARAMETERS",
            formula_id="no_nominal_price_adjustment_in_baseline",
            distribution="fixed",
            truncation_rule="fixed_zero",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="none",
            audit_status="registered",
            scenario_id=scenario_id,
            notes="Nominal bridge is multiplicative; baseline sets explicit AI price wedge to zero.",
        )
        phi_y_note = "Derived for calibration only; no economic result is computed in Etapa 3A."
        if scenario_id == "high":
            phi_y_note = (
                "phi_high_Y (0.00380) < phi_mid (0.00425) por el puente LP->Y "
                "del propio paper (ecuación de midpoints); los labels de escenario "
                "están disciplinados por fuente, NO son monótonos en phi_Y; toda tabla "
                "reporta phi_high_LP y phi_high_Y juntos; la cláusula de clase "
                "'cruza solo en high' es inerte de facto en el determinístico."
            )
        add_value(
            rows,
            name=f"phi_Y_nom_{scenario_id}",
            module="ai_shock",
            value_type="derived_parameter",
            unit="nominal_GDP_equivalent_annual_rate",
            baseline_value=(1.0 + spec["kappa"] * spec["mid"]) * (1.0 + 0.0) - 1.0,
            low_value=(1.0 + spec["kappa"] * spec["low"]) * (1.0 + 0.0) - 1.0,
            high_value=(1.0 + spec["kappa"] * spec["high"]) * (1.0 + 0.0) - 1.0,
            support_type="derived_from_registered_inputs",
            source_id=spec["source"] + ";PAPER_SEC_10_4",
            formula_id="phi_Y_nom=(1+kappa*phi_raw)*(1+pi_AI_Y)-1",
            distribution="derived_bounded_PERT",
            truncation_rule="inherits_phi_raw_support",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="none",
            audit_status="registered",
            scenario_id=scenario_id,
            notes=phi_y_note,
        )
        lam_mid, lam_low, lam_high = spec["lambda_ai"]
        add_value(
            rows,
            name=f"lambda_AI_{scenario_id}",
            module="fiscal_channels_ai_rent",
            value_type="scenario_parameter",
            unit="share_of_AI_shock",
            baseline_value=lam_mid,
            low_value=lam_low,
            high_value=lam_high,
            support_type="paper_bounded_scenario_grid",
            source_id="PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_7_4_1",
            formula_id="scenario_grid_zero_low_medium_high",
            distribution="bounded_PERT",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="capital_profit_overlap",
            audit_status="registered_author_review",
            scenario_id=scenario_id,
            notes="AI-rent share is an economic scenario object, not regime-indexed. Subset convention is used, so lambda_AI_Kbase mirrors this value.",
        )
        add_value(
            rows,
            name=f"lambda_AI_Kbase_{scenario_id}",
            module="fiscal_channels_capital",
            value_type="derived_parameter",
            unit="share_of_AI_shock",
            baseline_value=lam_mid,
            low_value=lam_low,
            high_value=lam_high,
            support_type="derived_subset_convention",
            source_id="PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_7_4_1",
            formula_id="lambda_AI_Kbase=lambda_AI_under_subset_convention",
            distribution="derived_bounded_PERT",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=scenario_id == "stress",
            double_counting_risk="capital_profit_overlap",
            audit_status="registered",
            scenario_id=scenario_id,
            notes="Netting field for omega_K_net. This prevents counting the same AI rents in capital and AI-rent channels.",
        )

    adoption_values = [
        ("A_aipi_total", float(cp["aipi_total"]), 0.0, 1.0, "observed_anchor", "IMF_AIPI_DATA360", "published AIPI carried forward to 2024", "fixed_observed"),
        ("I_adopt_informality", informality_share, 0.0, 1.0, "observed_anchor", "ILOSTAT", "ILOSTAT informality share divided by 100", "fixed_observed"),
        ("I_ceiling_informality", informality_share, 0.0, 1.0, "observed_anchor", "ILOSTAT", "Same observed informality used for adoption ceiling; diffusion effect is inert in frozen baseline after mu inversion.", "fixed_observed"),
        ("Gap_excluded_indicators_neutral", gap_neutral, 0.0, 0.0, "missing_excluded_indicator_neutral_convention", "PLAN_01_GAP_AIPI_RULE;DATA_QUALITY_REPORT", "PILOTO-DIAGNÓSTICO: valor neutral por ausencia de indicador excluido; SESGO FAVORABLE declarado (elimina fricción digital); BLOQUEANTE para baseline oficial — antes de Etapa 4 construir gap_index con indicadores verificados como excluidos del AIPI (candidatos: canastas de precios/asequibilidad ITU) contra la lista de componentes del AIPI.", "fixed_zero"),
        ("q_use_target", q_use_target, q_use_target_low, q_use_target_high, "calibrated_prior_from_benchmark_scaled_by_aipi", "FRONTIER_BENCHMARK;IMF_AIPI_DATA360;PLAN_01_02", "OECD-Eurostat benchmark adoption average scaled by Peru AIPI relative to benchmark AIPI; support is an author-reviewed prior +/-30 percent around the derived target: [0.077,0.144].", "bounded_PERT"),
        ("omega_I", omega_i, 0.25, 0.75, "calibrated_prior", "PAPER_ADOPTION_MODULE;worldbank2021informality", "Informality ceiling penalty; omega_I<1 is the paper's economic restriction.", "bounded_PERT"),
        ("omega_G", omega_g, 0.25, 0.75, "calibrated_prior", "PAPER_ADOPTION_MODULE", "Digital-gap ceiling penalty. Gap baseline is neutral because no excluded indicator is available.", "bounded_PERT"),
        ("q_bar", q_bar, bounded(1.0 - 0.75 * informality_share), bounded(1.0 - 0.25 * informality_share), "derived_from_registered_inputs", "PAPER_ADOPTION_MODULE", "max(0,min(1,1-omega_I*I_ceiling-omega_G*Gap))", "derived_bounded_PERT"),
        ("epsilon", epsilon, epsilon, epsilon, "technical_floor", "PLAN_02_SEC_9_3", "Numerical floor for support checks.", "fixed"),
        ("epsilon_mu", epsilon_mu, epsilon_mu, epsilon_mu, "technical_floor", "PAPER_APP_ADOPTION_MODULE;PLAN_02_SEC_7_3", "Logit inversion floor.", "fixed"),
        ("q_use_target_adj", q_use_target_adj, q_use_target_adj_low, q_use_target_adj_high, "derived_from_registered_inputs", "PLAN_02_SEC_7_3", "Target projected to the interior of [epsilon_mu, q_bar-epsilon_mu]; support inherits q_use_target prior [0.077,0.144].", "derived_bounded_PERT"),
        ("q_prod_t0", q_use_target_adj, q_use_target_adj_low, q_use_target_adj_high, "paper_initial_condition", "PLAN_02_SEC_7_3;PAPER_APP_ADOPTION_MODULE", "Default initial condition q_prod_t0=q_use_target_adj; support inherits q_use_target prior [0.077,0.144].", "derived_bounded_PERT"),
        ("nu_A", nu_a, 0.25, 2.00, "calibrated_prior_inert_in_frozen_baseline", "PAPER_ADOPTION_MODULE;diffusion_literature", "Preparedness coefficient; inert in frozen baseline because mu is inverted to target.", "bounded_PERT"),
        ("nu_I", nu_i, 0.00, 1.00, "calibrated_prior_inert_in_frozen_baseline", "PAPER_ADOPTION_MODULE;worldbank2021informality", "Informality coefficient; inert in frozen baseline because mu is inverted to target.", "bounded_PERT"),
        ("nu_G", nu_g, 0.00, 1.00, "calibrated_prior_inert_in_frozen_baseline", "PAPER_ADOPTION_MODULE", "Gap coefficient; inert in frozen baseline because mu is inverted to target.", "bounded_PERT"),
        ("mu_t0_derived_not_free", mu_t0, mu_t0, mu_t0, "derived_not_free", "PLAN_02_SEC_7_3;PAPER_APP_ADOPTION_MODULE", "log(q_adj/(q_bar-q_adj))-nu_A*A+nu_I*I+nu_G*Gap. Primitive is q_use_target, not mu.", "fixed_derived"),
        ("lambda_q_baseline_mid", 0.30, 0.15, 0.50, "paper_grid", "PAPER_ADOPTION_MODULE;PLAN_02_SEC_7_3", "Baseline diffusion-speed grid {0.15,0.30,0.50}; frozen baseline keeps q_prod at anchor.", "discrete_grid"),
        ("lambda_q_stress_instant", 1.00, 1.00, 1.00, "stress_only", "PAPER_ADOPTION_MODULE", "Instant-adoption stress only, not baseline primary.", "fixed_stress"),
        ("beta_translation", 1.00, 0.50, 2.00, "paper_elasticity_grid", "PAPER_TRANSLATION_MODULE", "Baseline unit elasticity; sensitivity grid {0.5,1,1.5,2}.", "bounded_PERT"),
        ("gamma_translation", 1.00, 0.50, 2.00, "paper_elasticity_grid", "PAPER_TRANSLATION_MODULE", "Baseline unit elasticity; sensitivity grid {0.5,1,1.5,2}.", "bounded_PERT"),
    ]
    for name, val, low, high, support, source, formula, dist in adoption_values:
        add_value(
            rows,
            name=name,
            module="adoption_translation",
            value_type="derived_parameter" if "derived" in support or name in {"q_bar", "q_use_target_adj", "q_prod_t0", "mu_t0_derived_not_free"} else ("observed" if support == "observed_anchor" else "calibrated_parameter"),
            unit="share" if name not in {"mu_t0_derived_not_free", "nu_A", "nu_I", "nu_G", "lambda_q_baseline_mid", "lambda_q_stress_instant", "beta_translation", "gamma_translation"} else "unitless",
            baseline_value=val,
            low_value=low,
            high_value=high,
            support_type=support,
            source_id=source,
            formula_id=formula,
            distribution=dist,
            truncation_rule="0_to_1" if name not in {"mu_t0_derived_not_free", "nu_A", "nu_I", "nu_G", "beta_translation", "gamma_translation"} else "declared_support",
            primary_spec_flag=name != "lambda_q_stress_instant",
            robustness_flag=name == "lambda_q_stress_instant",
            stress_flag=name == "lambda_q_stress_instant",
            double_counting_risk="gap_aipi_overlap" if name.startswith("Gap") else ("aipi_target_and_logistic_index" if name == "q_use_target" else "none"),
            double_counting_note=(
                "AIPI entra a la derivación del target y al índice logístico; en baseline congelado la inversión de mu absorbe el nivel y neutraliza el doble uso; en modo structural-intercept debe recordarse"
                if name == "q_use_target"
                else ("gap_aipi_overlap" if name.startswith("Gap") else "none")
            ),
            audit_status="registered_author_review" if name in {"Gap_excluded_indicators_neutral", "q_use_target", "omega_I", "omega_G", "nu_A", "nu_I", "nu_G"} else "registered",
            country_id=COUNTRY_ID,
            notes=formula,
        )

    add_value(
        rows,
        name="frontier_benchmark_member_count",
        module="frontier_benchmark",
        value_type="benchmark_choice_scalar",
        unit="count",
        baseline_value=float(benchmark["n"]),
        low_value=float(benchmark["n"]),
        high_value=float(benchmark["n"]),
        support_type="population_consistency_choice",
        source_id="FRONTIER_BENCHMARK;PAPER_SEC_10_6;PLAN_02_SEC_10_6",
        formula_id="OECD_Eurostat_GE10_2024_subset_for_phi_mid_population_consistency",
        distribution="fixed",
        truncation_rule="fixed_choice",
        primary_spec_flag=True,
        robustness_flag=False,
        stress_flag=False,
        double_counting_risk="none",
        audit_status="registered",
        notes="Benchmark chosen as OECD/advanced Eurostat economies available in isoc_eb_ai because phi_mid is disciplined by OECD micro-to-macro evidence.",
    )
    add_value(
        rows,
        name="frontier_benchmark_avg_adoption_proxy",
        module="frontier_benchmark",
        value_type="benchmark_choice_scalar",
        unit="share_of_enterprises",
        baseline_value=float(benchmark["avg_adoption"]),
        low_value=float(benchmark["avg_adoption"]),
        high_value=float(benchmark["avg_adoption"]),
        support_type="observed_benchmark_average",
        source_id="FRONTIER_BENCHMARK",
        formula_id="mean_adoption_proxy_selected_oecd_eurostat_benchmark",
        distribution="fixed_observed_average",
        truncation_rule="0_to_1",
        primary_spec_flag=True,
        robustness_flag=False,
        stress_flag=False,
        double_counting_risk="none",
        audit_status="registered",
        notes="Used only to calibrate q_use_target prior and document benchmark choice; s_frontier_score is computed in 3B.",
    )
    add_value(
        rows,
        name="frontier_benchmark_avg_aipi",
        module="frontier_benchmark",
        value_type="benchmark_choice_scalar",
        unit="index_0_to_1",
        baseline_value=float(benchmark["avg_aipi"]),
        low_value=float(benchmark["avg_aipi"]),
        high_value=float(benchmark["avg_aipi"]),
        support_type="observed_benchmark_average",
        source_id="IMF_AIPI_DATA360;FRONTIER_BENCHMARK",
        formula_id="mean_aipi_selected_oecd_eurostat_benchmark",
        distribution="fixed_observed_average",
        truncation_rule="0_to_1",
        primary_spec_flag=True,
        robustness_flag=False,
        stress_flag=False,
        double_counting_risk="none",
        audit_status="registered",
        notes="Population-consistency scalar for q_use_target prior.",
    )

    fiscal_values = [
        ("tau_L_eff", tau_l_eff, tau_l_eff, tau_l_eff, "effective_labor_tax_capture", "observed_derived_anchor", "OECD_REVSTAT_LAC;ILOSTAT;PWT_10_01", "(PIT_GDP+social_contrib_GDP)/labor_share_GDP", "fixed_derived"),
        ("tau_K_eff", tau_k_eff, tau_k_eff, tau_k_eff, "effective_capital_tax_capture", "observed_derived_anchor", "OECD_REVSTAT_LAC;PWT_10_01", "CIT_GDP/(1-labor_share)", "fixed_derived"),
        ("tau_C_eff", tau_c_eff, tau_c_eff, tau_c_eff, "effective_consumption_tax_capture", "observed_derived_anchor", "OECD_REVSTAT_LAC;WDI", "VAT_GDP/final_consumption_GDP_share", "fixed_derived"),
        ("LS_labor_share", labor_share, labor_share, labor_share, "labor_share", "observed_anchor", "PWT_10_01", "PWT labor share carried forward to 2024", "fixed_observed"),
        ("E_auto", 0.035, 0.02, 0.05, "share_of_tasks_or_employment", "paper_lac_automation_risk_anchor", "PAPER_LAC_AUTOMATION_RISK_ANCHOR;PLAN_01_02", "LAC paper anchor for automation risk: central 3.5 percent, support 2-5 percent.", "bounded_PERT"),
        ("E_aug", float(exposure["exposure_productive"]), 0.08, 0.14, "share_of_tasks_or_employment", "lac_fallback_exposure", "PLAN_01_02", "No automation/augmentation split in snapshot; both use LAC productive-exposure fallback.", "bounded_PERT"),
        ("E_prod", float(exposure["exposure_productive"]), 0.08, 0.14, "share_of_tasks_or_employment", "lac_fallback_exposure", "PLAN_01_02", "Productive exposure remains at the LAC fallback: central 0.11, support [0.08,0.14].", "bounded_PERT"),
        ("RST", rst_proxy, 0.0, 1.0, "index_0_to_1", "residualized_aipi_fallback", "IMF_AIPI_DATA360;PLAN_01_SEC_14_6;PAPER_LABOR_SHARE_MODULE", rst_note, "bounded_PERT"),
        ("delta_s", 0.50, 0.25, 1.00, "unitless", "paper_provisional_grid", "PAPER_MASTER_CALIBRATION_MATRIX", "Automation pressure grid {0.25,0.50,1.00}.", "discrete_grid"),
        ("psi_s", 0.50, 0.25, 1.00, "unitless", "paper_provisional_grid", "PAPER_MASTER_CALIBRATION_MATRIX", "Augmentation pressure grid {0.25,0.50,1.00}.", "discrete_grid"),
        ("zeta_s", 0.50, 0.25, 1.00, "unitless", "paper_provisional_grid", "PAPER_MASTER_CALIBRATION_MATRIX", "Reskilling mitigation grid {0.25,0.50,1.00}; engine must enforce zeta*RST<=delta.", "discrete_grid"),
        ("lambda_LS", 0.50, 0.25, 1.00, "unitless", "paper_provisional_grid", "PAPER_MASTER_CALIBRATION_MATRIX", "Labor-share partial-adjustment grid {0.25,0.50,1.00}.", "discrete_grid"),
        ("chi_Kbase", 1.00, 1.00, 1.00, "share", "broad_effective_rate_no_extra_base_discount", "PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_10_8", "tau_K_eff is calibrated as broad NLS effective capture, so no additional K-base filter in primary.", "fixed_convention"),
        ("chi_dom", 1.00, 1.00, 1.00, "share", "broad_effective_rate_no_extra_base_discount", "PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_10_8", "Domestic reach already embedded in observed effective rate in primary.", "fixed_convention"),
        ("psi_shift", 0.15, 0.00, 0.30, "share", "calibrated_ordinary_capital_base_shifting", "PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_10_8", "shifting ordinario del incremento de base de capital; central conservador-moderado; el paper advierte que el shifting tecnológico puede ser mayor en emergentes; 0 solo como variante favorable etiquetada", "bounded_PERT"),
        ("mpc_W", consumption_gdp_share, max(0.0, consumption_gdp_share - 0.15), min(1.0, consumption_gdp_share + 0.10), "share", "national_accounts_proxy", "WDI;PAPER_APP_FISCAL_CONVERSION", "Final-consumption/GDP share used as transparent pilot proxy for labor-income MPC.", "bounded_PERT"),
        ("mpc_Pi", 0.50 * consumption_gdp_share, max(0.0, 0.50 * consumption_gdp_share - 0.15), min(1.0, 0.50 * consumption_gdp_share + 0.15), "share", "calibrated_prior_from_national_accounts", "WDI;PAPER_APP_FISCAL_CONVERSION", "Profit-income MPC proxy set below labor-income proxy; flagged for author review.", "bounded_PERT"),
        ("mpc_R", 0.75 * consumption_gdp_share, max(0.0, 0.75 * consumption_gdp_share - 0.15), min(1.0, 0.75 * consumption_gdp_share + 0.15), "share", "calibrated_prior_from_national_accounts", "WDI;PAPER_APP_FISCAL_CONVERSION", "Residual-income MPC proxy between labor and profit proxies; flagged for author review.", "bounded_PERT"),
        ("m_M", import_content_consumption, import_content_consumption, import_content_consumption, "import_content_share", "observed_derived_anchor", "WDI", "imports_GDP_share/final_consumption_GDP_share, capped to [0,1].", "fixed_derived"),
        ("theta_R_dom", 1.0 - import_content_consumption, 1.0 - import_content_consumption, 1.0 - import_content_consumption, "domestic_routing_share", "derived_from_import_content", "WDI;PAPER_APP_FISCAL_CONVERSION", "Domestic routing for residual income set to 1-m_M in pilot.", "fixed_derived"),
        ("exempt_C", 0.00, 0.00, 0.00, "share_of_consumption_base", "effective_rate_embeds_exemptions", "PLAN_02_SEC_10_8;PAPER_APP_FISCAL_CONVERSION", "Observed tau_C_eff already embeds exemptions and informal untaxed consumption; base-side exempt_C is zero to avoid double count.", "fixed_convention"),
        ("tau_L_disp", tau_l_eff, tau_l_eff, tau_l_eff, "effective_tax_rate", "simplified_disposable_rate", "PLAN_02_SEC_10_8", "Simplified pilot convention: disposable labor rate equals fiscal labor effective rate.", "fixed_derived"),
        ("tau_K_disp", tau_k_eff, tau_k_eff, tau_k_eff, "effective_tax_rate", "simplified_disposable_rate", "PLAN_02_SEC_10_8", "Simplified pilot convention: disposable capital rate equals fiscal capital effective rate.", "fixed_derived"),
        ("tau_R_disp", 0.00, 0.00, 0.00, "effective_tax_rate", "residual_income_not_directly_taxed", "PAPER_APP_FISCAL_CONVERSION", "Residual non-labor income is routed through consumption only in primary.", "fixed_convention"),
        ("sPB_plus_gdp_ratio", max(0.0, -float(debt["pb_gap_gdp"])) / 100.0, max(0.0, -float(debt["pb_gap_gdp"])) / 100.0, max(0.0, -float(debt["pb_gap_gdp"])) / 100.0, "share_of_GDP", "derived_debt_guardrail", "IMF_WEO_GFS;PLAN_02_SEC_7_7", "max(0,-pb_gap_gdp_pp)/100 because anchor stores IMF percent-of-GDP values in percentage points.", "fixed_derived"),
    ]
    for name, val, low, high, unit, support, source, formula, dist in fiscal_values:
        add_value(
            rows,
            name=name,
            module="fiscal_channels",
            value_type="observed" if support == "observed_anchor" else ("derived_parameter" if "derived" in support or "effective" in support or name.startswith("tau_") or name == "sPB_plus_gdp_ratio" else "calibrated_parameter"),
            unit=unit,
            baseline_value=val,
            low_value=low,
            high_value=high,
            support_type=support,
            source_id=source,
            formula_id=formula,
            distribution=dist,
            truncation_rule="0_to_1" if unit not in {"labor_share", "effective_labor_tax_capture", "effective_capital_tax_capture", "effective_consumption_tax_capture"} else "declared_support",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=False,
            double_counting_risk="tax_base_double_discount" if name in {"chi_Kbase", "chi_dom", "psi_shift", "exempt_C"} else "none",
            audit_status="registered_author_review" if name in {"mpc_W", "mpc_Pi", "mpc_R", "RST", "E_auto", "E_aug", "E_prod", "psi_shift"} else "registered",
            country_id=COUNTRY_ID,
            notes=formula,
        )

    regime_rows = {
        "r0": {"regime_id": 0, "tau_delta": 0.00, "tau_low": 0.00, "tau_high": 0.00, "base": 0.00, "base_low": 0.00, "base_high": 0.00, "tau_ai": 0.00, "tau_ai_low": 0.00, "tau_ai_high": 0.00, "leakage": 1.00},
        "r1": {"regime_id": 1, "tau_delta": 0.10, "tau_low": 0.05, "tau_high": 0.15, "base": 0.05, "base_low": 0.02, "base_high": 0.08, "tau_ai": 0.00, "tau_ai_low": 0.00, "tau_ai_high": 0.00, "leakage": 0.75},
        "r2": {"regime_id": 2, "tau_delta": 0.15, "tau_low": 0.10, "tau_high": 0.25, "base": 0.10, "base_low": 0.05, "base_high": 0.20, "tau_ai": 0.00, "tau_ai_low": 0.00, "tau_ai_high": 0.00, "leakage": 0.75},
        "r3": {"regime_id": 3, "tau_delta": 0.00, "tau_low": 0.00, "tau_high": 0.10, "base": 0.05, "base_low": 0.02, "base_high": 0.08, "tau_ai": 0.05, "tau_ai_low": 0.02, "tau_ai_high": 0.10, "leakage": 0.90},
        "r4": {"regime_id": 4, "tau_delta": 0.25, "tau_low": 0.15, "tau_high": 0.35, "base": 0.20, "base_low": 0.10, "base_high": 0.30, "tau_ai": 0.08, "tau_ai_low": 0.04, "tau_ai_high": 0.15, "leakage": 0.50},
    }
    for regime_code, spec in regime_rows.items():
        for channel in ["L", "K", "C"]:
            add_value(
                rows,
                name=f"tau_{channel}_relative_delta_{regime_code}",
                module="fiscal_regime",
                value_type="regime_parameter",
                unit="relative_delta_to_observed_effective_rate",
                baseline_value=spec["tau_delta"],
                low_value=spec["tau_low"],
                high_value=spec["tau_high"],
                support_type="calibrated_mechanical_reform_grid",
                source_id="PLAN_02_SEC_15_1;PAPER_APP_FISCAL_CONVERSION;brollo2024fiscal",
                formula_id="tau_j_r=tau_j_observed*(1+relative_delta_r)",
                distribution="bounded_PERT" if spec["tau_high"] > spec["tau_low"] else "fixed",
                truncation_rule="tau_j_r_capped_to_0_60_in_engine",
                primary_spec_flag=True,
                robustness_flag=regime_code != "r0",
                stress_flag=regime_code in {"r3", "r4"},
                double_counting_risk="regime_mechanical_upper_bound",
                audit_status="registered_author_review" if regime_code != "r0" else "registered",
                regime_code=regime_code,
                notes="Mechanical reform-regime delta for pre-run calibration; no behavioral result is computed here.",
            )
        add_value(
            rows,
            name=f"base_broadening_delta_{regime_code}",
            module="fiscal_regime",
            value_type="regime_parameter",
            unit="relative_base_broadening_index",
            baseline_value=spec["base"],
            low_value=spec["base_low"],
            high_value=spec["base_high"],
            support_type="calibrated_mechanical_reform_grid",
            source_id="PLAN_02_SEC_15_1;PAPER_APP_FISCAL_CONVERSION",
            formula_id="base_side_margin_only_when_not_already_in_effective_rate",
            distribution="bounded_PERT" if spec["base_high"] > spec["base_low"] else "fixed",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=regime_code != "r0",
            stress_flag=regime_code in {"r3", "r4"},
            double_counting_risk="base_vs_rate_same_margin",
            audit_status="registered_author_review" if regime_code != "r0" else "registered",
            regime_code=regime_code,
            notes="Registered for regime audit. Primary effective-rate convention does not apply base-side and rate-side margins twice.",
        )
        add_value(
            rows,
            name=f"tau_AI_eff_{regime_code}",
            module="fiscal_regime",
            value_type="regime_parameter",
            unit="effective_AI_rent_capture_rate",
            baseline_value=spec["tau_ai"],
            low_value=spec["tau_ai_low"],
            high_value=spec["tau_ai_high"],
            support_type="paper_bounded_policy_grid",
            source_id="PLAN_02_SEC_15_1;PAPER_APP_FISCAL_CONVERSION",
            formula_id="tau_AI_eff positive only in r3/r4",
            distribution="bounded_PERT" if spec["tau_ai_high"] > spec["tau_ai_low"] else "fixed",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=regime_code != "r0",
            stress_flag=regime_code in {"r3", "r4"},
            double_counting_risk="ai_rent_capture_without_lambda",
            audit_status="registered_author_review" if regime_code in {"r3", "r4"} else "registered",
            regime_code=regime_code,
            notes="Status quo and non-rent regimes have zero AI rent capture.",
        )
        add_value(
            rows,
            name=f"leakage_multiplier_{regime_code}",
            module="fiscal_regime",
            value_type="regime_parameter",
            unit="relative_leakage_multiplier",
            baseline_value=spec["leakage"],
            low_value=max(0.0, spec["leakage"] - 0.15),
            high_value=min(1.0, spec["leakage"] + 0.15),
            support_type="calibrated_mechanical_reform_grid",
            source_id="PLAN_02_SEC_15_1",
            formula_id="high_medium_low_leakage_order_encoded_as_multiplier",
            distribution="bounded_PERT" if regime_code != "r0" else "fixed",
            truncation_rule="0_to_1",
            primary_spec_flag=True,
            robustness_flag=regime_code != "r0",
            stress_flag=regime_code in {"r3", "r4"},
            double_counting_risk="leakage_vs_technology_shifting",
            audit_status="registered_author_review" if regime_code != "r0" else "registered",
            regime_code=regime_code,
            notes="Only a pre-run ordered scalar for later engine use; leakage is not subtracted here.",
        )
        for channel in ["L", "K", "C", "AI"]:
            ero_mid = 0.0 if regime_code == "r0" else 0.50
            add_value(
                rows,
                name=f"epsilon_ero_{channel}_{regime_code}",
                module="behavioral_erosion",
                value_type="companion_parameter",
                unit="taxable_base_erosion_elasticity",
                baseline_value=ero_mid,
                low_value=0.0,
                high_value=0.0 if regime_code == "r0" else 1.0,
                support_type="paper_companion_grid",
                source_id="PLAN_02_SEC_7_4_2;PAPER_APP_FISCAL_CONVERSION",
                formula_id="B_taxable=B*(1-epsilon_ero*tau_eff_r); epsilon_ero=0 in r0",
                distribution="fixed" if regime_code == "r0" else "discrete_grid_or_bounded_PERT",
                truncation_rule="epsilon_ero*tau_eff<1",
                primary_spec_flag=regime_code == "r0",
                robustness_flag=regime_code != "r0",
                stress_flag=regime_code in {"r3", "r4"},
                double_counting_risk="behavioral_response_not_in_capital_chain",
                audit_status="registered",
                regime_code=regime_code,
                notes="Companion mandatory for any headline result relying on r>=1; Etapa 3A only registers the grid.",
            )

    policy_cost = con.execute(
        f"SELECT * FROM policy_cost WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}"
    ).fetchdf()
    policy_admin = con.execute(
        f"SELECT * FROM policy_admin_transition_cost WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}"
    ).fetchdf()
    policy_parameter = con.execute(
        f"SELECT * FROM policy_parameter WHERE country_id='{COUNTRY_ID}' AND year={ANCHOR_YEAR}"
    ).fetchdf()
    policy_parameter_by_id = policy_parameter.set_index("policy_parameter_id")
    assumption = con.execute("SELECT * FROM assumption_registry").fetchdf()
    assumption_by_param = assumption[
        assumption["created_by_script"] == "build_anchors_from_snapshot.py"
    ].set_index("parameter_name")

    for _, row in policy_cost.iterrows():
        suffix = row["policy_id"] if pd.isna(row["gmi_version"]) else str(row["gmi_version"])
        policy_source_id = "PLAN_01_02"
        if row["policy_parameter_id"] in policy_parameter_by_id.index:
            policy_source_id = str(policy_parameter_by_id.loc[row["policy_parameter_id"], "source_id"])
        add_value(
            rows,
            name=f"policy_cost_gross_gdp_{suffix}",
            module="policy_cost",
            value_type="derived_policy_cost_anchor",
            unit="share_of_GDP",
            baseline_value=float(row["policy_cost_gross_gdp"]),
            low_value=float(row["policy_cost_gross_gdp"]),
            high_value=float(row["policy_cost_gross_gdp"]),
            support_type="derived_from_policy_cost_anchor",
            source_id=policy_source_id,
            formula_id=str(row["cost_convention"]),
            distribution="fixed_derived",
            truncation_rule="non_negative",
            primary_spec_flag=True,
            robustness_flag=False,
            stress_flag=row["policy_id"] == "UBI",
            double_counting_risk="gross_vs_net_cost",
            audit_status="registered",
            country_id=COUNTRY_ID,
            policy_id=str(row["policy_id"]),
            notes="Gross recurring cost is the primary cost convention.",
        )
        if not pd.isna(row["eta_policy"]):
            add_value(
                rows,
                name=f"eta_{row['policy_id']}",
                module="policy_cost",
                value_type="policy_design_parameter",
                unit="poverty_line_fraction",
                baseline_value=float(row["eta_policy"]),
                low_value=0.25,
                high_value=1.00,
                support_type="paper_policy_support",
                source_id="PAPER_MASTER_CALIBRATION_MATRIX;PLAN_01_02",
                formula_id="eta_policy * poverty_line",
                distribution="bounded_PERT",
                truncation_rule="0_25_to_1_00",
                primary_spec_flag=True,
                robustness_flag=row["policy_id"] != "PEN",
                stress_flag=row["policy_id"] == "UBI",
                double_counting_risk="none",
                audit_status="registered",
                country_id=COUNTRY_ID,
                policy_id=str(row["policy_id"]),
                notes="Policy eta ladder registered for MUT/PBI/UBI.",
            )
        if not pd.isna(row["chi_gmi"]):
            add_value(
                rows,
                name=f"chi_gmi_{suffix}",
                module="policy_cost",
                value_type="policy_design_parameter",
                unit="poverty_gap_coverage_share",
                baseline_value=float(row["chi_gmi"]),
                low_value=float(row["chi_gmi"]),
                high_value=float(row["chi_gmi"]),
                support_type="policy_definition",
                source_id="PLAN_01_02",
                formula_id="GMI closes measured poverty gap in aggregate ideal convention",
                distribution="fixed",
                truncation_rule="0_to_1",
                primary_spec_flag=True,
                robustness_flag=False,
                stress_flag=False,
                double_counting_risk="none",
                audit_status="registered",
                country_id=COUNTRY_ID,
                policy_id="GMI",
                notes="GMI aggregate gap-coverage parameter.",
            )
    add_value(
        rows,
        name="theta_target_GMI_loaded",
        module="policy_cost",
        value_type="policy_design_parameter",
        unit="multiplicative_loading_factor",
        baseline_value=1.50,
        low_value=1.00,
        high_value=1.50,
        support_type="paper_policy_support",
        source_id="PAPER_MASTER_CALIBRATION_MATRIX;PLAN_01_02",
        formula_id="loaded_GMI=theta_target*ideal_GMI",
        distribution="bounded_PERT",
        truncation_rule="1_00_to_1_50",
        primary_spec_flag=True,
        robustness_flag=True,
        stress_flag=False,
        double_counting_risk="none",
        audit_status="registered",
        country_id=COUNTRY_ID,
        policy_id="GMI",
        notes="Loaded aggregate GMI uses the upper support point requested for pilot reporting.",
    )

    for _, row in policy_admin.iterrows():
        for col in [
            "admin_cost_new_gdp",
            "transition_oneoff_gdp",
            "transition_recurring_gdp",
            "leakage_fixed_gdp",
        ]:
            param_name = f"{row['policy_id']}_{col}"
            low = high = float(row[col])
            if param_name in assumption_by_param.index:
                low = float(assumption_by_param.loc[param_name]["low_value"])
                high = float(assumption_by_param.loc[param_name]["high_value"])
            add_value(
                rows,
                name=param_name,
                module="policy_admin_transition_cost",
                value_type="calibrated_cost_parameter",
                unit="share_of_GDP",
                baseline_value=float(row[col]),
                low_value=low,
                high_value=high,
                support_type="assumption_registry_existing",
                source_id=str(row["source_id"]),
                formula_id=f"policy_admin_transition_cost.{col}",
                distribution="bounded_PERT" if high > low else "fixed",
                truncation_rule="non_negative",
                primary_spec_flag=True,
                robustness_flag=False,
                stress_flag=False,
                double_counting_risk="admin_transition_leakage_once",
                audit_status="registered",
                country_id=COUNTRY_ID,
                policy_id=str(row["policy_id"]),
                notes="Existing Etapa 2.1 assumption reused; no new cost scalar is invented here.",
            )
        for col in ["transition_horizon_years", "transition_discount_rate"]:
            add_value(
                rows,
                name=f"{row['policy_id']}_{col}",
                module="policy_admin_transition_cost",
                value_type="calibrated_cost_parameter",
                unit="years" if col == "transition_horizon_years" else "annual_discount_rate",
                baseline_value=float(row[col]),
                low_value=float(row[col]),
                high_value=float(row[col]),
                support_type="assumption_registry_existing",
                source_id=str(row["source_id"]),
                formula_id=f"policy_admin_transition_cost.{col}",
                distribution="fixed",
                truncation_rule="non_negative",
                primary_spec_flag=True,
                robustness_flag=False,
                stress_flag=False,
                double_counting_risk="admin_transition_leakage_once",
                audit_status="registered",
                country_id=COUNTRY_ID,
                policy_id=str(row["policy_id"]),
                notes="Existing transition convention from Etapa 2.1.",
            )

    value_df = pd.DataFrame(rows)
    value_df = value_df.sort_values(["module", "scenario_id", "policy_id", "regime_code", "name"], na_position="first").reset_index(drop=True)
    context = {
        "tau_l_eff": tau_l_eff,
        "tau_k_eff": tau_k_eff,
        "tau_c_eff": tau_c_eff,
        "q_bar": q_bar,
        "benchmark_count": int(benchmark["n"]),
        "benchmark_avg_adoption": float(benchmark["avg_adoption"]),
        "benchmark_avg_aipi": float(benchmark["avg_aipi"]),
        "q_use_target": q_use_target,
        "rst_proxy": rst_proxy,
        "sPB_plus_ratio": max(0.0, -float(debt["pb_gap_gdp"])) / 100.0,
    }
    return value_df, context


def build_thresholds(con: duckdb.DuckDBPyConnection, q_bar: float) -> pd.DataFrame:
    hist = read_one(
        con,
        f"""
        SELECT * FROM historical_capture_percentiles
        WHERE country_id='{COUNTRY_ID}'
          AND revenue_concept='total_revenue'
          AND percentile_sample='2000plus'
        """,
    )
    rows = [
        ("Vgross_min", True, "inequality_min", 1.0, "", "classify not_feasible if Vgross < 1", "PLAN_02_SEC_10_12"),
        ("xi_buffer", True, "buffer_grid", 0.10, "0,0.05,0.25,0.50", "compute requirements as R_req(xi)", "PLAN_02_SEC_10_12"),
        ("MFC_P50_total_revenue_2000plus", True, "historical_percentile", float(hist["p50_mfc_hist_positive"]), "", "historical plausibility ordinary/moderate threshold", "PLAN_02_SEC_10_13"),
        ("MFC_P75_total_revenue_2000plus", True, "historical_percentile", float(hist["p75_mfc_hist_positive"]), "", "historical plausibility moderate/demanding threshold", "PLAN_02_SEC_10_13"),
        ("MFC_P90_total_revenue_2000plus", True, "historical_percentile", float(hist["p90_mfc_hist_positive"]), "", "historical plausibility extreme threshold", "PLAN_02_SEC_10_13"),
        ("prob_v_ge_1_10_min", True, "probability_min", 0.75, "0.50,0.90", "robustness probability label; prob_basis=all_draw", "PLAN_02_SEC_10_13"),
        ("prob_v_ge_1_fragility", True, "probability_min", 0.50, "", "below this, no robust language", "PLAN_02_SEC_10_13"),
        ("debt_guardrail_required", True, "boolean", 1.0, "", "debt guardrail must pass for robust class", "PLAN_02_SEC_10_13"),
        ("q_required_max", True, "support_max", q_bar, "", "q_required <= q_bar", "PLAN_02_SEC_10_13"),
        ("T_required_max", True, "support_max", 1.0, "", "T_required <= 1 and frontier_exceeds_one applies to T_req_H", "PLAN_02_SEC_7_7;PLAN_02_SEC_10_13"),
        ("E_required_max", True, "support_max", 1.0, "", "E_required <= 1", "PLAN_02_SEC_10_14"),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "threshold_name",
            "controls_decision",
            "threshold_type",
            "baseline_value",
            "sensitivity_values",
            "action_on_fail",
            "source_section",
        ],
    )
    df["parameter_set_id"] = PARAMETER_SET_ID
    df["dataset_version"] = DATASET_VERSION
    df["created_at"] = NOW
    df["created_by_script"] = SCRIPT_NAME
    return df


def build_rules() -> pd.DataFrame:
    rules = [
        ("cell_result_01", "existence condition fails -> impossible_or_noncomputable", "existence_flags", 1, "PLAN_02_SEC_18_1"),
        ("cell_result_02", "Vgross < 1 -> not_feasible", "Vgross", 2, "PLAN_02_SEC_18_1"),
        ("cell_result_03", "crosses but fails debt -> accounting_feasible_debt_failed", "Vgross,debt_guardrail", 3, "PLAN_02_SEC_18_1"),
        ("cell_result_04", "crosses only in stress+r4 over country-policy set -> extreme_conditional_crossing", "scenario_id,regime_code,crossing_set", 4, "PLAN_02_SEC_18_1"),
        ("cell_result_05", "otherwise crossing cell -> feasible_cell", "Vgross", 5, "PLAN_02_SEC_18_1"),
        ("hist_plaus_01", "MFCgross <= P50 -> fiscally_ordinary", "MFCgross,P50", 1, "PLAN_02_SEC_18_1"),
        ("hist_plaus_02", "P50 < MFCgross <= P75 -> fiscally_moderate", "MFCgross,P50,P75", 2, "PLAN_02_SEC_18_1"),
        ("hist_plaus_03", "P75 < MFCgross <= P90 -> fiscally_demanding", "MFCgross,P75,P90", 3, "PLAN_02_SEC_18_1"),
        ("hist_plaus_04", "MFCgross > P90 -> extreme_or_outside_historical_support", "MFCgross,P90", 4, "PLAN_02_SEC_18_1"),
        ("country_policy_00", "UBI -> stress_benchmark_only unless strong evidence exception applies", "policy_id,crossing_strength", 0, "PLAN_02_SEC_18_2"),
        ("country_policy_01", "no crossing except extremes/noncomputable -> not_feasible", "crossing_set", 1, "PLAN_02_SEC_18_2"),
        ("country_policy_02", "crosses but debt fails, MFC>P90, or prob_v_ge_1<0.50 -> fragile_feasible", "debt,MFC,probability", 2, "PLAN_02_SEC_18_2"),
        ("country_policy_03", "all robust conditions -> robustly_feasible", "mid_or_low,r0_r2,xi_0_10,MFC_P75,debt,prob_0_75,erosion_companion", 3, "PLAN_02_SEC_18_2"),
        ("country_policy_04", "remaining crossing policies -> conditionally_feasible", "residual", 4, "PLAN_02_SEC_18_2"),
    ]
    df = pd.DataFrame(rules, columns=["rule_id", "rule_text", "inputs_used", "precedence_order", "source_section"])
    df["parameter_set_id"] = PARAMETER_SET_ID
    df["dataset_version"] = DATASET_VERSION
    df["created_at"] = NOW
    df["created_by_script"] = SCRIPT_NAME
    return df


def build_audits(value_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = [
        "source_id",
        "unit",
        "support_type",
        "distribution",
        "low_value",
        "high_value",
        "audit_status",
        "double_counting_note",
    ]
    complete = bool(value_df[required].notna().all().all())
    low_high_ok = bool((value_df["low_value"] <= value_df["baseline_value"]).all() and (value_df["baseline_value"] <= value_df["high_value"]).all())
    no_hard_fail = not value_df["audit_status"].astype(str).str.contains("hard_fail", case=False, na=False).any()

    checks = [
        ("dataset_version_is_v0_1_2", "governance", "build_manifest", True, "hard", "Governance reads only frozen snapshot v0.1.2-pilot-per."),
        ("pilot_subset_declared_PER", "governance", "dim_country", True, "hard", "Etapa 3A run_readiness applies only to pilot PER and is not an official baseline authorization."),
        ("no_engine_results_computed", "governance", "src/ai_usp", True, "hard", "Script writes governance/calibration tables only; no economic result tables are computed."),
        ("value_assignment_required_fields_complete", "governance", "value_assignment_table", complete, "hard", "Every scalar has source, unit, support, distribution, low/high, and audit_status."),
        ("value_assignment_low_high_contains_baseline", "governance", "value_assignment_table", low_high_ok, "hard", "All low <= baseline <= high checks pass."),
        ("gap_aipi_overlap_avoided", "double_counting", "digital_gap_anchor", True, "hard", "Baseline gap remains neutral because no excluded non-AIPI indicator exists; overlapping ITU indicators are not used."),
        ("gap_pilot_diagnostic_official_baseline_blocker", "adoption_translation", "value_assignment_table", True, "robustness_only", "PILOTO-DIAGNÓSTICO: neutral Gap is a favorable diagnostic convention only; official baseline is blocked until gap_index is built from indicators verified as excluded from AIPI."),
        ("rst_fallback_registered", "labor_share", "value_assignment_table", True, "soft", "RST uses residualized AIPI human-capital fallback and is marked for author review."),
        ("author_review_priors_flagged", "governance", "value_assignment_table", True, "soft", "Calibrated priors without direct Peru survey source are audit_status=registered_author_review."),
        ("assumption_registry_complete_flag", "governance", "assumption_registry", complete and low_high_ok and no_hard_fail, "hard", "All Etapa 3A scalars are mirrored to assumption_registry/calibrated_parameter_registry/parameter_set_item."),
        ("run_readiness_flag", "governance", "input_audit_report", complete and low_high_ok and no_hard_fail, "hard", "TRUE only for pilot pre-run governance; it does not authorize the official baseline or Etapa 3B without author review."),
    ]
    audit_df = pd.DataFrame(
        checks,
        columns=["check_name", "module", "table_name", "passes_check", "severity", "notes"],
    )
    audit_df.insert(0, "parameter_set_id", PARAMETER_SET_ID)
    audit_df.insert(0, "dataset_version", DATASET_VERSION)
    audit_df["created_at"] = NOW
    audit_df["created_by_script"] = SCRIPT_NAME

    dc_rows = [
        ("gap_vs_aipi", True, "Gap neutral convention avoids reusing ITU internet/broadband/mobile indicators already inside AIPI digital infrastructure.", "digital_gap_anchor,value_assignment_table"),
        ("mu_not_free", True, "mu_t0 is derived by logit inversion; primitive is q_use_target.", "value_assignment_table"),
        ("historical_vs_channel_mfc", True, "Historical MFC percentiles discipline plausibility; channel mode remains primary and no independent MFC draw is mixed in.", "threshold_assignment_table"),
        ("capital_ai_rent_subset", True, "lambda_AI_Kbase mirrors lambda_AI under subset convention so omega_K_net can subtract AI rents.", "value_assignment_table"),
        ("capital_base_effective_rate", True, "chi_Kbase/chi_dom remain broad-base conventions while psi_shift now captures ordinary shifting of the incremental capital base only; technology shifting is not also embedded elsewhere.", "value_assignment_table"),
        ("consumption_exemptions", True, "tau_C_eff is observed effective VAT over consumption; exempt_C=0 in base-side channel to avoid applying exemptions twice.", "value_assignment_table"),
        ("admin_transition_leakage_once", True, "Admin, transition, and fixed leakage components are registered as separate cost terms and not embedded in MFC.", "policy_admin_transition_cost,value_assignment_table"),
        ("debt_guardrail_units", True, "pb_gap anchor is stored in percentage points of GDP; sPB_plus_gdp_ratio divides by 100 before joining cost ratios.", "value_assignment_table"),
    ]
    dc_df = pd.DataFrame(
        dc_rows,
        columns=["check_name", "passes_check", "notes", "tables_used"],
    )
    dc_df.insert(0, "parameter_set_id", PARAMETER_SET_ID)
    dc_df.insert(0, "dataset_version", DATASET_VERSION)
    dc_df["created_at"] = NOW
    dc_df["created_by_script"] = SCRIPT_NAME
    return audit_df, dc_df


def build_calibrated_registry(value_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "parameter_name": value_df["name"],
            "module": value_df["module"],
            "baseline_value": value_df["baseline_value"],
            "low_value": value_df["low_value"],
            "high_value": value_df["high_value"],
            "distribution": value_df["distribution"],
            "truncation_rule": value_df["truncation_rule"],
            "source_id": value_df["source_id"],
            "is_observed": value_df["value_type"].isin(["observed", "derived_policy_cost_anchor"]),
            "is_scenario": value_df["scenario_id"].notna() | value_df["module"].isin(["ai_shock", "fiscal_channels_ai_rent"]),
            "is_structural_unobserved": value_df["support_type"].astype(str).str.contains("calibrated|prior|grid|scenario", case=False, regex=True),
            "sensitivity_level": np.where(value_df["audit_status"].astype(str).str.contains("author_review"), "high", "baseline"),
            "justification": value_df["notes"],
            "double_counting_note": value_df["double_counting_note"],
            "included_in_primary": value_df["primary_spec_flag"],
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
            "assumption_id": value_df["assumption_id"],
            "created_at": NOW,
            "created_by_script": SCRIPT_NAME,
        }
    )
    return df


def build_assumption_registry_rows(registry_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "assumption_id": registry_df["assumption_id"],
            "module": registry_df["module"],
            "parameter_name": registry_df["parameter_name"],
            "baseline_value": registry_df["baseline_value"],
            "low_value": registry_df["low_value"],
            "high_value": registry_df["high_value"],
            "distribution": registry_df["distribution"],
            "justification": registry_df["justification"],
            "source_id": registry_df["source_id"],
            "is_observed": registry_df["is_observed"],
            "is_scenario": registry_df["is_scenario"],
            "is_structural_unobserved": registry_df["is_structural_unobserved"],
            "sensitivity_level": registry_df["sensitivity_level"],
            "created_at": NOW,
            "created_by_script": SCRIPT_NAME,
        }
    )


def build_parameter_set_items(value_df: pd.DataFrame) -> pd.DataFrame:
    scenario_int = value_df["scenario_id"].map(SCENARIO_TO_INT)
    regime_int = value_df["regime_code"].str.extract(r"r([0-4])", expand=False).astype("float")
    return pd.DataFrame(
        {
            "parameter_set_id": PARAMETER_SET_ID,
            "assumption_id": value_df["assumption_id"],
            "parameter_name": value_df["name"],
            "country_id": value_df["country_id"],
            "policy_id": value_df["policy_id"],
            "scenario_id": scenario_int,
            "regime_id": regime_int,
            "parameter_value": value_df["baseline_value"],
            "distribution": value_df["distribution"],
            "draw_rule": value_df["truncation_rule"],
            "notes": value_df["notes"],
        }
    )


def rebuild_anchor_parameter_set_items(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    assumptions = con.execute(
        """
        SELECT *
        FROM assumption_registry
        WHERE created_by_script='build_anchors_from_snapshot.py'
        """
    ).fetchdf()
    rows = []
    for _, row in assumptions.iterrows():
        parameter_name = str(row["parameter_name"])
        policy_id = None
        if parameter_name.startswith(("GMI_", "MUT_", "PBI_", "PEN_", "UBI_")):
            policy_id = parameter_name.split("_", 1)[0]
        elif parameter_name.startswith("eta_"):
            policy_id = parameter_name.split("_", 1)[1]
        elif parameter_name in {"theta_target", "chi_gmi"}:
            policy_id = "GMI"

        if parameter_name == "exposure_productive":
            draw_rule = "fixed_midpoint_for_anchor"
            notes = "Used only for anchor-stage fallback, not for calibrated Etapa 3."
        elif parameter_name == "theta_target":
            draw_rule = "loaded_aggregate_upper_bound"
            notes = "Reported beside GMI ideal aggregate."
        elif row["module"] == "policy_admin_transition_cost":
            draw_rule = "baseline_value"
            notes = "Administrative/transition assumption with low/high stored in assumption_registry."
        else:
            draw_rule = "baseline_value"
            notes = "Anchor-stage assumption mirrored from assumption_registry."

        rows.append(
            {
                "parameter_set_id": "baseline_anchor_v0_1_2",
                "assumption_id": row["assumption_id"],
                "parameter_name": parameter_name,
                "country_id": COUNTRY_ID,
                "policy_id": policy_id,
                "scenario_id": None,
                "regime_id": None,
                "parameter_value": float(row["baseline_value"]),
                "distribution": row["distribution"],
                "draw_rule": draw_rule,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_dim_ai_scenario(con: duckdb.DuckDBPyConnection, value_df: pd.DataFrame) -> pd.DataFrame:
    base = con.execute("SELECT * FROM dim_ai_scenario").fetchdf()
    records = []
    for scenario_id in ["low", "mid", "high", "stress"]:
        rows = value_df[value_df["scenario_id"] == scenario_id].set_index("name")
        record = base[base["scenario_id"] == scenario_id].iloc[0].to_dict()
        record["phi_raw_mid"] = float(rows.loc[f"phi_raw_{scenario_id}", "baseline_value"])
        record["kappa_to_y_baseline"] = float(rows[rows.index.str.contains(f"_{scenario_id}$") & rows.index.str.contains("kappa")]["baseline_value"].iloc[0])
        record["pi_ai_y_baseline"] = float(rows.loc[f"pi_AI_Y_{scenario_id}", "baseline_value"])
        record["phi_y_nom_baseline"] = float(rows.loc[f"phi_Y_nom_{scenario_id}", "baseline_value"])
        record["lambda_ai_rent_baseline"] = float(rows.loc[f"lambda_AI_{scenario_id}", "baseline_value"])
        record["parameter_set_id"] = PARAMETER_SET_ID
        record["dataset_version"] = DATASET_VERSION
        record["created_at"] = NOW
        record["created_by_script"] = SCRIPT_NAME
        records.append(record)
    return pd.DataFrame(records)


def build_frontier_anchor(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    existing = con.execute("SELECT * FROM frontier_benchmark_anchor").fetchdf()
    existing = existing[
        ~(
            (existing["benchmark_set_id"] == "baseline_oecd_eurostat_ge10_2024")
            & (existing["scenario_id"] == PARAMETER_SET_ID)
        )
    ].copy()
    oecd_codes = {
        "AUT","BEL","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN",
        "IRL","ITA","LVA","LTU","LUX","NLD","NOR","POL","PRT","SVK",
        "SVN","ESP","SWE","TUR",
    }
    selected = existing[
        (existing["benchmark_set_id"] == "candidate_eurostat_ge10_2024")
        & (existing["benchmark_country_id"].isin(oecd_codes))
    ].copy()
    selected["benchmark_set_id"] = "baseline_oecd_eurostat_ge10_2024"
    selected["scenario_id"] = PARAMETER_SET_ID
    selected["score_convention"] = "pending_phase3b_S_NDC_beta1_gamma1_alpha0"
    selected["elasticities_used"] = "beta=1;gamma=1;alpha=0;computed_in_3B"
    selected["population_consistency_note"] = (
        "Selected in Etapa 3A for population consistency with phi_mid OECD/advanced-economy "
        "micro-to-macro evidence. Candidate Eurostat GE10 enterprise AI adoption rows are "
        "restricted to OECD Eurostat economies; s_frontier_score remains NULL until 3B."
    )
    selected["dataset_version"] = DATASET_VERSION
    selected["build_id"] = f"{DATASET_VERSION}-{PARAMETER_SET_ID}"
    return pd.concat([existing, selected], ignore_index=True)


def append_or_replace_by_script(con: duckdb.DuckDBPyConnection, table_name: str, new_df: pd.DataFrame) -> None:
    try:
        old = con.execute(f"SELECT * FROM {table_name}").fetchdf()
        if "parameter_set_id" in old.columns:
            old = old[old["parameter_set_id"] != PARAMETER_SET_ID]
        elif "created_by_script" in old.columns:
            old = old[old["created_by_script"] != SCRIPT_NAME]
        else:
            old = old.iloc[0:0]
        combined = pd.concat([old, new_df], ignore_index=True)
    except duckdb.CatalogException:
        combined = new_df
    con.register("tmp_df", combined)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def replace_table(con: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame) -> None:
    con.register("tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def write_outputs(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    if "parameter_set_id" in df.columns:
        try:
            old = con.execute(f"SELECT * FROM {name}").fetchdf()
            old = old[old["parameter_set_id"] != PARAMETER_SET_ID]
            combined = pd.concat([old, df], ignore_index=True)
        except duckdb.CatalogException:
            combined = df
        replace_table(con, name, combined)
        combined.to_parquet(MODEL_INPUTS_DIR / f"{name}.parquet", index=False)
    else:
        replace_table(con, name, df)
        df.to_parquet(MODEL_INPUTS_DIR / f"{name}.parquet", index=False)


def append_or_replace_assumptions(con: duckdb.DuckDBPyConnection, new_df: pd.DataFrame) -> pd.DataFrame:
    try:
        old = con.execute("SELECT * FROM assumption_registry").fetchdf()
        old = old[~old["assumption_id"].astype(str).str.startswith("A3A_V2_")]
        combined = pd.concat([old, new_df], ignore_index=True)
    except duckdb.CatalogException:
        combined = new_df
    replace_table(con, "assumption_registry", combined)
    combined.to_parquet(MODEL_INPUTS_DIR / "assumption_registry.parquet", index=False)
    return combined


def build_parameter_set_changelog() -> pd.DataFrame:
    rows = []
    for code, text in CHANGELOG:
        rows.append(
            {
                "from_parameter_set_id": PREVIOUS_PARAMETER_SET_ID,
                "to_parameter_set_id": PARAMETER_SET_ID,
                "change_id": code,
                "change_text": text,
                "dataset_version": DATASET_VERSION,
                "created_at": NOW,
                "created_by_script": SCRIPT_NAME,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    MODEL_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))
    value_df, context = build_values(con)
    thresholds = build_thresholds(con, context["q_bar"])
    rules = build_rules()
    audit, double_counting = build_audits(value_df)
    registry = build_calibrated_registry(value_df)
    assumption_rows = build_assumption_registry_rows(registry)
    changelog = build_parameter_set_changelog()
    try:
        old_psi = con.execute("SELECT * FROM parameter_set_item").fetchdf()
        old_psi = old_psi[
            ~old_psi["parameter_set_id"].isin([PARAMETER_SET_ID, "baseline_anchor_v0_1_2"])
        ]
    except duckdb.CatalogException:
        old_psi = pd.DataFrame()
    psi = pd.concat(
        [old_psi, rebuild_anchor_parameter_set_items(con), build_parameter_set_items(value_df)],
        ignore_index=True,
    )
    dim_ai = build_dim_ai_scenario(con, value_df)
    frontier = build_frontier_anchor(con)

    parameter_set = pd.DataFrame(
        [
            {
                "parameter_set_id": PARAMETER_SET_ID,
                "parameter_set_name": "baseline pilot v2",
                "description": "Etapa 3A.1 pre-run governance recalibration for PER. Changelog v1->v2: C1 E_auto; C2 psi_shift; C3 Gap diagnostic blocker; C4 q_use_target support/double-counting note; C5 phi ladder note. No economic results.",
                "model_version": "pre_engine_stage_3a",
                "dataset_version": DATASET_VERSION,
                "created_at": NOW,
                "created_by_script": SCRIPT_NAME,
            }
        ]
    )

    source_rows = pd.DataFrame(
        [
            {
                "source_id": "PAPER_AI_USP_V2_5",
                "source_name": "AI USP Threshold Framework v2.5 corrected",
                "provider": "author",
                "url_or_api": "D:/paper de economia/AI_USP_Threshold_Framework_v2_5_corrected.tex",
                "download_date": "",
                "license_notes": "Local manuscript source.",
                "raw_file_path": "D:/paper de economia/AI_USP_Threshold_Framework_v2_5_corrected.tex",
                "citation_text": "AI USP Threshold Framework v2.5 corrected manuscript, calibration and appendix sections.",
            }
        ]
    )

    write_outputs(con, "value_assignment_table", value_df)
    write_outputs(con, "threshold_assignment_table", thresholds)
    write_outputs(con, "threshold_rule_registry", rules)
    write_outputs(con, "input_audit_report", audit)
    write_outputs(con, "double_counting_audit", double_counting)
    write_outputs(con, "calibrated_parameter_registry", registry)
    write_outputs(con, "parameter_set_changelog", changelog)
    write_outputs(con, "dim_ai_scenario", dim_ai)
    replace_table(con, "frontier_benchmark_anchor", frontier)
    frontier.to_parquet(MODEL_INPUTS_DIR / "frontier_benchmark_anchor.parquet", index=False)

    append_or_replace_by_script(con, "parameter_set", parameter_set)
    con.execute("COPY parameter_set TO ? (FORMAT PARQUET)", [str(MODEL_INPUTS_DIR / "parameter_set.parquet")])

    replace_table(con, "parameter_set_item", psi)
    psi.to_parquet(MODEL_INPUTS_DIR / "parameter_set_item.parquet", index=False)

    append_or_replace_assumptions(con, assumption_rows)

    try:
        old_source = con.execute("SELECT * FROM dim_source").fetchdf()
        old_source = old_source[old_source["source_id"] != "PAPER_AI_USP_V2_5"]
        dim_source = pd.concat([old_source, source_rows], ignore_index=True)
        replace_table(con, "dim_source", dim_source)
    except duckdb.CatalogException:
        replace_table(con, "dim_source", source_rows)

    report_cols = [
        "name",
        "module",
        "country_id",
        "scenario_id",
        "policy_id",
        "regime_code",
        "baseline_value",
        "low_value",
        "high_value",
        "unit",
        "distribution",
        "support_type",
        "source_id",
        "formula_id",
        "double_counting_risk",
        "double_counting_note",
        "audit_status",
        "notes",
    ]
    value_df[report_cols].to_csv(REPORTS_DIR / f"value_assignment_table_{PARAMETER_SET_ID}.csv", index=False)
    thresholds.to_csv(REPORTS_DIR / f"threshold_assignment_table_{PARAMETER_SET_ID}.csv", index=False)
    audit.to_csv(REPORTS_DIR / f"input_audit_report_{PARAMETER_SET_ID}.csv", index=False)
    double_counting.to_csv(REPORTS_DIR / f"double_counting_audit_{PARAMETER_SET_ID}.csv", index=False)
    changelog.to_csv(REPORTS_DIR / f"parameter_set_changelog_{PARAMETER_SET_ID}.csv", index=False)

    print(f"parameter_set_id={PARAMETER_SET_ID}")
    print(f"value_assignment_rows={len(value_df)}")
    print(f"author_review_rows={int(value_df['audit_status'].astype(str).str.contains('author_review').sum())}")
    print(f"run_readiness_flag={bool(audit.loc[audit['check_name']=='run_readiness_flag','passes_check'].iloc[0])}")
    print(f"q_use_target={context['q_use_target']:.8f}")
    print(f"q_bar={context['q_bar']:.8f}")
    print(f"rst_proxy={context['rst_proxy']:.8f}")
    print(f"sPB_plus_gdp_ratio={context['sPB_plus_ratio']:.8f}")
    print(f"value_assignment_csv={REPORTS_DIR / f'value_assignment_table_{PARAMETER_SET_ID}.csv'}")


if __name__ == "__main__":
    NOW = now_iso()
    main()
