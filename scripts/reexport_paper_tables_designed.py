"""Reexporta las tablas impresas 4, 5 y 7 desde los CSVs oficiales.

Se ejecuta DESPUÉS de finalize_phase_b; sustituye los .tex truncados head-N por
selecciones diseñadas; valores idénticos a los CSVs oficiales; cambio de formato
de reporte, sin recomputación.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "reports" / "paper_tables"
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

POLICY_VARIANTS = [
    "PEN",
    "GMI:GMI_ideal_aggregate",
    "GMI:GMI_loaded_aggregate",
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


def read_csv(name: str, expected_fields: list[str]) -> list[dict[str, str]]:
    path = SOURCE_DIR / name
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            raise AssertionError(f"{name}: unexpected fields {reader.fieldnames}")
        return list(reader)


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
    caption = r"Table 4. Baseline $V^{gross}$: primary-case moderate-scenario block and all crossing cells"
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
        r"\multicolumn{7}{l}{\textit{Panel A: Peru, moderate scenario, all policy variants and regimes}} \\",
        r"\midrule",
        *latex_rows(rows[:30], TABLE4_FIELDS),
        r"\midrule",
        r"\multicolumn{7}{l}{\textit{Panel B: all crossing cells}} \\",
        r"\midrule",
        *latex_rows(rows[30:], TABLE4_FIELDS),
        r"\bottomrule",
        r"\end{longtable}",
        r"\endgroup",
        "",
    ]
    (TARGET_DIR / "table4_vgross_baseline.tex").write_text("\n".join(lines), encoding="utf-8")


def write_table5(rows: list[dict[str, str]]) -> None:
    caption = "Table 5. Threshold inversion: headline cells"
    columns = [
        r">{\raggedright\arraybackslash}p{0.03\linewidth}",
        r">{\raggedright\arraybackslash}p{0.13\linewidth}",
        r">{\raggedright\arraybackslash}p{0.045\linewidth}",
        r">{\raggedright\arraybackslash}p{0.035\linewidth}",
        r">{\raggedright\arraybackslash}p{0.09\linewidth}",
        r">{\raggedright\arraybackslash}p{0.09\linewidth}",
        r">{\raggedright\arraybackslash}p{0.09\linewidth}",
        r">{\raggedright\arraybackslash}p{0.08\linewidth}",
        r">{\raggedright\arraybackslash}p{0.17\linewidth}",
        r">{\raggedright\arraybackslash}p{0.19\linewidth}",
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
        *latex_rows(rows, TABLE5_FIELDS),
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
    table5_source = read_csv("table5_threshold_inversion.csv", TABLE5_FIELDS)
    table7_source = read_csv("table7_monte_carlo.csv", TABLE7_FIELDS)

    table4_index = row_index(table4_source, ["country_id", "policy_variant_id", "scenario_id", "regime_id"])
    table4_moderate_keys = [
        ("PER", variant, "mid", regime)
        for regime in REGIMES
        for variant in POLICY_VARIANTS
    ]
    table4_crossing_source_rows = [row for row in table4_source if row["crosses_v1"] == "True"]
    if len(table4_crossing_source_rows) != 15:
        raise AssertionError(f"table4: expected 15 crossing source rows, found {len(table4_crossing_source_rows)}")
    table4_crossing_keys = [
        (country, variant, "stress", regime)
        for country, variant in [
            ("CHL", "GMI:GMI_ideal_aggregate"),
            ("CHL", "GMI:GMI_loaded_aggregate"),
            ("PER", "PEN"),
        ]
        for regime in REGIMES
    ]
    table4_rows = select_rows(
        table4_index,
        [*table4_moderate_keys, *table4_crossing_keys],
        table4_source,
        "table4",
    )
    if len(table4_rows) != 45:
        raise AssertionError(f"table4: expected 45 rows, found {len(table4_rows)}")
    if [row for row in table4_rows if row["crosses_v1"] == "True"] != select_rows(
        table4_index, table4_crossing_keys, table4_source, "table4 crossings"
    ):
        raise AssertionError("table4: not all crossing rows are present")
    if not any(
        row["country_id"] == "CHL"
        and row["policy_variant_id"] == "GMI:GMI_ideal_aggregate"
        and row["scenario_id"] == "stress"
        and row["regime_id"] == "r4"
        and row["v_gross"] == "5.799668762204835"
        for row in table4_rows
    ):
        raise AssertionError("table4: CHL ideal GMI stress r4 value is missing or changed")
    if not any(
        row["country_id"] == "PER"
        and row["policy_variant_id"] == "PEN"
        and row["scenario_id"] == "mid"
        and row["regime_id"] == "r0"
        for row in table4_rows
    ):
        raise AssertionError("table4: PER PEN mid r0 is missing")

    table5_index = row_index(
        table5_source,
        ["country_id", "policy_variant_id", "scenario_id", "regime_id", "requirement_basis"],
    )
    table5_keys = [
        (country, variant, scenario, regime, basis)
        for country, variant in HEADLINE_POLICIES
        for scenario in HEADLINE_SCENARIOS
        for regime in REGIMES
        for basis in REQUIREMENT_BASES
    ]
    table5_rows = select_rows(table5_index, table5_keys, table5_source, "table5")
    if len(table5_rows) != 40:
        raise AssertionError(f"table5: expected 40 rows, found {len(table5_rows)}")

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

    write_table4(table4_rows)
    write_table5(table5_rows)
    write_table7(table7_rows)

    print("PASS table4_count=45")
    print("PASS table4_crossing_rows=15")
    print("PASS table4_row_identity=45")
    print("PASS table4_chl_gmi_ideal_stress_r4=5.799668762204835")
    print("PASS table4_per_pen_mid_r0_present=True")
    print("PASS table5_count=40")
    print("PASS table5_row_identity=40")
    print("PASS table7_count=20")
    print("PASS table7_row_identity=20")
    print("PASS source_csvs_unchanged=True")
    print("SUCCESS designed paper-table re-export completed without recomputation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
