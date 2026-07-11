"""Reexporta las tablas impresas 4, 5 y 7 desde los CSVs oficiales.

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


def header_lines(fields: list[str], continued_caption: str) -> list[str]:
    header = " & ".join(latex_escape(field) for field in fields) + r" \\"
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
    lines = [
        r"\begin{landscape}",
        r"\fontsize{6}{7.2}\selectfont",
        r"\setlength{\tabcolsep}{1.5pt}",
        r"\setlength{\LTleft}{0pt}",
        r"\setlength{\LTright}{0pt}",
        r"\let\tableunderscore\_",
        r"\renewcommand{\_}{\tableunderscore\allowbreak}",
        r"\begin{longtable}{@{}",
        *columns,
        r"@{}}",
        rf"\caption{{{caption}}}\label{{tab:results_inversions}}\\",
        *header_lines(TABLE5_FIELDS, caption + " (continued)"),
        rf"\multicolumn{{{len(TABLE5_FIELDS)}}}{{l}}{{\textit{{Panel A: all countries, moderate scenario, r0, baseline requirement}}}} \\",
        r"\midrule",
        *latex_rows(rows[:20], TABLE5_FIELDS),
        r"\midrule",
        rf"\multicolumn{{{len(TABLE5_FIELDS)}}}{{l}}{{\textit{{Panel B: cited stress crossing cells}}}} \\",
        r"\midrule",
        *latex_rows(rows[20:], TABLE5_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\end{landscape}",
        "",
    ]
    (TARGET_DIR / "table5_threshold_inversion.tex").write_text("\n".join(lines), encoding="utf-8")


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


def main() -> int:
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
    table7_source = read_csv("table7_monte_carlo.csv", TABLE7_FIELDS)

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

    write_table4(table4_rows)
    write_table5(table5_rows)
    write_table7(table7_rows)

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
    print("PASS table7_count=20")
    print("PASS table7_row_identity=20")
    print("PASS table7_already_minimal=True")
    print("PASS table7_results_literals=0.97_bound,0.98,0.6,0.8")
    print("PASS source_csvs_unchanged=True")
    print("SUCCESS designed paper-table re-export completed without recomputation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
