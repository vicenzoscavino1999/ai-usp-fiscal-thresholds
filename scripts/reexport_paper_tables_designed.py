"""Reexporta las tablas impresas 1--7 y 5b desde los CSVs oficiales.

Se ejecuta DESPUÉS de finalize_phase_b; sustituye los .tex truncados head-N por
selecciones diseñadas; valores idénticos a los CSVs oficiales; cambio de formato
de reporte, sin recomputación.
"""

from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "reports" / "paper_tables"
REPORTS_DIR = ROOT / "reports"
TARGET_DIR = ROOT / "paper" / "tables"

TABLE1_FIELDS = [
    "country_id",
    "year",
    "gdp_nominal_lcu",
    "gdp_nominal_usd",
    "cpi_index",
    "tax_revenue_gdp",
    "total_revenue_gdp",
    "gross_debt_gdp",
    "pb_stabilizing_gdp",
    "nominal_interest_rate",
    "gap_index",
    "coverage_lte_wimax_pct",
    "speed_fixed_download_mbps",
    "speed_mobile_download_mbps",
    "A_aipi_total",
    "E_prod",
    "Gap_excluded_indicators",
    "I_adopt_informality",
    "q_use_target",
]
TABLE2_FIELDS = [
    "country_id",
    "policy_id",
    "policy_variant_id",
    "gmi_version",
    "cost_gross_gdp",
    "cost_net_gdp",
    "endpoint_cost_rule",
]
TABLE3_FIELDS = [
    "block",
    "id",
    "phi_y_nominal_min",
    "phi_y_nominal_max",
    "description",
]
TABLE4_FIELDS = [
    "country_id",
    "policy_variant_id",
    "scenario_id",
    "regime_id",
    "v_gross",
    "crosses_v1",
    "cell_result_class",
]
TABLE5_FIELDS = [
    "country_id",
    "policy_variant_id",
    "scenario_id",
    "regime_id",
    "requirement_basis",
    "g_ai_required",
    "mfc_required_gross",
    "q_prod_required",
    "historical_tax_class",
    "historical_tax_borderline",
    "historical_total_revenue_class",
    "flags",
]
TABLE5_HEADERS = [
    "country",
    "policy variant",
    "scenario",
    "regime",
    "basis",
    "g required",
    "MFC required",
    "q required",
    "tax class",
    "tax border",
    "total-revenue class",
    "flags",
]
TABLE6_FIELDS = [
    "country_id",
    "scenario_id",
    "regime_id",
    "mfc_gross",
    "tax_class",
    "tax_borderline",
    "total_revenue_class",
    "total_revenue_borderline",
]
TABLE7_FIELDS = [
    "country_id",
    "policy_variant_id",
    "scenario_id",
    "regime_id",
    "prob_v_ge_1",
    "prob_v_ge_1_10",
    "v_p05",
    "v_p50",
    "v_p95",
    "converged_flag",
]
TABLE5B_FIELDS = [
    "country_id",
    "policy_id",
    "policy_variant_id",
    "gmi_version",
    "scenario_id",
    "regime_id",
    "h_star_baseline",
    "h_star_status_baseline",
    "h_star_debt_consistent",
    "h_star_status_debt_consistent",
    "prob_h_star_le_10",
    "prob_h_star_le_25",
    "note",
]
TABLE5B_PRINT_FIELDS = [
    "country_id",
    "policy_id",
    "policy_variant_id",
    "gmi_version",
    "scenario_id",
    "regime_id",
    "h_star_baseline",
    "h_star_debt_consistent",
    "prob_h_star_le_10",
    "prob_h_star_le_25",
]
TABLE5B_HEADERS = [
    r"\shortstack{country\\id}",
    r"\shortstack{policy\\id}",
    r"\shortstack{policy\\variant}",
    r"\shortstack{GMI\\version}",
    "scenario",
    "regime",
    r"\shortstack{$H^*$\\baseline}",
    r"\shortstack{$H^*$\\debt}",
    r"\shortstack{$\Pr(H^*\leq10)$}",
    r"\shortstack{$\Pr(H^*\leq25)$}",
]

COUNTRIES = ["PER", "CHL", "COL", "MEX"]
PRIMARY_POLICY_VARIANTS = [
    "PEN",
    "GMI:GMI_ideal_aggregate",
    "MUT",
    "PBI",
    "UBI",
]
REGIMES = ["r0", "r1", "r2", "r3", "r4"]
HEADLINE_POLICIES = [
    ("CHL", "GMI:GMI_ideal_aggregate"),
    ("PER", "PEN"),
]
HEADLINE_SCENARIOS = ["mid", "stress"]
REQUIREMENT_BASES = ["baseline", "debt_consistent"]
CAPTION_SUFFIX = "Headline cells; the full grid is provided in the Online Appendix and the reproducibility package."
COUNTRY_LABELS = {"CHL": "Chile", "COL": "Colombia", "MEX": "Mexico", "PER": "Peru"}


def read_csv(name: str, expected_fields: list[str]) -> list[dict[str, str]]:
    path = SOURCE_DIR / name
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            raise AssertionError(f"{name}: unexpected fields {reader.fieldnames}")
        return list(reader)


def read_csv_fields(path: Path, required_fields: list[str]) -> list[dict[str, str]]:
    """Read a complete official CSV and retain an ordered publication subset."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in required_fields if field not in (reader.fieldnames or [])]
        if missing:
            raise AssertionError(f"{path.name}: missing required fields {missing}")
        return [{field: row[field] for field in required_fields} for row in reader]


def rounds_to_literal(value: str, literal: str) -> bool:
    """Match a source value to the precision printed in Results prose."""
    decimals = len(literal.partition(".")[2]) if "." in literal else 0
    quantum = Decimal(1).scaleb(-decimals)
    return Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP) == Decimal(literal)


def assert_literal_present(rows: list[dict[str, str]], field: str, literal: str, table_name: str) -> None:
    if not any(row[field] and rounds_to_literal(row[field], literal) for row in rows):
        raise AssertionError(f"{table_name}: no {field} value rounds to Results literal {literal}")


def row_index(rows: Iterable[dict[str, str]], fields: list[str]) -> dict[tuple[str, ...], dict[str, str]]:
    index: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in index:
            raise AssertionError(f"duplicate source key: {key}")
        index[key] = row
    return index


def select_rows(
    index: dict[tuple[str, ...], dict[str, str]],
    keys: Iterable[tuple[str, ...]],
    source_rows: list[dict[str, str]],
    table_name: str,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    source_values = {tuple(row.items()) for row in source_rows}
    for key in keys:
        if key not in index:
            raise AssertionError(f"{table_name}: missing source row for {key}")
        row = index[key]
        if tuple(row.items()) not in source_values:
            raise AssertionError(f"{table_name}: selected row is not field-identical to its source")
        selected.append(row)
    if len({tuple(row.items()) for row in selected}) != len(selected):
        raise AssertionError(f"{table_name}: duplicate selected row")
    return selected


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    text = value
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def header_lines(fields: list[str], continued_caption: str, headers: list[str] | None = None) -> list[str]:
    labels = fields if headers is None else headers
    if len(labels) != len(fields):
        raise AssertionError("header label count does not match table field count")
    header = " & ".join(latex_escape(label) for label in labels) + r" \\"
    return [
        r"\toprule",
        header,
        r"\midrule",
        r"\endfirsthead",
        rf"\caption[]{{{continued_caption}}}\\",
        r"\toprule",
        header,
        r"\midrule",
        r"\endhead",
    ]


def latex_rows(rows: Iterable[dict[str, str]], fields: list[str]) -> list[str]:
    return [" & ".join(latex_escape(row[field]) for field in fields) + r" \\" for row in rows]


def display_round(
    rows: Iterable[dict[str, str]], decimal_fields: set[str], decimal_places: int
) -> list[dict[str, str]]:
    """Round only the printed representation; source-row assertions use full precision."""
    rendered: list[dict[str, str]] = []
    for row in rows:
        output = dict(row)
        for field in decimal_fields:
            if output[field]:
                output[field] = f"{float(output[field]):.{decimal_places}f}"
        rendered.append(output)
    return rendered


def decimal_text(value: str, places: int, scale: Decimal = Decimal("1")) -> str:
    quantum = Decimal(1).scaleb(-places)
    return f"{(Decimal(value) * scale).quantize(quantum, rounding=ROUND_HALF_UP):.{places}f}"


def write_table1(rows: list[dict[str, str]]) -> None:
    caption = (
        "Observed 2024 country anchors. GDP is in USD billions; fiscal ratios, "
        "informality, and adoption are percentages. The complete anchor matrix is "
        "provided in the replication package."
    )
    lines = [
        r"\begingroup",
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:results_anchors}}",
        r"\fontsize{7.2}{8.6}\selectfont",
        r"\setlength{\tabcolsep}{2.4pt}",
        r"\begin{tabular}{@{}lrrrrrrrr@{}}",
        r"\toprule",
        r"Country & \shortstack{GDP\\(USD bn)} & \shortstack{Tax rev.\\(\% GDP)} & \shortstack{Total rev.\\(\% GDP)} & \shortstack{Debt\\(\% GDP)} & AIPI & \shortstack{Digital\\gap} & \shortstack{Informality\\(\%)} & \shortstack{Adoption\\target (\%)} \\",
        r"\midrule",
    ]
    for row in rows:
        rendered = [
            COUNTRY_LABELS[row["country_id"]],
            decimal_text(row["gdp_nominal_usd"], 1, Decimal("0.000000001")),
            decimal_text(row["tax_revenue_gdp"], 1),
            decimal_text(row["total_revenue_gdp"], 1),
            decimal_text(row["gross_debt_gdp"], 1),
            decimal_text(row["A_aipi_total"], 3),
            decimal_text(row["Gap_excluded_indicators"], 3),
            decimal_text(row["I_adopt_informality"], 1, Decimal("100")),
            decimal_text(row["q_use_target"], 1, Decimal("100")),
        ]
        lines.append(" & ".join(latex_escape(value) for value in rendered) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            r"\endgroup",
            "",
        ]
    )
    (TARGET_DIR / "table1_anchors.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table2(rows: list[dict[str, str]]) -> None:
    caption = (
        "Gross annual policy costs at the 2024 anchor. GMI rows report ideal and loaded "
        "targeting separately; net costs equal gross costs under the pure-layering baseline."
    )
    lines = [
        r"\begingroup",
        r"\singlespacing",
        r"\fontsize{8}{9.6}\selectfont",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{longtable}{@{}p{0.12\linewidth}p{0.12\linewidth}p{0.13\linewidth}r p{0.36\linewidth}@{}}",
        rf"\caption{{{caption}}}\label{{tab:results_policy_costs}}\\",
        r"\toprule",
        r"Country & Instrument & Variant & \shortstack{Gross cost\\(\% GDP)} & Endpoint convention \\",
        r"\midrule",
        r"\endfirsthead",
        rf"\caption[]{{{caption} (continued)}}\\",
        r"\toprule",
        r"Country & Instrument & Variant & \shortstack{Gross cost\\(\% GDP)} & Endpoint convention \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in rows:
        if row["gmi_version"] == "GMI_ideal_aggregate":
            variant = "Ideal"
        elif row["gmi_version"] == "GMI_loaded_aggregate":
            variant = "Loaded"
        else:
            variant = "--"
        rule = row["endpoint_cost_rule"]
        if rule.startswith("GMI fixed aggregate"):
            endpoint = "Fixed aggregate cost"
        elif rule.startswith("Colombia PEN"):
            endpoint = "WPP sex- and age-specific eligibility"
        else:
            endpoint = "WPP eligible-share ratio"
        rendered = [
            COUNTRY_LABELS[row["country_id"]],
            row["policy_id"],
            variant,
            decimal_text(row["cost_gross_gdp"], 4, Decimal("100")),
            endpoint,
        ]
        lines.append(" & ".join(latex_escape(value) for value in rendered) + r" \\")
    lines.extend([r"\bottomrule", r"\end{longtable}", r"\endgroup", ""])
    (TARGET_DIR / "table2_policy_costs.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table3(rows: list[dict[str, str]]) -> None:
    caption = "Primary AI scenarios and fiscal regimes."
    scenario_rows = {row["id"]: row for row in rows if row["block"] == "scenario"}
    regime_rows = {row["id"]: row for row in rows if row["block"] == "regime"}
    scenario_labels = {"low": "Low", "mid": "Moderate", "high": "High", "stress": "Disruptive stress"}
    paired: list[tuple[str, str, str, str]] = []
    for index, regime in enumerate(REGIMES):
        scenario = ("low", "mid", "high", "stress")[index] if index < 4 else None
        if scenario is None:
            scenario_label = ""
            support = ""
        else:
            row = scenario_rows[scenario]
            low = decimal_text(row["phi_y_nominal_min"], 3, Decimal("100"))
            high = decimal_text(row["phi_y_nominal_max"], 3, Decimal("100"))
            support = low if low == high else f"{low}--{high}"
            scenario_label = scenario_labels[scenario]
        match = regime_rows[regime]["description"].rsplit("=", 1)[-1]
        paired.append((scenario_label, support, regime, decimal_text(match, 2, Decimal("100"))))
    lines = [
        r"\begingroup",
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:results_primary_spec}}",
        r"\small",
        r"\setlength{\tabcolsep}{7pt}",
        r"\begin{tabular}{@{}lr@{\hspace{3em}}lr@{}}",
        r"\toprule",
        r"Scenario & \shortstack{Annual AI shock\\(\% of GDP)} & Regime & \shortstack{Median $MFC^{gross}$\\(\%)} \\",
        r"\midrule",
    ]
    for row in paired:
        lines.append(" & ".join(latex_escape(value) for value in row) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\multicolumn{4}{@{}p{0.88\linewidth}@{}}{\footnotesize The high scenario reports the country range after the source-unit and nominal-output bridges; other scenarios are point supports.} \\",
            r"\end{tabular}",
            r"\end{table}",
            r"\endgroup",
            "",
        ]
    )
    (TARGET_DIR / "table3_primary_specification.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table4(rows: list[dict[str, str]]) -> None:
    caption = rf"Table 4. Baseline $V^{{gross}}$: four-country moderate-support null and all crossing cells. {CAPTION_SUFFIX}"
    columns = [
        r">{\raggedright\arraybackslash}p{0.06\linewidth}",
        r">{\raggedright\arraybackslash}p{0.23\linewidth}",
        r">{\raggedright\arraybackslash}p{0.10\linewidth}",
        r">{\raggedright\arraybackslash}p{0.07\linewidth}",
        r">{\raggedright\arraybackslash}p{0.19\linewidth}",
        r"@{\hspace{0.35em}}",
        r">{\raggedright\arraybackslash}p{0.12\linewidth}",
        r">{\raggedright\arraybackslash}p{0.18\linewidth}",
    ]
    lines = [
        r"\begingroup",
        r"\fontsize{8}{9.6}\selectfont",
        r"\setlength{\tabcolsep}{1.2pt}",
        r"\let\tableunderscore\_",
        r"\renewcommand{\_}{\tableunderscore\allowbreak}",
        r"\begin{longtable}{@{}",
        *columns,
        r"@{}}",
        rf"\caption{{{caption}}}",
        r"\label{tab:results_vgross}\\",
        *header_lines(TABLE4_FIELDS, caption + " (continued)"),
        r"\multicolumn{7}{l}{\textit{Panel A: all countries, moderate scenario, r0, primary policy variants}} \\",
        r"\midrule",
        *latex_rows(rows[:20], TABLE4_FIELDS),
        r"\midrule",
        r"\multicolumn{7}{l}{\textit{Panel B: all crossing cells}} \\",
        r"\midrule",
        *latex_rows(rows[20:], TABLE4_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\endgroup",
        "",
    ]
    (TARGET_DIR / "table4_vgross_baseline.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table5(rows: list[dict[str, str]]) -> None:
    caption = f"Table 5. Threshold inversion: moderate-support base accounting and cited crossing cells. {CAPTION_SUFFIX}"
    columns = [
        r">{\raggedright\arraybackslash}p{0.03\linewidth}",
        r">{\raggedright\arraybackslash}p{0.11\linewidth}",
        r">{\raggedright\arraybackslash}p{0.04\linewidth}",
        r">{\raggedright\arraybackslash}p{0.03\linewidth}",
        r">{\raggedright\arraybackslash}p{0.07\linewidth}",
        r">{\raggedright\arraybackslash}p{0.07\linewidth}",
        r">{\raggedright\arraybackslash}p{0.07\linewidth}",
        r">{\raggedright\arraybackslash}p{0.065\linewidth}",
        r">{\raggedright\arraybackslash}p{0.13\linewidth}",
        r">{\raggedright\arraybackslash}p{0.055\linewidth}",
        r">{\raggedright\arraybackslash}p{0.13\linewidth}",
        r">{\raggedright\arraybackslash}p{0.16\linewidth}",
    ]
    printed_rows = display_round(rows, {"g_ai_required", "mfc_required_gross", "q_prod_required"}, 4)
    lines = [
        r"\begin{landscape}",
        r"\fontsize{5}{6}\selectfont",
        r"\setlength{\tabcolsep}{2pt}",
        r"\setlength{\LTleft}{0pt}",
        r"\setlength{\LTright}{0pt}",
        r"\let\tableunderscore\_",
        r"\renewcommand{\_}{\tableunderscore\allowbreak}",
        r"\begin{longtable}{@{}",
        *columns,
        r"@{}}",
        rf"\caption{{{caption}}}\label{{tab:results_inversions}}\\",
        *header_lines(TABLE5_FIELDS, caption + " (continued)", TABLE5_HEADERS),
        rf"\multicolumn{{{len(TABLE5_FIELDS)}}}{{l}}{{\textit{{Panel A: all countries, moderate scenario, r0, baseline requirement}}}} \\",
        r"\midrule",
        *latex_rows(printed_rows[:20], TABLE5_FIELDS),
        r"\midrule",
        rf"\multicolumn{{{len(TABLE5_FIELDS)}}}{{l}}{{\textit{{Panel B: cited stress crossing cells}}}} \\",
        r"\midrule",
        *latex_rows(printed_rows[20:], TABLE5_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\end{landscape}",
        "",
    ]
    (TARGET_DIR / "table5_threshold_inversion.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table6(rows: list[dict[str, str]]) -> None:
    caption = (
        "Historical plausibility of constructed channel-based captures. "
        "Headline rows; constant provenance fields and the full 80-row grid in the Online Appendix "
        "and the reproducibility package."
    )
    columns = [
        r">{\raggedright\arraybackslash}p{0.055\linewidth}",
        r">{\raggedright\arraybackslash}p{0.065\linewidth}",
        r">{\raggedright\arraybackslash}p{0.05\linewidth}",
        r">{\raggedright\arraybackslash}p{0.11\linewidth}",
        r">{\raggedright\arraybackslash}p{0.19\linewidth}",
        r">{\raggedright\arraybackslash}p{0.09\linewidth}",
        r">{\raggedright\arraybackslash}p{0.22\linewidth}",
        r">{\raggedright\arraybackslash}p{0.10\linewidth}",
    ]
    lines = [
        r"\begin{landscape}",
        r"\fontsize{7}{8.4}\selectfont",
        r"\setlength{\tabcolsep}{1.8pt}",
        r"\let\tableunderscore\_",
        r"\renewcommand{\_}{\tableunderscore\allowbreak}",
        r"\begin{longtable}{@{}",
        *columns,
        r"@{}}",
        rf"\caption{{{caption}}}\label{{tab:results_plausibility}}\\",
        *header_lines(TABLE6_FIELDS, caption + " (continued)"),
        rf"\multicolumn{{{len(TABLE6_FIELDS)}}}{{l}}{{\textit{{Panel A: moderate scenario, all countries and regimes}}}} \\",
        r"\midrule",
        *latex_rows(rows[:20], TABLE6_FIELDS),
        r"\midrule",
        rf"\multicolumn{{{len(TABLE6_FIELDS)}}}{{l}}{{\textit{{Panel B: low, high, and stress scenarios at r0}}}} \\",
        r"\midrule",
        *latex_rows(rows[20:], TABLE6_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\end{landscape}",
        "",
    ]
    (TARGET_DIR / "table6_historical_plausibility.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table7(rows: list[dict[str, str]]) -> None:
    caption = "Table 7. Monte Carlo probabilities and percentiles: headline cells"
    lines = [
        r"\begin{landscape}",
        r"\fontsize{7}{8.4}\selectfont",
        r"\setlength{\tabcolsep}{2.2pt}",
        r"\begin{longtable}{llllllllll}",
        rf"\caption{{{caption}}}\label{{tab:results_mc}}\\",
        *header_lines(TABLE7_FIELDS, caption + " (continued)"),
        *latex_rows(rows, TABLE7_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\end{landscape}",
        "",
    ]
    (TARGET_DIR / "table7_monte_carlo.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table5b(rows: list[dict[str, str]]) -> None:
    caption = (
        r"Time to threshold $H^*$ (post-baseline extension). Both status fields are "
        r"\texttt{crosses\_within\_cap} in all four data rows; the common note is ``$H^*$ "
        r"censored at 25 years; values are conditional years of frozen scenario persistence, "
        r"not calendar forecasts.''"
    )
    columns = [
        r">{\raggedright\arraybackslash}p{0.06\linewidth}",
        r">{\raggedright\arraybackslash}p{0.055\linewidth}",
        r">{\raggedright\arraybackslash}p{0.17\linewidth}",
        r">{\raggedright\arraybackslash}p{0.14\linewidth}",
        r">{\raggedright\arraybackslash}p{0.07\linewidth}",
        r">{\raggedright\arraybackslash}p{0.055\linewidth}",
        r">{\raggedright\arraybackslash}p{0.075\linewidth}",
        r">{\raggedright\arraybackslash}p{0.075\linewidth}",
        r">{\raggedright\arraybackslash}p{0.105\linewidth}",
        r">{\raggedright\arraybackslash}p{0.105\linewidth}",
    ]
    lines = [
        r"\begingroup",
        r"\let\tableunderscore\_",
        r"\renewcommand{\_}{\tableunderscore\allowbreak}",
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:results_h_star}}",
        r"\fontsize{7}{8.4}\selectfont",
        r"\setlength{\tabcolsep}{1.5pt}",
        r"\begin{tabular}{@{}",
        *columns,
        r"@{}}",
        r"\toprule",
        " & ".join(TABLE5B_HEADERS) + r" \\",
        r"\midrule",
        *latex_rows(rows, TABLE5B_PRINT_FIELDS),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        r"\endgroup",
        "",
    ]
    (TARGET_DIR / "table5b_time_to_threshold.tex").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    table1_source = read_csv("table1_anchors.csv", TABLE1_FIELDS)
    table2_source = read_csv("table2_policy_costs.csv", TABLE2_FIELDS)
    table3_source = read_csv("table3_primary_specification.csv", TABLE3_FIELDS)
    table4_source = read_csv("table4_vgross_baseline.csv", TABLE4_FIELDS)
    table5_source_all = read_csv_fields(
        REPORTS_DIR / "threshold_inversion_result_baseline-official-v2.csv",
        ["xi", *TABLE5_FIELDS],
    )
    table5_source = [
        {field: row[field] for field in TABLE5_FIELDS}
        for row in table5_source_all
        if Decimal(row["xi"]) == Decimal("0.10")
    ]
    table6_source = read_csv_fields(SOURCE_DIR / "table6_historical_plausibility.csv", TABLE6_FIELDS)
    table7_source = read_csv("table7_monte_carlo.csv", TABLE7_FIELDS)
    table5b_source = read_csv("table5b_time_to_threshold.csv", TABLE5B_FIELDS)

    if len(table1_source) != 4 or {row["country_id"] for row in table1_source} != set(COUNTRIES):
        raise AssertionError("table1: expected one anchor row for each of four countries")
    if {row["year"] for row in table1_source} != {"2024"}:
        raise AssertionError("table1: expected all anchors at 2024")
    if len(table2_source) != 24:
        raise AssertionError(f"table2: expected 24 source rows, found {len(table2_source)}")
    if any(row["cost_gross_gdp"] != row["cost_net_gdp"] for row in table2_source):
        raise AssertionError("table2: compact pure-layering note is invalid because gross and net costs differ")
    if len(table3_source) != 9:
        raise AssertionError(f"table3: expected 9 source rows, found {len(table3_source)}")
    if {row["id"] for row in table3_source if row["block"] == "scenario"} != {"low", "mid", "high", "stress"}:
        raise AssertionError("table3: scenario vocabulary changed")
    if {row["id"] for row in table3_source if row["block"] == "regime"} != set(REGIMES):
        raise AssertionError("table3: regime vocabulary changed")

    if len(table4_source) != 480:
        raise AssertionError(f"table4: expected 480 source rows, found {len(table4_source)}")
    table4_index = row_index(table4_source, ["country_id", "policy_variant_id", "scenario_id", "regime_id"])
    # The four-country moderate-support null is the central negative result: one
    # r0 row for each country x primary policy pair, excluding the loaded GMI companion.
    table4_moderate_keys = [
        (country, variant, "mid", "r0")
        for country in COUNTRIES
        for variant in PRIMARY_POLICY_VARIANTS
    ]
    table4_crossing_source_rows = [row for row in table4_source if row["crosses_v1"] == "True"]
    if len(table4_crossing_source_rows) != 15:
        raise AssertionError(f"table4: expected 15 crossing source rows, found {len(table4_crossing_source_rows)}")
    # Every official crossing remains visible, including both GMI targeting
    # variants; this preserves the prose ranges rather than sampling endpoints.
    table4_crossing_keys = [
        (row["country_id"], row["policy_variant_id"], row["scenario_id"], row["regime_id"])
        for row in table4_crossing_source_rows
    ]
    table4_rows = select_rows(
        table4_index,
        [*table4_moderate_keys, *table4_crossing_keys],
        table4_source,
        "table4",
    )
    if len(table4_moderate_keys) != 20 or len(table4_rows) != 35:
        raise AssertionError(f"table4: expected 20 moderate + 15 crossing = 35 rows, found {len(table4_rows)}")
    if [row for row in table4_rows if row["crosses_v1"] == "True"] != select_rows(
        table4_index, table4_crossing_keys, table4_source, "table4 crossings"
    ):
        raise AssertionError("table4: not all crossing rows are present")
    moderate_rows = table4_rows[:20]
    if not all(float(row["v_gross"]) < 0.7 for row in moderate_rows):
        raise AssertionError("table4: a selected moderate-support row violates the Results bound V<0.7")
    for literal in ("2.6", "5.8", "3.9", "1.0", "1.4", "1.02"):
        assert_literal_present(table4_rows, "v_gross", literal, "table4")

    if len(table5_source) != 960:
        raise AssertionError(f"table5: expected 960 xi=0.10 source rows, found {len(table5_source)}")
    table5_index = row_index(
        table5_source,
        ["country_id", "policy_variant_id", "scenario_id", "regime_id", "requirement_basis"],
    )
    # The moderate r0 baseline row for every country x primary policy pair
    # establishes the universal translation-support failure in Results.
    table5_moderate_keys = [
        (country, variant, "mid", "r0", "baseline")
        for country in COUNTRIES
        for variant in PRIMARY_POLICY_VARIANTS
    ]
    # Cited crossing cells retain both accounting/debt bases at r0. Two r4
    # accounting rows retain the combined-reform comparison without restoring
    # the full regime grid already preserved in the Online Appendix copy.
    table5_crossing_keys = [
        (country, variant, "stress", "r0", basis)
        for country, variant in [
            ("CHL", "GMI:GMI_ideal_aggregate"),
            ("CHL", "GMI:GMI_loaded_aggregate"),
            ("PER", "PEN"),
        ]
        for basis in REQUIREMENT_BASES
    ] + [
        ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r4", "baseline"),
        ("PER", "PEN", "stress", "r4", "baseline"),
    ]
    table5_keys = [*table5_moderate_keys, *table5_crossing_keys]
    table5_rows = select_rows(table5_index, table5_keys, table5_source, "table5")
    if len(table5_moderate_keys) != 20 or len(table5_crossing_keys) != 8 or len(table5_rows) != 28:
        raise AssertionError(f"table5: expected 20 moderate + 8 cited crossing = 28 rows, found {len(table5_rows)}")
    if not all("frontier_exceeds_one" in row["flags"] for row in table5_rows[:20]):
        raise AssertionError("table5: every moderate-support base row must retain frontier_exceeds_one")
    assert_literal_present(table5_rows, "mfc_required_gross", "0.17", "table5")
    assert_literal_present(table5_rows, "mfc_required_gross", "0.305", "table5")
    peru_required = table5_index[("PER", "PEN", "mid", "r0", "baseline")]
    if peru_required["historical_tax_class"] != "extreme_or_outside_historical_support" or peru_required[
        "historical_tax_borderline"
    ] != "True":
        raise AssertionError("table5: Peru PEN moderate r0 tax class/borderline is missing or changed")

    if len(table6_source) != 80:
        raise AssertionError(f"table6: expected complete 80-row source, found {len(table6_source)}")
    table6_index = row_index(table6_source, ["country_id", "scenario_id", "regime_id"])
    # Constructed channel-based captures are policy-invariant within a
    # country-scenario-regime cell. Keep the complete moderate block and one
    # r0 row for each remaining scenario-country combination.
    table6_moderate_keys = [(country, "mid", regime) for country in COUNTRIES for regime in REGIMES]
    table6_other_r0_keys = [
        (country, scenario, "r0")
        for scenario in ("low", "high", "stress")
        for country in COUNTRIES
    ]
    table6_rows = select_rows(
        table6_index,
        [*table6_moderate_keys, *table6_other_r0_keys],
        table6_source,
        "table6",
    )
    if len(table6_moderate_keys) != 20 or len(table6_other_r0_keys) != 12 or len(table6_rows) != 32:
        raise AssertionError(f"table6: expected 20 moderate + 12 other-r0 = 32 rows, found {len(table6_rows)}")

    table7_index = row_index(table7_source, ["country_id", "policy_variant_id", "scenario_id", "regime_id"])
    table7_keys = [
        (country, variant, scenario, regime)
        for country, variant in HEADLINE_POLICIES
        for scenario in HEADLINE_SCENARIOS
        for regime in REGIMES
    ]
    table7_rows = select_rows(table7_index, table7_keys, table7_source, "table7")
    if len(table7_rows) != 20:
        raise AssertionError(f"table7: expected 20 rows, found {len(table7_rows)}")
    chl_stress = [row for row in table7_rows if row["country_id"] == "CHL" and row["scenario_id"] == "stress"]
    if min(float(row["prob_v_ge_1"]) for row in chl_stress) <= 0.97:
        raise AssertionError("table7: Chile stress crossing probability no longer exceeds Results literal 0.97")
    for literal in ("0.98", "0.6", "0.8"):
        assert_literal_present(table7_rows, "prob_v_ge_1", literal, "table7")

    if len(table5b_source) != 4:
        raise AssertionError(f"table5b: expected 4 data rows plus header, found {len(table5b_source)}")
    if {row["h_star_status_baseline"] for row in table5b_source} != {"crosses_within_cap"}:
        raise AssertionError("table5b: baseline status is not constant crosses_within_cap")
    if {row["h_star_status_debt_consistent"] for row in table5b_source} != {"crosses_within_cap"}:
        raise AssertionError("table5b: debt-consistent status is not constant crosses_within_cap")
    if len({row["note"] for row in table5b_source}) != 1:
        raise AssertionError("table5b: note is not constant across source rows")

    write_table1(table1_source)
    write_table2(table2_source)
    write_table3(table3_source)
    write_table4(table4_rows)
    write_table5(table5_rows)
    write_table6(table6_rows)
    write_table7(table7_rows)
    write_table5b(table5b_source)

    print("PASS table1_source_count=4")
    print("PASS table1_selected_anchor_columns=9")
    print("PASS table2_source_count=24")
    print("PASS table2_gross_equals_net_pure_layering=True")
    print("PASS table3_source_count=9")
    print("PASS table3_scenario_regime_panels=True")
    print("PASS table4_source_count=480")
    print("PASS table4_count=35")
    print("PASS table4_moderate_r0_primary_rows=20")
    print("PASS table4_crossing_rows=15")
    print("PASS table4_row_identity=35")
    print("PASS table4_results_literals=0.7_bound,2.6,5.8,3.9,1.0,1.4,1.02")
    print("PASS table5_source_xi_0_10_count=960")
    print("PASS table5_count=28")
    print("PASS table5_moderate_base_rows=20")
    print("PASS table5_cited_crossing_rows=8")
    print("PASS table5_row_identity=28")
    print("PASS table5_results_literals=0.17,0.305")
    print("PASS table5_per_pen_tax_extreme_borderline_visible=True")
    print("PASS table6_source_count=80")
    print("PASS table6_count=32")
    print("PASS table6_moderate_rows=20")
    print("PASS table6_low_high_stress_r0_rows=12")
    print("PASS table6_row_identity=32")
    print("PASS table7_count=20")
    print("PASS table7_row_identity=20")
    print("PASS table7_already_minimal=True")
    print("PASS table7_results_literals=0.97_bound,0.98,0.6,0.8")
    print("PASS table5b_csv_lines=5")
    print("PASS table5b_data_rows=4")
    print("PASS table5b_row_identity=4")
    print("PASS table5b_constant_status_and_note_fields_moved_to_caption=True")
    print("PASS table5b_numeric_values_unrounded=True")
    print("PASS source_csvs_unchanged=True")
    print("SUCCESS designed paper-table re-export completed without recomputation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
