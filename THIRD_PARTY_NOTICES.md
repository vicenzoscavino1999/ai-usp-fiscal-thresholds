# Source notices and attribution

Terms reviewed on 2026-11-14 (America/Lima). Snapshot retrieval dates are listed separately. The following sources do not endorse this study. Links and provider conditions remain applicable to the relevant components. No raw individual survey data are distributed.

## WDI: World Development Indicators

**Terms:** CC-BY-4.0.

Attribute World Bank and indicator providers; identify changes; retain indicator-specific notices. All 23 included indicators have License_Type CC BY-4.0 in checked API metadata.

**Attribution:** World Bank, World Development Indicators; underlying providers listed in WDI_INDICATOR_LICENSES.json.

**Official sources:** [Source 1](https://data.worldbank.org/summary-terms-of-use), [Source 2](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators).

**Frozen retrieval:** 2026-07-08T22:11:21.840347+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/wdi/metadata.json`.

**Project transformation:** WDI API pull for Plan 01 raw_wdi_indicator.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/wdi/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/wdi/wdi_country_year.parquet`.

## PIP: Poverty and Inequality Platform

**Terms:** CC-BY-4.0.

Attribute World Bank PIP and underlying survey source where identified; mark transformations. Included data are country aggregates, not survey records.

**Attribution:** World Bank, Poverty and Inequality Platform (PIP).

**Official sources:** [Source 1](https://datacatalog.worldbank.org/search/dataset/0038020/poverty-and-equity-database-poverty-and-inequality-platform), [Source 2](https://data.worldbank.org/summary-terms-of-use).

**Frozen retrieval:** 2026-07-08T22:13:47.751268+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/pip/metadata.json`.

**Project transformation:** PIP REST pull preserving unit/currency/periodicity/ppp fields required by Plan 01 section 13.4.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/pip/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/pip/pip_poverty.parquet`.

## OECD_REVSTAT_LAC: Revenue Statistics in Latin America and the Caribbean

**Terms:** OECD data terms.

Data section allows extraction, adaptation and redistribution including commercial use, with acknowledgement and terms communicated to downstream users; retain any third-party exceptions. Do not substitute the separate written-content policy.

**Attribution:** OECD, Revenue Statistics in Latin America and the Caribbean, SDMX DSD_REV_COMP_LAC@DF_RSLAC.

**Official sources:** [Source 1](https://www.oecd.org/en/about/terms-conditions.html).

**Frozen retrieval:** 2026-07-08T22:20:05.375692+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/oecd/metadata.json`.

**Project transformation:** OECD Revenue Statistics LAC via SDMX; structure request precedes PER-filtered CSV data query.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/oecd/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/oecd/oecd_revenue.parquet`.

## GRD: Government Revenue Dataset 2025

**Terms:** CC-BY-NC-SA-3.0-IGO.

Noncommercial reuse, attribution, indication of changes and share-alike. Filtered central/general-government extract included; original Excel workbooks and guide are excluded.

**Attribution:** UNU-WIDER (2025). UNU-WIDER Government Revenue Dataset. Version 2025. Helsinki: UNU-WIDER. https://doi.org/10.35188/UNU-WIDER/GRD-2025

**Official sources:** [Source 1](https://www.wider.unu.edu/about/copyright), [Source 2](https://www.wider.unu.edu/database/data-and-resources-grd), [Source 3](https://creativecommons.org/licenses/by-nc-sa/3.0/igo/).

**Frozen retrieval:** 2026-07-08T23:28:21.343255+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/grd/metadata.json`.

**Project transformation:** UNU-WIDER GRD 2025 manually registered by author; central and general workbooks converted to one filtered parquet retaining government_level.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/grd/grd_revenue.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/grd/metadata.json`.

## IMF_WEO_GFS: IMF DataMapper WEO and Fiscal Monitor series

**Terms:** IMF statistical data terms.

Accurate IMF attribution, explicit material transformations and communication of terms. Current terms direct potential commercial reuse to IMF permission. No claim of a CC licence. Fiscal series use Fiscal Monitor aliases, not an unqualified WEO/GFS bulk extract.

**Attribution:** International Monetary Fund, WEO / Fiscal Monitor data via IMF DataMapper, https://www.imf.org/external/datamapper/.

**Official sources:** [Source 1](https://www.imf.org/en/About/copyright-and-terms).

**Frozen retrieval:** 2026-07-08T22:20:30.718335+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/imf/metadata.json`.

**Project transformation:** IMF DataMapper API pull using browser User-Agent; response filtered explicitly to requested ISO3 countries. Fiscal Monitor DataMapper aliases are used where the requested WEO-style codes are not exposed in the public indicator catalog.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/imf/imf_fiscal_macro.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/imf/metadata.json`.

## ILOSTAT: ILOSTAT annual country aggregates

**Terms:** CC-BY-4.0.

ILO data/metadata published from 3 May 2023 are CC BY 4.0 unless otherwise indicated. Credit ILO and mark adaptations. This does not license restricted partner microdata; none are included.

**Attribution:** International Labour Organization, ILOSTAT, annual country aggregate statistics.

**Official sources:** [Source 1](https://www.ilo.org/rights-and-permissions), [Source 2](https://ilostat.github.io/Rilostat/).

**Frozen retrieval:** 2026-07-08T22:25:47.966886+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/ilostat/metadata.json`.

**Project transformation:** ILOSTAT bulk ref_area annual files. classif1/classif2 are mapped only when prefixes identify age, sector, or occupation.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/ilostat/ilostat_labor.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/ilostat/metadata.json`.

## PWT_10_01: Penn World Table 10.01

**Terms:** CC-BY-4.0.

Credit PWT authors and version; identify the four-country extraction and transformations.

**Attribution:** Feenstra, R. C., Inklaar, R. and Timmer, M. P. (2015), The Next Generation of the Penn World Table, American Economic Review 105(10):3150–3182. PWT 10.01: https://doi.org/10.34894/QT5BCC.

**Official sources:** [Source 1](https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt1001?lang=en).

**Frozen retrieval:** 2026-07-08T22:25:54.714811+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/pwt/metadata.json`.

**Project transformation:** PWT 10.01 Stata .dta via DataverseNL API.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/pwt/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/pwt/pwt_country_year.parquet`.

## ITU_DATAHUB_WDI_FALLBACK: ITU coverage and WDI fallback rows

**Terms:** Mixed: ITU CC-BY-NC-SA-3.0-IGO; WDI CC-BY-4.0.

ITU_* coverage rows retain noncommercial/share-alike and attribution terms. Other rows retain WDI indicator terms. Do not label the whole parquet CC BY. Include access date and no endorsement; derived coverage/speed Gap retains source conditions.

**Attribution:** International Telecommunication Union, ITU DataHub, https://datahub.itu.int/; World Bank WDI for explicitly labelled fallback rows.

**Official sources:** [Source 1](https://datahub.itu.int/about/), [Source 2](https://creativecommons.org/licenses/by-nc-sa/3.0/igo/), [Source 3](https://data.worldbank.org/summary-terms-of-use).

**Evidence scope:** Official indexed DataHub terms available; direct page open returned 403.

**Frozen retrieval:** 2026-07-08T22:26:29.025966+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/itu/metadata.json`.

**Project transformation:** Plan 01 rule keeps frontier/benchmark inputs unfiltered. This script captures all economies even when --countries is passed. ITU DataHub coverage series are the official excluded digital Gap inputs; legacy WDI fallback rows are retained only for audit/frontier context.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/itu/itu_digital.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/itu/metadata.json`.

## IMF_AIPI_DATA360: AI Preparedness Index, IMF via World Bank Data360

**Terms:** IMF statistical data terms; World Bank third-party conditions.

Identify IMF as origin and Data360 as distributor; preserve IMF terms, not a blanket World Bank CC licence. Material transforms must be identified; commercial reuse follows IMF permission condition.

**Attribution:** International Monetary Fund, AI Preparedness Index, retrieved through World Bank Data360 (IMF_AI).

**Official sources:** [Source 1](https://www.imf.org/en/About/copyright-and-terms), [Source 2](https://data.worldbank.org/summary-terms-of-use).

**Frozen retrieval:** 2026-07-08T22:26:30.771950+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/imf_aipi/metadata.json`.

**Project transformation:** Downloaded all AIPI economies as required for frontier benchmark. --countries was accepted (['PER', 'CHL', 'COL', 'MEX']) but not used to filter AIPI.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/imf_aipi/aipi.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/imf_aipi/metadata.json`.

## NATIONAL_PER_BCRP: BCRPData national contrast series

**Terms:** BCRPData attribution terms.

BCRP permits full or partial reproduction with source citation. Keep originating institution attribution for third-party series; do not imply endorsement.

**Attribution:** Banco Central de Reserva del Perú, BCRPData, https://estadisticas.bcrp.gob.pe/estadisticas/series/.

**Official sources:** [Source 1](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso).

**Frozen retrieval:** 2026-07-08T22:26:33.272577+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/national/metadata.json`.

**Project transformation:** BCRPData API implemented for Peru macro-fiscal contrast series; SUNAT Excel tables are manual_registered.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/national/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/national/national_per_bcrp.parquet`.

## FRONTIER_BENCHMARK: Eurostat enterprise AI adoption isoc_eb_ai

**Terms:** Eurostat statistical-data reuse terms.

Acknowledge Eurostat, identify changes and retain third-party exceptions. Statistical-data reuse is governed by the stated EU reuse policy; do not confuse with copyright in publications.

**Attribution:** Eurostat, isoc_eb_ai, AI use by enterprises; project-selected benchmark economies.

**Official sources:** [Source 1](https://ec.europa.eu/eurostat/help/copyright-notice).

**Frozen retrieval:** 2026-07-08T22:26:39.784175+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/frontier/metadata.json`.

**Project transformation:** Captured Eurostat isoc_eb_ai adoption_proxy inputs. No benchmark set is selected here; Phase 1 calibration chooses the benchmark population.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/frontier/frontier_benchmark.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/frontier/metadata.json`.

## UN_WPP: World Population Prospects 2024

**Terms:** CC-BY-3.0-IGO.

Attribute UN DESA Population Division, revision and variant; identify extraction and aggregations. Single-age/sex country population counts are aggregate statistics.

**Attribution:** United Nations, Department of Economic and Social Affairs, Population Division (2024). World Population Prospects 2024, medium variant, single-age/sex population projections.

**Official sources:** [Source 1](https://population.un.org/dataportalapi/index.html), [Source 2](https://population.un.org/wpp/), [Source 3](https://creativecommons.org/licenses/by/3.0/igo/).

**Evidence scope:** Licence shown in official Data Portal API indexed page; WPP 2024 bulk file identified by frozen metadata.

**Frozen retrieval:** 2026-07-08T22:26:59.203302+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/wpp/metadata.json`.

**Project transformation:** UN WPP 2024 bulk CSV, Standard Projections, single-age/sex, medium variant. No five-year age groups or 65+/15-64/18+ aggregates are constructed in raw ingest.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/wpp/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/wpp/wpp_projections.parquet`.

## OOKLA_SPEEDTEST_OPEN_DATA: Ookla Speedtest global performance

**Terms:** CC-BY-NC-SA-4.0.

Noncommercial reuse, attribution, changes and share-alike. Country aggregates remain subject to source terms. Raw tiles are excluded. Apply conditions also to relevant derived data, not only to a file named gap_index.

**Attribution:** Ookla, Speedtest Global Performance / Speedtest by Ookla Global Fixed and Mobile Network Performance Maps, 2024 Q4 and 2026 Q1; 2024 Q4 used for the baseline Gap.

**Official sources:** [Source 1](https://registry.opendata.aws/speedtest-global-performance/), [Source 2](https://creativecommons.org/licenses/by-nc-sa/4.0/).

**Frozen retrieval:** 2026-07-08T22:32:31.423457+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/ookla/metadata.json`.

**Project transformation:** Country-level speed anchors derived from AWS Ookla parquet tiles. The official Gap uses the 2024Q4 anchor period; the latest available period is also downloaded and aggregated for source completeness. Older full history is not downloaded because it is not cheap.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/ookla/metadata.json`, `upstream/data/raw_snapshots/v1.0.1-official-4c/ookla/ookla_speedtest.parquet`.

## UN_SNA: UNdata System of National Accounts

**Terms:** UNdata use terms.

Data and metadata may be copied and distributed with reference to UNdata. Identify filtering and the compensation/GDP calculation; preserve originating national-statistics attribution.

**Attribution:** United Nations Statistics Division, UNdata SNA, compensation of employees (D.1), Table 4.1/group 401, and GDP at market prices (B.1*g), group 101.

**Official sources:** [Source 1](https://data.un.org/Host.aspx?Content=UNdataUse).

**Frozen retrieval:** 2026-07-10T17:54:23.063341+00:00. **Metadata:** `upstream/data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share/metadata.json`.

**Project transformation:** New input series for the declared LS raw-vs-adjusted robustness extension. It is isolated from every official baseline snapshot.

**Included files:** `upstream/data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share/metadata.json`, `upstream/data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share/un_sna_labor_share_raw.parquet`.

## NATURAL_EARTH: Natural Earth country boundaries

**Terms:** Public domain.

Boundary data were used upstream for country aggregation; geometry is not included in this package.

**Attribution:** Made with Natural Earth.

**Official sources:** [Source 1](https://www.naturalearthdata.com/about/terms-of-use/).

## MANUAL_SOURCE_REGISTRY: Manual source registration

**Terms:** Project-authored metadata.

The registry contains descriptions and URLs, not permission grants or proof that all listed datasets were acquired.

**Attribution:** Project source registry.

**Frozen retrieval:** 2026-07-08T23:28:21.356254+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/manual/metadata.json`.

**Project transformation:** Created metadata/manual_source_registry.yml and mirrored it as parquet for the snapshot manifest.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/manual/manual_source_registry.parquet`, `upstream/data/raw_snapshots/v1.0.1-official-4c/manual/metadata.json`.

## SEDLAC: CEDLAS / World Bank SEDLAC

**Terms:** Redistribution not established for a payload.

Only acquisition-status metadata are included. No SEDLAC numerical payload is distributed or required by the current reconstruction. Exclude any newly added payload until its terms are established.

**Attribution:** CEDLAS and World Bank, SEDLAC.

**Official sources:** [Source 1](https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/).

**Frozen retrieval:** 2026-07-08T22:13:47.900266+00:00. **Metadata:** `upstream/data/raw_snapshots/v1.0.1-official-4c/sedlac/metadata.json`.

**Project transformation:** SEDLAC/CEDLAS has no public API for this pull; registered as manual_pending, not as a pipeline failure.

**Included files:** `upstream/data/raw_snapshots/v1.0.1-official-4c/sedlac/metadata.json`.

## MIDIS_PENSION65: Peru Pensión 65, 2024

**Terms:** Cited factual parameter; no source publication redistributed.

Only stated amounts/eligibility conventions and citation are used, not article text, images or provider databases. No general licence over the provider website is asserted. S/250 bimonthly; model annualizes to S/1500.

**Attribution:** Peru Pensión 65, 2024. https://www.gob.pe/institucion/pension65/noticias/1002406-pension-65-usuarios-empiezan-a-cobrar-en-los-24-departamentos-del-pais-a-traves-de-3-modalidades

**Official sources:** [Source 1](https://www.gob.pe/institucion/pension65/noticias/1002406-pension-65-usuarios-empiezan-a-cobrar-en-los-24-departamentos-del-pais-a-traves-de-3-modalidades).

**Evidence scope:** Frozen source citation inspected in build_official_4c_anchors.py; supplementary official 2024 links added for Peru/Colombia; scientific values unchanged.

## SP_CHILE_PGU_2024: Chile PGU, 2024

**Terms:** Cited factual parameter; no source publication redistributed.

Only stated amounts/eligibility conventions and citation are used, not article text, images or provider databases. No general licence over the provider website is asserted. CLP214296 monthly from February 2024; model annualizes by 12.

**Attribution:** Chile PGU, 2024. https://www.spensiones.cl/portal/institucional/594/w3-article-15857.html

**Official sources:** [Source 1](https://www.spensiones.cl/portal/institucional/594/w3-article-15857.html).

**Evidence scope:** Frozen source citation inspected in build_official_4c_anchors.py; supplementary official 2024 links added for Peru/Colombia; scientific values unchanged.

## PROSPERIDAD_SOCIAL_COLOMBIA_MAYOR_2024: Colombia Mayor, 2024

**Terms:** Cited factual parameter; no source publication redistributed.

Only stated amounts/eligibility conventions and citation are used, not article text, images or provider databases. No general licence over the provider website is asserted. COP80000 / COP225000 by age; model applies the declared annualized reference, not actual calendar-year disbursements.

**Attribution:** Colombia Mayor, 2024. https://prosperidadsocial.gov.co/Noticias/colombia-mayor-prosperidad-social-aumenta-el-monto-de-la-transferencia-para-mayores-de-80-anos/

**Official sources:** [Source 1](https://prosperidadsocial.gov.co/Noticias/colombia-mayor-prosperidad-social-aumenta-el-monto-de-la-transferencia-para-mayores-de-80-anos/).

**Evidence scope:** Frozen source citation inspected in build_official_4c_anchors.py; supplementary official 2024 links added for Peru/Colombia; scientific values unchanged.

## BIENESTAR_MEXICO_ADULTOS_MAYORES_2024: Mexico Pensión Bienestar, 2024

**Terms:** Cited factual parameter; no source publication redistributed.

Only stated amounts/eligibility conventions and citation are used, not article text, images or provider databases. No general licence over the provider website is asserted. MXN6000 bimonthly; model annualizes by six.

**Attribution:** Mexico Pensión Bienestar, 2024. https://www.gob.mx/bienestar/prensa/2024-inicia-con-aumentos-a-pensiones-de-bienestar-anuncia-ariadna-montiel?idiom=es

**Official sources:** [Source 1](https://www.gob.mx/bienestar/prensa/2024-inicia-con-aumentos-a-pensiones-de-bienestar-anuncia-ariadna-montiel?idiom=es).

**Evidence scope:** Frozen source citation inspected in build_official_4c_anchors.py; supplementary official 2024 links added for Peru/Colombia; scientific values unchanged.

## IMF_AIPI_NOTE_COMPONENTS: AIPI component documentation

**Terms:** Citation only.

Used to document excluded indicators. The IMF note PDF is not bundled and is not relicensed.

**Attribution:** IMF, AI Preparedness Index component note.

**Official sources:** [Source 1](https://www.imf.org/external/datamapper/AIPINote.pdf).

## AUTHOR_MODEL: Author model, scenarios and methodological conventions

**Terms:** Project rights; code MIT; data contribution scoped in LICENSE-DATA.

Scenario coefficients are project choices documented in registries, not separately downloaded observations. Scientific documents remain subject to a separate publication decision.

**Attribution:** Vicenzo Scavino and project documentation.

## LITERATURE_CONTEXT: Bibliographic foundations and cited calibration anchors

**Terms:** Citation only; no full third-party papers distributed.

Literature identifiers, factual coefficients and the author’s synthesis do not grant rights to reproduce cited articles. Consult the manuscript references and frozen calibration registries.

**Attribution:** Authors and titles in the manuscript, supplement and calibration registries.

## ENAHO_2024: INEI ENAHO 2024 Module 34

**Terms:** Exact extract redistribution not established.

Absent from r5; do not infer a Module 34 ZIP licence from the licence of a different open-data sample. Exclude row-level data. Current GMI uses PIP aggregates.

**Attribution:** Instituto Nacional de Estadística e Informática, ENAHO 2024.

**Official sources:** [Source 1](https://proyectos.inei.gob.pe/microdatos/).

## CASEN_2024: CASEN 2024

**Terms:** BIDAT CC-BY-4.0 for datasets covered by its terms.

No CASEN file is included or required by r5. Any future raw extract requires a separate content/scope check; current bundle makes no claim of full microdata reconstruction.

**Attribution:** Ministerio de Desarrollo Social y Familia de Chile, CASEN 2024 / BIDAT.

**Official sources:** [Source 1](https://bidat.gob.cl/terminos-de-uso), [Source 2](https://bidat.gob.cl/details/ficha/dato/trabajo-casen-2024).

## BFJZ: Bachas, Fisher-Post, Jensen and Zucman: factor taxation

**Terms:** MIT repository notice, copyright 2021 Pierre Bachas.

Preserve the supplied copyright and MIT permission notice for the copied code and repository material. Aggregate data and their underlying provider rights are not relabelled as the project’s own data. The frozen repository contains no separate data licence notice among the files inspected.

**Attribution:** Bachas, P., Fisher-Post, M., Jensen, A. and Zucman, G., Globalization and Factor Income Taxation, repository commit a1aba1f98ce6e5bd5964be15a61fe772ea77f928.

**Official sources:** [Source 1](https://github.com/pierrebachas/Globalization_Factor_Taxation/blob/a1aba1f98ce6e5bd5964be15a61fe772ea77f928/LICENSE).

**Evidence scope:** Licence fetched through GitHub connector at the exact commit and matched to the historical local licence hash; source README directs users to the aggregate ETR dataset.

**Included files:** `revision_jpm_v2/paso_07d/conciliacion_fiscal_02/fuentes/BFJZ_ETR_4_construction.do`, `revision_jpm_v2/paso_07d/conciliacion_fiscal_02/fuentes/BFJZ_globalETR.csv`, `revision_jpm_v2/paso_07d/conciliacion_fiscal_02/fuentes/BFJZ_pit_alpha.dta`.
