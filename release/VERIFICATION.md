# Verification of version 2.0.0

The scientific baseline is r9, with a complete local and GitHub Actions PASS. `BASELINE_VERIFICATION.json` preserves that dated result, including its historical pre-publication fields. `SCIENTIFIC_BASELINE.json` records the unchanged r9 calculation/input/reference files by SHA-256. Final availability edits affect one paragraph in each Word document; the tables, equations, figure and scientific prose are unchanged.

The source package is frozen before publication. Its `RELEASE_STATUS.json` therefore records `published: false` and `distribution_stage: PREPARED_FOR_ARCHIVE`. Those fields do not monitor the external services. The DOI record and GitHub release establish publication. The final release includes a separate verification report and evidence archive identifying this source manifest. They are outside the source archive to avoid a recursive checksum dependency.

`COMPARISON_COMPLETE.json` is the complete scientific reproduction result. `PACKAGE_CHECK.json` is a static integration check. A source integrity PASS alone does not replace a complete reconstruction. The historical `v2_release_ready: false` fields in scientific reports mean that those reports do not evaluate publication; the legacy plan also retains unsupported and untestable expectations. Neither field changes the reported numerical findings.

Original survey files are not included. Complete verification with retained originals is distinguished from validation of new provider downloads. The exact input contract is mandatory in both cases. Release data and numerical reference hashes are not changed to accommodate a provider revision.
