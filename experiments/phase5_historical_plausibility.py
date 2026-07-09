"""Phase 5 wrapper: historical plausibility."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_usp.engine import run_tier_a


def run(write: bool = True):
    return run_tier_a(write=write)


if __name__ == "__main__":
    run(write=True)
