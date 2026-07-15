DATASET_VERSION ?= v1.0.1-official-4c
PARAMETER_SET_ID ?= baseline-official-v2
RUN_LABEL ?= official
BUNDLE ?= dist/zenodo_bundle_v1.1.1-rc1.zip

.PHONY: reproduce reproduce-public reproduce-restricted build-from-frozen-dataset run verify verify-freeze verify-extensions verify-extensions-all reproduce-extensions figures test check reproduce-deterministic reproduce-full run-diagnostics check-env determinism-check bundle-public verify-bundle

reproduce:                              # author-side: requires the restricted ENAHO input
	$(MAKE) verify-freeze
	$(MAKE) reproduce-full
	$(MAKE) verify-extensions-all

reproduce-public:                       # public path: skips the non-redistributable ENAHO extension
	$(MAKE) verify-freeze
	$(MAKE) reproduce-full
	$(MAKE) verify-extensions

reproduce-restricted:              # adds the ENAHO-based GMI validation (first: python scripts/17_download_enaho_sumaria.py)
	python reproducibility/verify_extensions.py --require-restricted

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

verify-extensions-all:
	python reproducibility/verify_extensions.py --require-restricted

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

bundle-public:
	python scripts/build_zenodo_bundle.py --output $(BUNDLE)

verify-bundle:
	python scripts/verify_zenodo_bundle.py $(BUNDLE)
