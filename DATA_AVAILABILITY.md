# Data availability and redistribution matrix

**Verification date:** 2026-07-11
**Scope:** the 15 source records in `dataset_manifest_v1.0.1-official-4c.json`
and the three post-baseline robustness snapshots. This document records the
state of the cited sites and terms on the verification date. It does not change
the frozen dataset, the pipeline, or any source license.

## Decision rule

- `raw_redistributable`: the source expressly permits redistribution, subject
  to the attribution or other conditions stated below. The public archive may
  still carry only the filtered parquet to avoid needless bulk.
- `derived_only`: the public archive carries the filtered/derived artifact,
  source metadata, script, retrieval instructions, and hashes, but not the
  downloaded source file. Source-specific license conditions continue to apply
  to the derived artifact.
- `instructions_only`: the archive carries no source data; it carries the
  recipe and, once available, the source-file hash.
- `license_check_pending`: public access was verified, but the official page
  did not state an unambiguous right to redistribute the downloaded file.

All live endpoints below were checked on 2026-07-11 with a browser user agent
and a range-limited request. HTTP `206` means that the server honored the range
request; it is a successful availability check, not a partial source record.

## Manifest anchors

| Anchor | Snapshot manifest | SHA-256 | Size |
|---|---|---:|---:|
| M1 | `reproducibility/snapshot/dataset_manifest_v1.0.1-official-4c.json` | `74ab875ba64b31fa4e757c9932c6083bc34e01f0a30540e04bd12dbc10d047c8` | 38,077 B |
| M2 | `reproducibility/snapshot/dataset_manifest_robustness-lsraw-v1.json` | `ac910af0e72f28e4dfd2c510772a54edcf4a146c01247e10f90b954074b1ba38` | 3,965 B |
| M3 | `reproducibility/snapshot/dataset_manifest_robustness-gmimicro-per-v1.json` | `cddec679283ccc7dae17d3ab13da5c94354ce4ed2db3d56be755edfe4bda6eae` | 1,653 B |
| M4 | `reproducibility/snapshot/dataset_manifest_robustness-gmimicro-chl-v1.json` | `4a777961d2e56fa739ec96c8c76c81b009ac25982cfe0c4e258b64d17d7947ca` | 1,679 B |

## Source matrix

| # | Source and exact acquisition | Repository script and parameters | Terms checked on 2026-07-11 | Verdict | Public-archive artifact and restart point | Anchor; size |
|---:|---|---|---|---|---|---|
| 1 | **WDI**. API root <https://api.worldbank.org/v2>; representative query `country/PER/indicator/NY.GDP.MKTP.CN?format=json&per_page=5` returned HTTP 200. The manifest lists all 23 indicators and four countries. | `scripts/01_download_wdi.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | WDI is public and explicitly [CC BY 4.0](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators): copying, modification, and distribution are allowed with attribution and change notice. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/wdi/wdi_country_year.parquet`; restart at `make build-from-frozen-dataset`. | M1; 51,878 B |
| 2 | **PIP**. <https://api.worldbank.org/pip/v1/pip?country=PER&povline=8.30&format=json> returned HTTP 200; the frozen pull uses `PER,CHL,COL,MEX` and lines `3.00,4.20,8.30`. | `scripts/02_download_pip.py --countries PER,CHL,COL,MEX --poverty-lines 3.00,4.20,8.30 --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | The [Poverty and Inequality Platform catalog record](https://datacatalog.worldbank.org/search/dataset/0038020/poverty-and-equity-database-poverty-and-inequality-platform) states CC BY 4.0. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/pip/pip_poverty.parquet`; restart at anchor build. | M1; 15,682 B |
| 3 | **SEDLAC**. The [CEDLAS download page](https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/) returned HTTP 206. It provides Excel tables, not the API required by the ingest contract; the official snapshot therefore records `manual_pending`. | `scripts/03_download_sedlac.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c`, then register the downloaded Excel and SHA-256 through `scripts/12_register_manual_sources.py`. | The [methodology page](https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/metodologia-sedlac/) prescribes attribution to SEDLAC (CEDLAS and World Bank), but no explicit redistribution license was found. `license_check_pending`. | `instructions_only` | No SEDLAC data file. Archive the existing `sedlac/metadata.json` recipe and the future author-independent download hash. It is non-blocking for the frozen official run. | M1; 0 B data payload |
| 4 | **OECD Revenue Statistics LAC**. The structure request <https://sdmx.oecd.org/public/rest/dataflow/OECD.CTP.TPS/DSD_REV_COMP_LAC@DF_RSLAC/1.1?references=all> returned HTTP 200. Data queries use `OECD.CTP.TPS,DSD_REV_COMP_LAC@DF_RSLAC/{ISO}......`. | `scripts/04_download_oecd_revenue.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | The [OECD open-by-default policy](https://www.oecd.org/en/about/oecd-open-by-default-policy.html) sets CC BY 4.0 as the default from 2024 and permits broad reuse with attribution, subject to identified third-party exceptions. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/oecd/oecd_revenue.parquet`; restart at anchor build. | M1; 347,976 B |
| 5 | **GRD 2025**. The current [GRD project/download page](https://www.wider.unu.edu/project/grd-government-revenue-dataset) returned HTTP 200 and requires a short information form. The author-held inputs are the Central and General Excel files plus the user guide. | `scripts/12_register_manual_sources.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --register-grd-2025 --grd-source-dir <download-dir>` | The GRD page says the data are open and free to use and gives DOI `10.35188/UNU-WIDER/GRD-2025`. The [UNU-WIDER copyright page](https://www.wider.unu.edu/about/copyright) applies CC BY-NC-SA 3.0 IGO unless another notice applies. | `derived_only` | Include `data/raw_snapshots/v1.0.1-official-4c/grd/grd_revenue.parquet` as a four-country, central/general-government contrast table, marked CC BY-NC-SA 3.0 IGO. Exclude the two Excel files and guide; a stranger can obtain them from the form and verify their hashes in M1, or start at anchor build from the filtered parquet. | M1; public 82,378 B; withheld local source files 20,903,808 B |
| 6 | **IMF WEO/GFS DataMapper**. <https://www.imf.org/external/datamapper/api/v1/NGDPD/PER> returned HTTP 206. M1 records the seven indicators and all 28 country-indicator URLs. | `scripts/06_download_imf_weo_gfs.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite`; browser `User-Agent` is set by the script. | The IMF's [Copyright and Usage](https://www.imf.org/en/about/copyright-and-terms) special data terms allow downloading, copying, derivative works, publication, and distribution of published IMF statistical data with accurate attribution and disclosure of material transformation. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/imf/imf_fiscal_macro.parquet`; restart at anchor build. | M1; 15,782 B |
| 7 | **ILOSTAT**. <https://rplumber.ilo.org/data/ref_area?id=PER_A&format=.csv.gz> returned HTTP 200; repeat with `CHL_A`, `COL_A`, and `MEX_A`. | `scripts/07_download_ilostat.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | ILOSTAT's [dissemination page](https://ilostat.ilo.org/about/dissemination-and-analysis/) says its data are free to use and supplies required citations; it also documents systematic reuse by other organizations. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/ilostat/ilostat_labor.parquet`; restart at anchor build. | M1; 43,102,934 B (41.11 MiB) |
| 8 | **PWT 10.01**. Dataverse endpoint <https://dataverse.nl/api/access/datafile/354098> returned HTTP 200. | `scripts/08_download_pwt.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | The [PWT 10.01 release page](https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt1001?lang=en) and [Dataverse record](https://dataverse.nl/dataset.xhtml?persistentId=doi:10.34894/QT5BCC) state CC BY 4.0 and the required Feenstra-Inklaar-Timmer citation. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/pwt/pwt_country_year.parquet`; restart at anchor build. | M1; 17,348 B |
| 9 | **ITU DataHub plus WDI fallback**. The ITU collection endpoint <https://api.datahub.itu.int/v2/data/download/byid/100095/iscollection/true> returned HTTP 200; four WDI digital series are pulled for all economies. | `scripts/09_download_itu.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite`; by design `--countries` does not filter the international panel. | [ITU DataHub terms](https://beta.datahub.itu.int/about/) license ITU data under CC BY-NC-SA 3.0 IGO for non-commercial use; WDI fallback rows are CC BY 4.0. The stricter ITU terms govern the mixed artifact. | `derived_only` | `data/raw_snapshots/v1.0.1-official-4c/itu/itu_digital.parquet`, carrying the ITU license and attribution; restart at anchor build. | M1; 271,817 B |
| 10 | **IMF AIPI via World Bank Data360**. <https://data360api.worldbank.org/data360/data?DATABASE_ID=IMF_AI> returned HTTP 200 and the script retains all economies. | `scripts/10_download_aipi.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite`; the country option is intentionally ignored for frontier construction. | [Data360 terms](https://data360.worldbank.org/en/about) warn that third-party data follow the provider's terms. AIPI identifies IMF as provider, so the IMF statistical-data reuse terms cited in row 6 apply. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/imf_aipi/aipi.parquet`; restart at anchor build. | M1; 14,337 B |
| 11 | **Peru national BCRPData**. Representative query <https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PM10103FA/json/2024/2024> returned HTTP 200. Exact annual and quarterly code lists and date ranges are in M1. | `scripts/11_download_national_sources.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite`; only PER is operational, and SUNAT remains a manual optional contrast. | [BCRPData conditions](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso) permit total or partial reproduction without prior authorization when the source is cited. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/national/national_per_bcrp.parquet`; restart at anchor build. No SUNAT file is represented as available. | M1; 14,309 B |
| 12 | **Manual source registry**. This is package-authored metadata, not an external data provider. Its canonical input is `metadata/manual_source_registry.yml`. | `scripts/12_register_manual_sources.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c`; add `--register-grd-2025` only when rebuilding row 5. | Repository-authored factual registry; external files named in it retain their own terms and are not thereby relicensed. | `raw_redistributable` for the registry itself | Include `metadata/manual_source_registry.yml` and `data/raw_snapshots/v1.0.1-official-4c/manual/manual_source_registry.parquet`; restart at anchor build. | M1; 6,239 B YAML + 11,095 B parquet |
| 13 | **Frontier benchmark (Eurostat)**. <https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/isoc_eb_ai?format=JSON> returned HTTP 200. The source layer captures EU economies and does not select the calibrated benchmark set. | `scripts/13_download_frontier_benchmark.py --countries PER,CHL,COL,MEX --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | [Eurostat's copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice) authorizes commercial and non-commercial reuse of statistical data with source acknowledgement and change notice, subject to listed third-party exceptions. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/frontier/frontier_benchmark.parquet`; restart at anchor build. The pending USA manual benchmark is not used by the frozen benchmark choice. | M1; 195,065 B |
| 14 | **UN WPP 2024**. The exact bulk file <https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz> returned HTTP 206. | `scripts/14_download_wpp_projections.py --countries PER,CHL,COL,MEX --start-year 2024 --end-year 2035 --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | WPP 2024 materials and the [Population Data Portal API](https://population.un.org/dataportalapi/index.html) identify CC BY 3.0 IGO. | `raw_redistributable` | `data/raw_snapshots/v1.0.1-official-4c/wpp/wpp_projections.parquet`; restart at anchor build. The full bulk need not be duplicated in Zenodo. | M1; 115,104 B |
| 15 | **Ookla Speedtest Open Data**. The [AWS registry record](https://registry.opendata.aws/speedtest-global-performance/) returned HTTP 200. M1 records exact fixed/mobile tile URLs for 2024Q4 and 2026Q1. Country polygons come from [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), which is public domain. | `scripts/15_download_ookla.py --countries PER,CHL,COL,MEX --year 2024 --quarter 4 --period-start 2024-10-01 --raw-root data/raw_snapshots/v1.0.1-official-4c --overwrite` | The AWS record confirms CC BY-NC-SA 4.0. Redistribution and adaptations are non-commercial and share-alike; attribution is required. | `derived_only` | Include `data/raw_snapshots/v1.0.1-official-4c/ookla/ookla_speedtest.parquet`, `data/model_inputs/digital_gap_anchor.parquet`, and `reports/gap_index_baseline-official-v1.csv`, all with the Ookla caveat. Exclude four tile caches and the local boundary copy. Restart at anchor build. | M1; public 38,683 B; withheld cache/reference 1,081,825,287 B (1.01 GiB) |
| 16 | **UN SNA labor share (`robustness-lsraw-v1`)**. Eight exact UNdata requests combine country codes `604/152/170/484` with groups `401` (compensation) and `101` (GDP); a representative request returned HTTP 200. | `scripts/16_download_un_sna_labor_share.py` with its default `--output-dir data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share` and M2 manifest path. | [UNdata conditions](https://data.un.org/Host.aspx?Content=UNdataUse) say data and metadata may be copied, duplicated, and further distributed when UNdata is cited. | `raw_redistributable` | Include `data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share/un_sna_labor_share_raw.parquet`; the eight ZIPs are legally redistributable but unnecessary. Restart with `python scripts/run_ls_raw_robustness_extension.py`. | M2; parquet 12,748 B; complete local source snapshot 194,134 B |
| 17 | **INEI ENAHO 2024 Sumaria (`robustness-gmimicro-per-v1`)**. <https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip> returned HTTP 206 without login. | `scripts/17_download_enaho_sumaria.py` with its default output directory and M3 manifest path. | The [INEI Microdatos portal](https://proyectos.inei.gob.pe/microdatos/index.htm) says it "pone a disposición del público en general el sistema de Microdatos." The [national open-data record for ENAHO 2024](https://datosabiertos.gob.pe/dataset/encuesta-nacional-de-hogares-enaho-2024-instituto-nacional-de-estad%C3%ADstica-e-inform%C3%A1tica-%E2%80%93) states `Open Data Commons Open Database License (ODbL)`, but lists only a sample CSV, not the Module 34 ZIP used here. The INEI portal and the DL 604/DS 043-2001-PCM confidentiality framework do not explicitly extend that redistribution license to this exact binary. `license_check_pending` remains. | `derived_only` | Do not publish the row-level required-variable parquet while the license scope remains unconfirmed. Publish aggregate validation/cost/class-change reports, the fetch and runner scripts, URL, and M3 hashes. From scratch, run `scripts/17_download_enaho_sumaria.py`, then `scripts/run_gmi_microdata_robustness_extension.py`; operationally the runner starts from the derived parquet without the ZIP or DTA. | M3; public aggregate payload only; local derived parquet 596,893 B; raw ZIP+DTA 37,154,738 B |
| 18 | **MDSF CASEN 2024 (`robustness-gmimicro-chl-v1`)**. <https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/casen_2024.sav> returned HTTP 206 without login. | `scripts/18_download_casen_2024.py` with its default output directory and M4 manifest path. | The official [2024 note of use](https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/Nota_uso_bases_de_datos_Casen_2024.pdf) states that the databases are published through Observatorio Social and BIDAT and that identifying information is excluded. [BIDAT's terms](https://bidat.gob.cl/terminos-de-uso) expressly allow: "Compartir — copiar y redistribuir el material en cualquier medio o formato para cualquier propósito, incluso comercialmente," under CC BY 4.0 with attribution and change notice. | `raw_redistributable`; the archive selects the smaller derived extract | Include `data/raw_snapshots/robustness-gmimicro-chl-v1/casen_2024/casen_2024_gmi_required_variables.parquet`, metadata, and aggregate extension reports under CC BY 4.0; exclude the `.sav` and codebook for size, not legal restriction. Restart with `python scripts/run_gmi_microdata_chl_robustness_extension.py`; the runner needs only the derived parquet. | M4; public 3,576,424 B; omitted raw SAV+codebook 749,898,052 B (715.16 MiB) |

## Portal-independence insurance

The frozen hashes, not a provider's current filename, identify the inputs used
by the published extensions. If a portal later returns a file with a different
hash, it is a different version: retain it separately, record the retrieval
date and source URL, compare it with the frozen file, and never overwrite the
published snapshot in place.

| Source | Primary and alternative retrieval pages | Frozen raw verification anchor | Archived pages saved 2026-07-11 |
|---|---|---|---|
| ENAHO 2024 Sumaria | Binary: <https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip>. Primary portal: <https://proyectos.inei.gob.pe/microdatos/index.htm>. Query alternative: <https://proyectos.inei.gob.pe/microdatos/Consulta_por_Encuesta.asp?CU=19558%2F>. National catalog alternative: [ENAHO 2024](https://datosabiertos.gob.pe/dataset/encuesta-nacional-de-hogares-enaho-2024-instituto-nacional-de-estad%C3%ADstica-e-inform%C3%A1tica-%E2%80%93). | M3: ZIP `5ee98dad87810d42d7e252401d8366feac2fbce151c7af986d9644a40952567c`, 15,935,617 B; extracted DTA `491066f6049b0debc542739ea379e66e8eac8912162e31c5628114aae3c4592d`, 21,219,121 B. | [Portal](https://web.archive.org/web/20260711200041/https://proyectos.inei.gob.pe/microdatos/index.htm); [query page](https://web.archive.org/web/20260711200118/https://proyectos.inei.gob.pe/microdatos/Consulta_por_Encuesta.asp?CU=19558%2F). Saving the national-catalog page failed with Wayback HTTP 523; its live URL remains recorded. |
| CASEN 2024 | Binary: <https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/casen_2024.sav>. Primary page: <https://observatorio.ministeriodesarrollosocial.gob.cl/encuesta-casen-2024>. BIDAT alternatives: <https://bidat.gob.cl/catalogo-de-datos> and dataset `105286d9-10a8-410a-b060-a335f3168a46`. | M4: SAV `ac2d48b5c0b17f6e9c9744dd55853d1021248e2d985d173871338abfe3c8758f`, 749,656,107 B; codebook `c78453bb68ca55cd0201d5421c14a6fee80028e40b6ece639e6a5c6c8b7d4f74`, 241,945 B. Derived extract: `8be9a199edda2c9490482d4cd1cf9a3817bd4fe8bc93dcf7563854862ebe8ab1`, 3,576,424 B. | [Observatorio page](https://web.archive.org/web/20260711195912/https://observatorio.ministeriodesarrollosocial.gob.cl/encuesta-casen-2024); [BIDAT catalog](https://web.archive.org/web/20260711200310/https://bidat.gob.cl/catalogo-de-datos); [dataset route](https://web.archive.org/web/20260711200025/https://bidat.gob.cl/details/ficha/dataset/105286d9-10a8-410a-b060-a335f3168a46/catalogo-datos); [BIDAT terms](https://web.archive.org/web/20260711200343/https://bidat.gob.cl/terminos-de-uso). |
| SEDLAC | Primary English page: <https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/>. Spanish alternative: <https://www.cedlas.econo.unlp.edu.ar/wp/estadisticas/sedlac/>. | M1 records `manual_pending`: no source file, size, or SHA-256 was frozen. A future file is not part of the official snapshot until registered and hashed through script 12. | [English download page](https://web.archive.org/web/20260711200152/https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/). |

The baseline is portal-independent once the lightweight official snapshot is
restored: start with `make build-from-frozen-dataset`. The LS-raw and CASEN
extensions start directly from their archived derived parquets and independent
runners. The ENAHO runner also starts from its derived parquet without the raw
ZIP/DTA, but that extract is not placed in the public archive until the exact
Module 34 redistribution terms are confirmed; a third party can recreate it
from the direct public URL and M3 recipe without contacting the author.

## How to fully reproduce from scratch

1. Check out the tagged release and create the pinned environment described in
   `README.md`. Do not begin from live APIs when reproducing the published
   numbers; first restore the public frozen parquets and the four manifests to
   the paths listed above.
2. Verify the four manifest files against the SHA-256 values M1-M4. Then verify
   every included parquet against its `raw_files[].sha256` entry. These are
   exact Tier C checks; there is no numeric tolerance.
3. For an independent live reconstruction, run scripts `01`-`15` with the
   parameters in the matrix. Scripts `01`, `02`, `04`, and `06`-`15` are
   automatic. SEDLAC is optional and remains `manual_pending`. GRD requires the
   stranger to complete UNU-WIDER's short download form, place the three files
   in a local intake directory, and run script `12` with `--register-grd-2025`;
   no contact with the author is needed.
4. Compare every rebuilt file to M1. Live providers may revise data, so a new
   pull need not reproduce the old hash. To reproduce the paper, use the
   archived frozen parquet; to audit provenance, compare the live rebuild and
   preserve its new hash under a new `dataset_version`.
5. Run `make build-from-frozen-dataset DATASET_VERSION=v1.0.1-official-4c` (or
   `python scripts/build_anchors_from_snapshot.py --dataset-version
   v1.0.1-official-4c --strict-gates`). This is the earliest author-independent
   restart point for the official pipeline.
6. Run `make reproduce-deterministic`, `make reproduce-full`, and `make verify`
   according to `README.md`. These commands consume the frozen snapshot and do
   not contact data providers.
7. For robustness inputs, restore the archived UN SNA and CASEN derived
   parquets and verify M2/M4. Until ENAHO redistribution is confirmed, run
   script `17` once to recreate its required-variable parquet and verify M3.
   Then run the three extension runners named in rows 16-18 and
   `python reproducibility/verify_extensions.py`.
8. For `instructions_only` or withheld raw inputs, retain the downloaded file
   outside the public repository and compare its SHA-256 with the relevant
   manifest before processing. A mismatch means a provider revision, not the
   published frozen dataset.

## What the public archive contains

The proposed release payload contains:

- the source scripts, environment lock files, four snapshot manifests, and each
  source `metadata.json`;
- the 14 available filtered parquets from M1 (SEDLAC has none), plus the UN SNA
  and CASEN robustness parquets: 16 parquet files totaling 47,862,563 bytes
  (45.65 MiB);
- `metadata/manual_source_registry.yml`, the generated model-input anchors,
  canonical outputs, reports, and extension amendment records;
- the aggregate `gap_index` artifacts and the GRD four-country contrast parquet
  under their source-specific non-commercial/share-alike notices;
- the column-reduced CASEN required-variable parquet, not its 715.16 MiB source
  payload; ENAHO contributes aggregate validation/cost/class-change reports,
  scripts, URLs, and M3 hashes while its exact redistribution scope is pending;
  and
- instructions and recorded hashes for SEDLAC, GRD source workbooks, Ookla tile
  caches, ENAHO source files, and CASEN source files.

With those files, a stranger starts the official run at
`make build-from-frozen-dataset`, the LS-raw and CASEN extensions at their
runner scripts, and ENAHO by executing its public fetch script once before its
runner. Reconstructing the source layer requires no contact with the author.

## License-policy closure

1. The Ookla check is closed: the live AWS registry still states CC BY-NC-SA
   4.0. The existing `LICENSE-DATA` decision not to redistribute raw tiles and
   to archive the derived `gap_index` with attribution and the license caveat is
   consistent with the source terms.
2. `LICENSE-DATA` now labels `grd_revenue.parquet` CC BY-NC-SA 3.0 IGO,
   retaining UNU-WIDER attribution, DOI, and share-alike instead of applying
   the package's generic CC BY 4.0 notice.
3. `LICENSE-DATA` now distinguishes redistributable filtered extracts and
   derived artifacts enumerated here from withheld provider source files under
   `data/`.
4. CASEN redistribution is confirmed by the BIDAT CC BY 4.0 terms and its
   required-variable extract is archivable. ENAHO remains under the explicit
   microdata fallback: aggregate outputs, scripts, URL, and hashes only until
   the exact Module 34 redistribution scope is confirmed.
5. `license_check_pending` remains only for SEDLAC and ENAHO. CASEN is closed;
   no other row was pending on the verification date.
