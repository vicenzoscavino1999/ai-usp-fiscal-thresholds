DATASET_VERSION ?= v1.0.1-official-4c
PARAMETER_SET_ID ?= baseline-official-v2
RUN_LABEL ?= official

.PHONY: reproduce build-from-frozen-dataset run verify verify-freeze verify-extensions reproduce-extensions figures test check reproduce-deterministic reproduce-full run-diagnostics check-env determinism-check

reproduce: reproduce-full verify-freeze verify-extensions

build-from-frozen-dataset:
	python scripts/build_anchors_from_snapshot.py --dataset-version $(DATASET_VERSION) --strict-gates

run:
	python reproducibility/run_all.py --tier A --run-label $(RUN_LABEL) --parameter-set-id $(PARAMETER_SET_ID) --dataset-version $(DATASET_VERSION)

verify:
	python reproducibility/verify.py

verify-freeze:
	python reproducibility/verify_freeze.py

verify-extensions:
	python reproducibility/verify_extensions.py

reproduce-extensions:
	python reproducibility/reproduce_extensions.py

figures:
	python scripts/finalize_phase_b.py

test:
	python -m pytest

check: test verify

reproduce-deterministic:            # Tier A: Fases 2-5, exacto
	python reproducibility/run_all.py --tier A --run-label $(RUN_LABEL) --parameter-set-id $(PARAMETER_SET_ID) --dataset-version $(DATASET_VERSION)

reproduce-full:                     # Tier A + B (MC), consume snapshot congelado
	python reproducibility/run_all.py --tier B --run-label $(RUN_LABEL) --parameter-set-id $(PARAMETER_SET_ID) --dataset-version $(DATASET_VERSION)
	python scripts/run_deterministic_robustness_6a.py
	python scripts/run_diagnostics_6b.py
	python scripts/finalize_phase_b.py
	python scripts/run_h_star_extension_7_1.py
	python reproducibility/verify.py

run-diagnostics:                    # Tier D: placebo ICT, negative controls, LOSO, ablation
	python scripts/run_diagnostics_6b.py
	python scripts/finalize_phase_b.py

check-env:
	python reproducibility/run_all.py --check-env-only

determinism-check:
	python -m pytest tests/test_determinism.py tests/test_determinism_mc.py -q
