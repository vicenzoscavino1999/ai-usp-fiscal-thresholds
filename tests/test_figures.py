from pathlib import Path

from scripts.generate_all_figures import main


ROOT = Path(__file__).resolve().parents[1]


def test_generate_all_figures_smoke_if_results_present():
    if not (ROOT / "results" / "official" / "fiscal_space_result.csv").exists():
        return
    assert main() == 0
    for country in ["PER", "CHL", "COL", "MEX"]:
        assert (ROOT / "figures" / f"heatmap_vgross_{country}.png").exists()
