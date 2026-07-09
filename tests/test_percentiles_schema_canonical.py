import duckdb


CANONICAL_COLUMNS = [
    "country_id",
    "government_level",
    "revenue_concept",
    "percentile_sample",
    "p10_mfc_hist_positive",
    "p25_mfc_hist_positive",
    "p50_mfc_hist_positive",
    "p50_ci_low",
    "p50_ci_high",
    "p75_mfc_hist_positive",
    "p75_ci_low",
    "p75_ci_high",
    "p90_mfc_hist_positive",
    "p90_ci_low",
    "p90_ci_high",
    "ci_method",
    "n_years_total",
    "n_years_positive",
    "p_negative_capture",
    "p10_mfc_hist_negative",
    "p50_mfc_hist_negative",
    "p90_mfc_hist_negative",
    "support_warning",
    "dataset_version",
    "build_id",
]


def test_percentiles_schema_canonical():
    con = duckdb.connect("db/ai_usp_threshold.duckdb", read_only=True)
    try:
        df = con.execute("SELECT * FROM historical_capture_percentiles").fetchdf()
    finally:
        con.close()
    assert list(df.columns) == CANONICAL_COLUMNS
    assert set(df["percentile_sample"]) == {
        "2000plus",
        "2010plus",
        "2015plus",
        "excl_pandemic_2020_2021",
    }
    assert set(df["revenue_concept"]) == {"tax", "total_revenue"}
    assert set(df["government_level"]) == {"general_government"}
    assert df["p_negative_capture"].between(0, 1).all()
