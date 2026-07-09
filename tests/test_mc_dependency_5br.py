from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_official_monte_carlo import (
    MC_FACTOR_NOMINAL,
    MC_FACTOR_RHO08,
    MC_PAIRWISE_05_CHECK,
    V2_V3_DELTA_SOFT_THRESHOLD,
    dependency_matrix,
    dependency_scores,
    reorder_to_scores,
)


ROOT = Path(__file__).resolve().parents[1]


def test_rank_reorder_preserves_marginal_percentiles_exactly():
    rng = np.random.default_rng(20260709)
    values = rng.beta(2.0, 5.0, size=5000)
    scores = dependency_scores(MC_FACTOR_NOMINAL, len(values), rng)["q_use_target"]
    reordered = reorder_to_scores(values, scores)
    assert np.array_equal(np.sort(values), np.sort(reordered))
    before = np.percentile(values, [5, 25, 50, 75, 95])
    after = np.percentile(reordered, [5, 25, 50, 75, 95])
    assert np.allclose(before, after, atol=0.0, rtol=0.0)


def test_dependency_matrices_are_psd():
    for mode in [MC_PAIRWISE_05_CHECK, MC_FACTOR_NOMINAL, MC_FACTOR_RHO08]:
        eigenvalues = np.linalg.eigvalsh(dependency_matrix(mode).to_numpy(dtype=float))
        assert eigenvalues.min() >= -1e-10


def test_v2_to_v3_headline_deltas_stay_within_declared_soft_threshold_if_report_exists():
    path = ROOT / "results" / "official" / "mc_v2_to_v3_headline_deltas.csv"
    if not path.exists():
        return
    deltas = pd.read_csv(path)
    assert (deltas["abs_delta_prob_v_ge_1"] <= V2_V3_DELTA_SOFT_THRESHOLD).all()
    assert (deltas["abs_delta_prob_v_ge_1_10"] <= V2_V3_DELTA_SOFT_THRESHOLD).all()
