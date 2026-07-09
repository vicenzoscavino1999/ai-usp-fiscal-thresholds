import numpy as np

from scripts.run_official_monte_carlo import pert_draw, summarize_probabilities


def test_determinism_mc_pert_draws_same_seed():
    rng_a = np.random.default_rng(np.random.SeedSequence(20260709))
    rng_b = np.random.default_rng(np.random.SeedSequence(20260709))
    a = pert_draw(0.1, 0.2, 0.4, 1000, rng_a)
    b = pert_draw(0.1, 0.2, 0.4, 1000, rng_b)
    assert np.array_equal(a, b)


def test_determinism_mc_summary_same_arrays():
    arrays = {
        "v_gross": np.array([0.8, 1.0, 1.2, 1.4, 1.6]),
        "fs_eff": np.array([0.008, 0.010, 0.012, 0.014, 0.016]),
        "basic_valid": np.array([True, True, True, True, True]),
        "support_valid": np.array([True, True, True, True, True]),
        "threshold_computable": np.array([True, True, True, True, True]),
    }
    policy = {
        "policy_id": "PEN",
        "policy_variant_id": "PEN",
        "gmi_version": None,
        "cost_gross_gdp": 0.01,
    }
    first = summarize_probabilities(
        arrays=arrays,
        country="PER",
        policy=policy,
        scenario="mid",
        regime="r0",
        mc_mode="MC_independent_baseline",
        converged=True,
        support_threshold=0.9,
        spb_plus_gdp=0.0,
    )
    second = summarize_probabilities(
        arrays=arrays,
        country="PER",
        policy=policy,
        scenario="mid",
        regime="r0",
        mc_mode="MC_independent_baseline",
        converged=True,
        support_threshold=0.9,
        spb_plus_gdp=0.0,
    )
    assert first == second
    all_draw = [row for row in first if row["prob_basis"] == "all_draw"][0]
    assert all_draw["prob_v_ge_1_10"] == 0.6
