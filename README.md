# AI, Fiscal Space and Social Protection — replication package 2.0.0

Code and data supporting the revised scenario-based study of Peru, Chile, Colombia and Mexico. The package reconstructs fiscal receipts, recurring-cost frontiers, transition financing, sensitivity analyses and the separate ENAHO/CASEN household-cost comparisons.

- **Version DOI:** [10.5281/zenodo.24257720](https://doi.org/10.5281/zenodo.24257720).
- **All versions:** [10.5281/zenodo.21348534](https://doi.org/10.5281/zenodo.21348534).
- **Start here:** [four-step reproduction guide](REPRODUCING_JPM_V2.md).
- [Main manuscript](revision_jpm_v2/paso_07l/evidencia/MANUSCRITO_JPM_V2.docx): 25 pages; [technical supplement](revision_jpm_v2/paso_07l/evidencia/SUPLEMENTO_TECNICO_JPM_V2.docx): 16 pages.
- [Data availability](DATA_AVAILABILITY.md), [survey acquisition](surveys/ADQUISICION.md), [source notices](THIRD_PARTY_NOTICES.md) and [CI](CI.md).
- [Release notes](CHANGELOG.md), [citation](CITATION.cff) and [verification scope](release/VERIFICATION.md).

The complete result is `run_logs/COMPARISON_COMPLETE.json`: PASS requires 77 core outputs, 88 extension outputs, four survey tables, 164 documentary cells and the figure comparison. PASS means that the stated results were reproduced, including mixed and adverse scientific findings. It does not mean every hypothesis was supported.

The frozen aggregate inputs are included. Original ENAHO/CASEN files must be obtained separately and match the hashes in `surveys/INPUT_CONTRACT.json`; individual survey records are not redistributed. No calculated working outputs are preloaded. Files in `reference/` and equivalent reference directories are comparison targets.

Version 2.0.0 uses the scientifically verified r9 calculation. Changes made for deposit concern availability statements, release metadata, documentation and publication checks. The r9 verification record is preserved in `release/BASELINE_VERIFICATION.json`; final release-run evidence is supplied as separate release assets, identified by source-manifest hash. `RELEASE_STATUS.json` records the immutable pre-publication package state. Historical scientific-scope fields named `v2_release_ready` do not certify archive publication or journal acceptance.

Code is MIT-licensed. Data retain the file-level conditions in `LICENSE-DATA` and `provenance_public/FILE_RIGHTS.json`; these include source-specific noncommercial and share-alike terms. The accompanying manuscripts retain the author's copyright.
