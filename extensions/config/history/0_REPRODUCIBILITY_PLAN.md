# Reproducibility plan — AI, Fiscal Space, and Universal Social Protection in Emerging Economies

Este documento define el paquete de reproducibilidad que acompaña al paper
*AI, Fiscal Space, and Universal Social Protection in Emerging Economies: A Robust
Accounting-Fiscal Threshold Framework* (v2.5). El objetivo no es solo publicar
código, sino hacer las afirmaciones numéricas **auditables**: un revisor debe poder
reconstruir el entorno, re-ejecutar el motor, regenerar las tablas y figuras del
paper, y verificar los resultados reportados, sin re-descargar datos que las
fuentes públicas pueden haber revisado.

El repositorio público debe crearse como repo limpio, no subiendo la carpeta de
trabajo actual.

**Exclusión explícita de artefactos de trabajo:** los archivos internos del ciclo
de trabajo — `CLAUDE.md` (estado de proyecto del asistente), notas y memoria de
agentes, prompts de corrección BUSCAR/REEMPLAZAR, borradores de rondas de revisión
y cualquier bitácora del proceso de redacción — NUNCA entran al repo público, al
build context de Docker ni al depósito Zenodo. No son artefactos de investigación
y no forman parte del layout definido abajo (que es taxativo: lo que no está en el
layout, no se sube). Si la carpeta de trabajo se versionara con git alguna vez,
estos archivos van en su `.gitignore` local.

> **Nota de alcance específica de este paper.** A diferencia de un paquete de
> pura simulación, la reproducción de este trabajo se organiza en **cuatro tiers**
> con contratos de reproducibilidad distintos:
>
> - **Tier A — Núcleo determinista.** Baseline determinístico (Fase 2), scenario-regime grid (Fase 3), threshold inversion (Fase 4) y plausibilidad histórica (Fase 5): todas son fórmulas cerradas dadas la base congelada y el parameter_set.
> - **Tier B — Monte Carlo.** Propagación de incertidumbre (Fase 6). Reproducible
>   **solo hasta el seed**; las probabilidades de cruce y percentiles se verifican
>   con tolerancia relajada calibrada, y la estabilidad se controla con
>   `mc_convergence_report`. El Experimento 8 del plan `02` (Spearman / tornado / Sobol, ranking de drivers) pertenece al Tier B porque consume draws; su verificación es de forma: el ranking de drivers principales es estable entre seeds, no valores exactos.
> - **Tier C — Snapshot de datos externos.** Los datos públicos (WDI, PIP, OECD,
>   GRD, ILOSTAT, IMF, AIPI, ITU, PWT, ASPIRE, UN WPP, fuentes nacionales) **no son
>   reproducibles re-ejecutando el pull**: las fuentes revisan sus series. El
>   contrato es *reconstrucción desde snapshot congelado y hasheado*, nunca
>   re-descarga. Este tier es el análogo económico de la "hardware carve-out" de un
>   paquete experimental.
> - **Tier D — Diagnósticos y falsificación.** Placebo ICT, negative controls,
>   leave-one-source-out, channel ablation (Fase 7). Su verificación es
>   **cualitativa** (`pass/fail` + `rank_change`), no una comparación `atol/rtol`,
>   porque su función es refutar, no coincidir numéricamente.
>
> Esta distinción se aplica a lo largo de todo el plan (ver "Tolerance tiers" y
> "Snapshot de datos externos: carve-out").

---

## Interfaz con los otros planes

La familia de documentos del proyecto es:

| Documento | Rol canónico |
|---|---|
| `01_database_construction_plan_AI_USP_threshold_framework_v6.md` | Construye, armoniza y audita la base. Define tablas raw/interim/processed, `variable_source_map`, `data_quality_report`, `assumption_registry`, `dataset_version`, `build_id`. |
| `02_ESD_AI_USP_v6.md` | Estrategia empírica y diseño de simulación. Define la especificación primaria, las fórmulas operativas, las fases 0–9, los esquemas canónicos de resultado (§19) y los `computational_validation_tests` (§20). |
| `REPRODUCIBILITY_PLAN.md` | Este documento. Define verificación, tolerancias, layout del snapshot de datos, Docker, CI, archivo Zenodo y versionado. |

No existe documento maestro separado: el layout, el orden de ejecución y los estándares de este paquete los define ESTE documento (dueño único por concern, regla anti-drift).

**Regla de conflicto:**

- `01` controla los esquemas de tablas de datos, la trazabilidad de fuentes y la
  construcción del snapshot.
- `02` controla las ecuaciones, los esquemas canónicos de las tablas de resultado
  (`fiscal_space_result`, `threshold_inversion_result`, `monte_carlo_result`,
  `diagnostic_result`, `run_manifest`), la clasificación y la disciplina de
  resultados.
- `REPRODUCIBILITY_PLAN.md` controla la mecánica de verificación, las tolerancias,
  el freezing/hashing de snapshots, la ejecución Docker, CI, el archivo Zenodo y el
  versionado. **No** redefine esquemas ni nombres de tablas de forma independiente.

**Regla de implementación:**

- `reproducibility/config/schemas.yaml` codifica los esquemas de resultado
  importados de `02` §19.
- `reproducibility/config/tolerances.yaml` define tolerancias por tier para esos
  campos.
- `reproducibility/reference/reference_manifest.json` lista los outputs canónicos
  de resultado archivados como referencia.
- `reproducibility/snapshot/dataset_manifest.json` lista los archivos raw
  congelados (Tier C) con su `raw_file_hash`, `download_date` y `dataset_version`.

> **Interfaz de pre-registro.** El plan `02` fija una especificación primaria
> (§2) y una metodología de asignación de valores y umbrales (§10) *antes* de
> generar resultados. El paquete de reproducibilidad archiva el hash SHA-256 de
> ese estado congelado (`PRIMARY_SPEC_HASH.txt`) junto al commit del código, y
> `verify.py` trata la tabla de adjudicación de hipótesis H1–H5 y la clasificación
> país-política como outputs canónicos sujetos a validación de esquema (ver
> "Adjudicación").
>
> **Mecánica del congelamiento (para que el hash no sea una trampa):** (a) el hash
> se computa sobre el CONTENIDO del archivo, no sobre su nombre — renombrar
> archivos no lo invalida; (b) el congelamiento ocurre en el paso 2 de la Fase A:
> hasta ese momento, nombres, estructura y qué entra al repo se deciden
> libremente; (c) después del congelamiento, una enmienda al plan `02` no está
> prohibida — está VISIBILIZADA: el pre-flight reporta el mismatch, la enmienda se
> documenta con nota de versión y fecha, y el estado confirmatorio de H1–H5 se
> re-declara. Lo único prohibido es re-congelar en silencio. Ante un revisor, una
> enmienda declarada es disciplina; un hash que "siempre coincide" tras cambios no
> declarados sería el verdadero problema.

---

## Decisión central

La ruta oficial de reproducción es **basada en Docker**. Docker es el entorno
base, no una capa opcional. El entorno local es útil para desarrollo, pero las
instrucciones publicadas tratan al contenedor como el entorno de ejecución
autoritativo.

Política de dependencias:

- `pyproject.toml`: metadata canónica y bounds de dependencias.
- `requirements-lock.txt`: dependencias exactas generadas dentro del contenedor,
  preferiblemente con hashes vía `pip-compile --generate-hashes`.
- Sin `environment.yml` salvo que una dependencia futura exija Conda.
- Sin `requirements.txt` suelto y sin pinear como artefacto de reproducibilidad.

Stack esperado (todo pineable, **sin servicio externo en tiempo de cómputo**):
`python`, `numpy`, `scipy`, `pandas`, `duckdb`, `pyarrow`, `pyyaml`, `pandera`,
`matplotlib`, `SALib`. La capa de ingesta (Tier C) usa
clientes de API (`wbgapi`, `requests`, `sdmx`, etc.) pero **estos no forman parte
del path de reproducción del motor**: el motor lee siempre del snapshot congelado,
nunca de una API en vivo.

PERT se implementa como Beta reescalada con `scipy.stats.beta` (sin dependencia adicional de muestreo).

---

## Snapshot de datos externos: carve-out (Tier C)

Esta sección no tiene análogo en un paquete de pura simulación y es obligatoria
aquí porque los insumos del paper son datos públicos externos.

**Principio: el pull de datos no es reproducible re-ejecutándolo.** Las fuentes
revisan sus series (una revisión del PIB 2024 de Perú mueve `MFC_hist` y reclasifica
celdas). El contrato de reproducibilidad para los datos es, por tanto,
*reconstrucción de anclas desde snapshot crudo archivado*, no re-descarga.

Reglas:

- Cada pull escribe, bajo `data/raw/<source>/`:
  - el archivo crudo (parquet),
  - `metadata.json` con `source_id`, `download_date`, `source_url`,
    `query_or_endpoint`, `raw_file_hash` (SHA-256), `script_name`, `script_version`.
- El raw es **inmutable** (regla 25.3 del plan `01`). Nada se edita ahí.
- Un `dataset_version` etiqueta un snapshot coherente de todas las fuentes.
  Re-pull = versión nueva, **nunca** overwrite.
- El motor y el análisis leen **siempre** de DuckDB/Parquet construidos desde el
  snapshot, jamás de una API en vivo.
- `make build-from-frozen-dataset` reconstruye las anclas desde el snapshot y
  **nunca** contacta una fuente externa.
- `verify.py` comprueba que el `raw_file_hash` de cada fuente coincide con
  `dataset_manifest.json`; **falla** si un archivo del snapshot falta o su hash no
  cuadra, porque los datos externos no pueden regenerarse de forma reproducible.

**Dónde viven los snapshots (por peso y licencia):**

| Categoría | Ejemplo | Dónde | Nota |
|---|---|---|---|
| Panel país-año ligero | WDI, PIP, OECD, GRD, ILOSTAT, IMF WEO, AIPI, ITU, PWT, ASPIRE, WPP | Zenodo + DVC | Chico; se archiva completo. |
| Derivados de microdatos | vector `poverty_gap` / costo GMI por país-año | Zenodo (solo el derivado) | El microdato crudo NO se redistribuye; se archiva el agregado + el script + instrucciones de descarga registrada. |
| Microdatos crudos restringidos | ENAHO, CASEN, GEIH/ENCV, ENIGH | NO se archivan | Licencia de redistribución restringida. Se documenta la descarga registrada y se archiva solo el hash del archivo obtenido. |

- **DVC (o `git-annex`)** apunta los raw a un remoto durante el ciclo de trabajo;
  **Zenodo versionado** es el archivo final citado por el DOI. No se mezclan: DVC es
  el "durante", Zenodo el "congelado".
- **Chequeo legal antes de archivar cualquier microdato.** La licencia de cada
  fuente nacional se registra en `dim_source.license_notes` *antes* de decidir qué
  se sube. Este es el único punto del plan con riesgo legal real.

El README y `METHODS.md` deben decir con claridad que los resultados dependen de un
`dataset_version` específico y que "actualizar" significa correr un pull nuevo,
generar `dataset_version` nuevo y re-correr el motor con ese identificador
explícito. El paper cita la versión con la que corrió.

---

## Fases de release

El trabajo de reproducibilidad se parte en dos fases para que no se vuelva un
bloqueador abierto antes de submission.

### Fase A — MVP submission-ready

Objetivo: que un revisor pueda verificar las afirmaciones numéricas del manuscrito.

Alcance requerido:

- Esqueleto de repo limpio.
- Dockerfile simple y funcional (multi-stage no requerido aún).
- Motor `src/ai_usp/` implementado (shock IA, adopción, canales fiscales, costo de
  política, espacio fiscal, umbrales, captura histórica).
- Capa `build-from-frozen-dataset` funcional sobre un snapshot mínimo (MVP
  ejecutable del plan `01` §23.2: MVP de ingesta + `debt_guardrail_anchor`,
  `labor_share_anchor`, `digital_gap_anchor`, `ai_exposure_anchor`).
- `run_all.py` genera los outputs relevantes: **Tier A completo (Fases 2-5: baseline, scenario-regime grid, threshold inversion y plausibilidad histórica)**.
- `verify.py` compara outputs generados contra referencia **y** valida el hash del
  snapshot de input.
- `test_determinism.py` y `test_regression.py` pasan.
- `README.md` explica `make reproduce-deterministic`, `make reproduce-full` y
  `make verify`.
- `METHODS.md` mínimo: modo channel-based frozen-weight, convención endpoint
  congelado (H=10, 2024→2034), construcción de pesos `omega`, calibración de
  `S_frontier`, política de snapshot, seed policy y comandos de reproducción.
- Borradores de `CITATION.cff` y `.zenodo.json`; el DOI final no se requiere antes
  de submission.
- Statement de disponibilidad de código/datos con placeholder de DOI Zenodo.

No requerido en Fase A: multi-stage Dockerfile, digest pinning, GitHub Actions,
pre-commit, `CONTRIBUTING.md`, `METHODS.md` completo, release Zenodo, suite
completa, Tier B (Monte Carlo completo con convergencia) y Tier D (diagnósticos
completos). Estos pueden diferirse a Fase B si el claim central del submission lo
cargan el Tier A + plausibilidad histórica.

### Fase B — Release archival

Objetivo: que un investigador independiente reproduzca, audite, reimplemente y
extienda el trabajo años después.

Alcance requerido: multi-stage Dockerfile pineado por digest; suite completa; CI
en Docker; `METHODS.md` completo; `CONTRIBUTING.md`; pre-commit; check advisory de
vulnerabilidades; release final en GitHub; release archival en Zenodo con DOI
versión-específico; mapeo paper-to-code final; Tier B completo (MC independiente +
rank-correlated + `mc_convergence_report`) y Tier D completo (placebo ICT,
negative controls, leave-one-source-out, channel ablation).

Fase A es el paquete mínimo viable. Fase B es el artefacto de investigación
archival.

---

## Layout del repositorio

```text
ai-usp-fiscal-thresholds/
  README.md
  METHODS.md
  CONTRIBUTING.md
  LICENSE
  LICENSE-DATA
  CITATION.cff
  .zenodo.json
  PRIMARY_SPEC_HASH.txt
  01_database_construction_plan_AI_USP_threshold_framework_v6.md
  02_ESD_AI_USP_v6.md
  REPRODUCIBILITY_PLAN.md
  Dockerfile
  .dockerignore
  .pre-commit-config.yaml
  .devcontainer/
    devcontainer.json
  Makefile
  pyproject.toml
  requirements-lock.txt
  dvc.yaml
  .github/
    workflows/
      reproduce.yml
  src/
    ai_usp/
      __init__.py
      shock.py            # phi_raw -> phi_Y_nom (bridges kappa, pi_AI_Y)
      translation.py      # S_NDC, S_frontier, T, g_AI_level acumulado
      adoption.py         # logistic anchored adoption; q_use, q_prod, q_bar
      labor_share.py      # LS', Delta_W, Delta_NLS, chi_Kbase
      fiscal_channels.py  # omega_L/K/C, lambda_AI, tau_eff, MFC_gross (channel-based)
      policy_cost.py      # c_gross/c_net por PEN/MUT/GMI/PBI/UBI; endpoint scaling
      fiscal_space.py     # fs_eff, MFC_tilde, F_fix
      thresholds.py       # V_gross, buffers xi, debt guardrail, threshold inversion
      historical.py       # MFC_hist_gross, percentiles, mezcla incondicional
      montecarlo.py       # draws PERT/beta, dependencia, probabilidades de cruce
      diagnostics.py      # placebo ICT, negative controls, LOSO, ablation
      audit.py            # double_counting_audit, hard/soft/robustness gates
      classify.py         # cell_result_class, country_policy_result_class
      plotting.py
  scripts/
    01_download_wdi.py ... 14_download_wpp.py   # capa de ingesta (Tier C)
    build_snapshot.py                            # congela raw + hashes -> dataset_version
    generate_all_figures.py
  experiments/
    phase2_deterministic_baseline.py
    phase3_scenario_regime_grid.py
    phase4_threshold_inversion.py
    phase5_historical_plausibility.py
    phase6_monte_carlo.py
    phase7_diagnostics.py
    phase8_final_classification.py
  reproducibility/
    run_all.py
    verify.py
    config/
      tierA_deterministic.yaml      # Fases 2-5
      tierB_monte_carlo.yaml        # Fase 6 + Experimento 8
      tierC_snapshot.yaml           # dataset_version, hashes
      tierD_diagnostics.yaml        # Fase 7 (Experimento 8 pertenece a Tier B)
      run_modes.yaml                # fiscal_conversion_mode, adoption_mode, etc.
      rng_policy.yaml
      schemas.yaml
      tolerances.yaml
    reference/
      reference_manifest.json
      <outputs canónicos de resultado>
      checksums.sha256
    snapshot/
      dataset_manifest.json         # raw_file_hash por fuente + dataset_version
  tests/
    fixtures/
      mini_snapshot/                # snapshot chico de 1-2 celdas para CI
      regression_baseline.csv
    test_cost_monotonicity.py
    test_zero_mfc.py
    test_zero_phi.py
    test_zero_qprod.py
    test_fixed_cost_monotonicity.py
    test_bilinear_corner.py
    test_historical_class.py
    test_debt_guardrail.py
    test_stress_only.py
    test_phi_raw_blocked.py
    test_mfc_mode_exclusion.py
    test_erosion_companion.py
    test_static_labeling.py
    test_gmi_labeling.py
    test_gap_aipi_overlap.py
    test_endpoint_scaling.py
    test_frozen_weight_inversion.py
    test_determinism.py
    test_regression.py
    test_figures.py
    test_verify.py
  data/
    raw/                            # snapshot inmutable (DVC-tracked)
    interim/
    processed/
    model_inputs/
  db/
    ai_usp_threshold.duckdb         (generado por build-from-frozen-dataset; en .gitignore, nunca commiteado)
  results/
    .partial/
  figures/
  paper/
    main.tex
    references.bib
```

`paper/` no debe incluir `.aux`, `.log`, `.out`, `.synctex.gz` ni artefactos de
editor. `LICENSE` cubre código; `LICENSE-DATA` (CC-BY-4.0) cubre datos archivados
y figuras. `PRIMARY_SPEC_HASH.txt` registra el SHA-256 y timestamp de la
especificación primaria congelada (plan `02` §2 y §10), para que el estado
confirmatorio de H1–H5 sea auditable.

---

## Política de Docker

Imagen basada en un patch de Python pineado. En desarrollo:

```dockerfile
FROM python:3.12.X-slim
```

Para el release Zenodo, pinear por digest:

```dockerfile
FROM python:3.12.X-slim@sha256:<digest>
```

No usar un tag flotante (`python:3.12-slim`) para el release archival.

El Dockerfile fija defaults numéricos deterministas:

```dockerfile
ENV PYTHONHASHSEED=0
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
```

Estos pins importan para las **reducciones del Monte Carlo** (sumas sobre draws) y
para el orden de operaciones en `pandas`/`numpy`. A diferencia de un paquete con
eigendescomposiciones intensivas, el motor AI-USP es aritmética + muestreo +
percentiles, así que el determinismo bit-a-bit del Tier A es *más fácil* de lograr;
aun así se pinean los threads para que las tolerancias estrictas sean defendibles.

`.dockerignore` debe excluir historia Git, `data/raw/` (va por DVC/Zenodo, no en el
build context), resultados, figuras y artefactos LaTeX:

```text
.git
data/
results/
figures/
paper/
*.pdf
__pycache__/
*.pyc
.mypy_cache/
.pytest_cache/
```

Incluir `.devcontainer/devcontainer.json` para reproducir el entorno en VS Code.

---

## Interfaz Makefile

```makefile
reproduce: run verify

build-from-frozen-dataset:
	python scripts/build_snapshot.py --from-frozen --dataset-version $(DATASET_VERSION)

run:
	python reproducibility/run_all.py

verify:
	python reproducibility/verify.py --reference reproducibility/reference/ \
		--snapshot reproducibility/snapshot/

figures:
	python scripts/generate_all_figures.py

test:
	pytest tests/ -v

check: test verify

reproduce-deterministic:            # Tier A: Fases 2-5, exacto
	python reproducibility/run_all.py --tier A
	python reproducibility/verify.py --reference reproducibility/reference/ --tier A

reproduce-full:                     # Tier A + B (MC), consume snapshot congelado
	python reproducibility/run_all.py --tier all
	python reproducibility/verify.py --reference reproducibility/reference/

run-diagnostics:                    # Tier D: placebo ICT, negative controls, LOSO, ablation
	python reproducibility/run_all.py --tier D
	python reproducibility/verify.py --reference reproducibility/reference/ --tier D

check-env:
	python reproducibility/run_all.py --check-env-only

determinism-check:
	python reproducibility/run_all.py --tier A --output results/determinism-run-1
	python reproducibility/run_all.py --tier A --output results/determinism-run-2
	python reproducibility/verify.py \
		--reference results/determinism-run-1 \
		--generated results/determinism-run-2 \
		--exact-numeric
```

Comando Docker canónico para el README y el Makefile:

```bash
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/results:/app/results -v $(pwd)/figures:/app/figures ai-usp:latest make reproduce-deterministic
```

`data/` va SIEMPRE por volumen (el `.dockerignore` la excluye del build context a propósito).

`reproduce-deterministic` recomputa solo el núcleo determinista (baseline +
threshold inversion), el grid y la plausibilidad histórica, sin muestreo. Es el comando que corre un revisor escéptico
para comprobar que `V_gross`, `g_AI_required`, `MFC_required` y `T_required`
coinciden con las fórmulas cerradas del plan `02` §7.7.

`reproduce-full` recomputa Tier A + Tier B; **nunca** re-descarga datos (consume el
snapshot congelado). El Tier C no se "recomputa": se verifica por hash.

---

## Contratos de comando

El README debe declarar exactamente qué prueba cada comando.

**`make reproduce-deterministic` (Tier A):**
- Recomputa el baseline determinístico, el scenario-regime grid, las inversiones de umbral y la plausibilidad histórica con `parameter_set` central, sin muestreo.
- Un pass significa que `V_gross`, los objetos de nivel acumulado `g_AI_level`, y las
  inversiones cerradas reproducen dentro de tolerancia de máquina.
- No prueba el Monte Carlo ni los diagnósticos.
- Produce la clasificación preliminar sin MC; la clasificación final y la adjudicación completa requieren `reproduce-full`.

**`make reproduce-full` (Tier A + B):**
- Recomputa todos los outputs numéricos del cuerpo del paper, incluido el Monte Carlo.
- No usa outputs archivados salvo como targets de verificación.
- **No** re-ejecuta el pull de datos (Tier C): consume el snapshot.
- Reporta runtime y RAM medidos en la plataforma Docker soportada.

**`make run-diagnostics` (Tier D):**
- Corre placebo ICT (pipeline completo con inputs era-consistentes 2010–2018),
  negative controls, leave-one-source-out y channel ablation.
- Un pass es **cualitativo**: los diagnósticos producen el veredicto esperado
  (p.ej. el placebo ICT **no** genera factibilidad amplia), no una coincidencia
  numérica `atol/rtol`.

**`make build-from-frozen-dataset` (Tier C):**
- El target ejecuta las Fases 1-5 del plan 01 (armonización de raw a interim, construcción de anchors, gates de validación de la Fase 4 — `data_quality_report` y hard gates —, y export de `model_inputs`) leyendo EXCLUSIVAMENTE del snapshot congelado. El freezing (pull + hash + `dataset_version`) es la operación inversa y separada: `build_snapshot.py --freeze`. Un pass del target incluye que los gates de validación del plan 01 pasen, no solo que los hashes cuadren.

**`make verify`:**
- Valida esquema + comparación numérica de outputs (por tier) **y** la integridad
  del snapshot de input (hash).
- Semántica hard-fail para outputs canónicos salvo campos marcados warning-only.
- Aplica tolerancias relajadas y documentadas a los campos del Tier B.

---

## Fallback sin Docker

El path oficial es Docker en `linux/amd64`. Un path no-Docker puede documentarse
para HPC/Podman/Singularity/máquinas institucionales, pero no es el path soportado:

```bash
pip install -e .
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
make reproduce-deterministic
```

Fuera de Docker, las tolerancias estrictas pueden no sostenerse. Proveer
`tolerances-relaxed.yaml` o `verify.py --relaxed` como diagnóstico, no como estándar
archival.

---

## Pre-flight checks

Antes de cualquier cómputo caro, `run_all.py` ejecuta pre-flight (también vía
`make check-env`):

- Versiones de Python/NumPy/SciPy/pandas/DuckDB coinciden con el lockfile.
- `PYTHONHASHSEED=0`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
  `OPENBLAS_NUM_THREADS=1`.
- Arquitectura `x86_64` (warn en `aarch64`).
- Directorio de output escribible; sin outputs parciales huérfanos salvo modo
  resume.
- **Tier C:** el `dataset_manifest.json` existe y **todos** los `raw_file_hash`
  coinciden con el snapshot; **falla** si un archivo del snapshot falta o el hash no
  cuadra (los datos externos no se regeneran).
- El hash de `PRIMARY_SPEC_HASH.txt` coincide con el registrado en la referencia;
  **warn** en mismatch (señal de estado confirmatorio: la spec cambió tras el
  pre-registro).
- **Tier B:** el seed del Monte Carlo está fijado en `rng_policy.yaml`.
- **Tier D:** existen los inputs era-consistentes del placebo ICT.

Los fallos críticos abortan antes de empezar el cómputo numérico.

---

## Política de ejecución larga

Cualquier cómputo que supere ~30 min soporta checkpointing y recovery.

- `run_all.py` escribe resultados parciales bloque a bloque bajo `results/.partial/`.
- Un bloque se considera completo solo tras escribir su data **y** su checksum
  SHA-256.
- Al arrancar, `run_all.py` detecta bloques completos y resume desde el primero
  faltante o corrupto.
- Bloques corruptos se ignoran y recomputan.
- `run_all.py --restart` borra parciales y arranca de cero.
- `manifest.json` registra si la corrida fue limpia o resumida, cuántos bloques se
  recuperaron y cuántos se recomputaron.

**Granularidad natural de bloque:** una celda del grid
`país × política × escenario × régimen` (400 celdas base), y dentro del Tier B, un
sub-bloque por `mc_mode`. Esto hace `reproduce-full` robusto a interrupciones,
cortes de energía y timeouts de CI.

Manejo de error: default fail-fast. Si un experimento lanza excepción, produce
`NaN`/`Inf` o falla validación de esquema, `run_all.py` aborta. Un flag
`--continue-on-error` puede continuar experimentos independientes, pero el manifest
marca los outputs fallidos como `incomplete`, y `verify.py` falla si un output
requerido está `incomplete`.

---

## Presupuesto de cómputo y regla de vectorización

El motor es aritmética contable, no cómputo pesado. El objeto más grande del
proyecto (Monte Carlo paper-ready: 400 celdas × 50,000 draws × 3 modos = 60M
evaluaciones de ~100-200 flops) cabe en minutos de una laptop. Tiempos esperados
(un core, `OMP_NUM_THREADS=1`, implementación vectorizada):

| Cómputo | Tiempo esperado |
|---|---|
| Tier A completo (Fases 2-5, 400 celdas + inversiones cerradas) | segundos |
| MC MVP (5,000 draws × 400 celdas, modo independiente) | ~10-30 s |
| MC paper-ready (50,000 × 400 × 3 modos, con escalera de convergencia) | ~5-15 min |
| Bootstrap de percentiles históricos (B=2,000, ~24 obs/país) | segundos |
| Sobol/Saltelli del Experimento 8 (`N×(2D+2)` evaluaciones) | minutos |
| `reproduce-full` end-to-end (con audits, I/O y figuras) | ~15-40 min |

**REGLA DE VECTORIZACIÓN (obligatoria en `montecarlo.py` y en todo camino que
evalúe el modelo muchas veces): los draws se vectorizan, las celdas se iteran.**
Cada primitivo sorteado es un array numpy de longitud `M`; toda la cadena
`phi -> adopción -> T -> g -> pesos -> MFC -> fs_eff -> V` opera sobre arrays
completos; el ÚNICO loop de Python es sobre las 400 celdas. Prohibido: loop de
Python por draw, `pandas.apply` fila a fila, o funciones escalares llamadas 60M
veces — esa implementación es 100-1000× más lenta y es la única forma de que este
proyecto tarde "horas o días". **Síntoma de diagnóstico: si una celda con M=50,000
tarda más de ~1 segundo, hay un loop por draw; detenerse y vectorizar antes de
continuar.** La misma regla aplica al muestreo Saltelli del Experimento 8.

Otros puntos potencialmente largos (todos one-time o acotados, ninguno del path de
reproducción del motor):

- **Microdatos GMI (el candidato real a "lento"):** leer `.sav`/`.dta` de
  ENAHO/CASEN/GEIH/ENIGH con `pyreadstat` toma minutos por archivo. Regla:
  convertir a Parquet en la PRIMERA lectura y releer siempre el Parquet (10-100×
  más rápido); la deduplicación por hogar y la agregación ponderada se hacen
  vectorizadas. Costo one-time de construcción, no entra a `reproduce-full`.
- **Descargas Tier C:** limitadas por red y rate limits de APIs (SDMX/PIP pueden
  tardar), no por CPU; se corren UNA vez y quedan congeladas en el snapshot.
  Mitigación operativa en los scripts de ingesta: reintentos con backoff
  exponencial, preferir endpoints bulk cuando existan (ILOSTAT bulk facility, WDI
  bulk) sobre consultas indicador-por-indicador, y escribir cada fuente apenas
  descarga (una fuente caída no invalida las demás; el snapshot se completa por
  partes y se congela al final).
- **Placebo ICT (Tier D):** duplica el pipeline completo con inputs 2010-2018;
  sigue siendo minutos bajo la regla de vectorización.

El presupuesto NO justifica paralelismo: `OMP_NUM_THREADS=1` se mantiene. Si
alguna extensión futura lo exigiera, se paraleliza por celdas con sub-seeds
derivados (`numpy.random.SeedSequence.spawn`), nunca compartiendo un `Generator`
entre workers — el determinismo por celda es parte del contrato de verificación.

---

## Contrato de modos por corrida

A diferencia de un paquete de simulación pura, una corrida AI-USP **no es
reproducible si no declara sus modos**. `run_manifest` (plan `02` §19.1) debe fijar,
y `verify.py` debe comprobar contra `run_modes.yaml`:

| Campo | Valores | Regla |
|---|---|---|
| `fiscal_conversion_mode` | `channel_based` / `historical_reduced_form` | Baseline: `channel_based` frozen-weight. Nunca se mezclan en una celda. |
| `adoption_mode` | `anchored_simulated` / `observed` / `structural_intercept` | Baseline: `anchored_simulated`. |
| `trajectory_convention` | `frozen_anchor_2024` / `trajectory_sensitivity` | Baseline: `frozen_anchor_2024` (hace `g=(1+phiT)^H-1` exacta). |
| `static_or_accumulated` | `accumulated_endpoint` / `one_period_static` | Baseline: `accumulated_endpoint` (H=10). |
| `cost_convention` | `gross` / `net` | Baseline: `gross`. |
| `gmi_version` | `GMI_ideal_aggregate` / `GMI_loaded_aggregate` / `GMI_ideal_microdata` / `GMI_loaded_microdata` | Declarado explícito. |
| `mc_mode` | `independent` / `rank_correlated` / `block_correlated_stress` | Solo Tier B. |
| `dataset_version` | id del snapshot congelado | Debe coincidir con el hash de `dataset_manifest.json`. |

Dos corridas con el mismo código pero distintos modos son corridas distintas. El
`run_manifest` es el objeto que las distingue.

---

## Política de verificación

`run_all.py` escribe un manifest de provenance al final de cada ejecución:

```text
results/manifest.json
```

Contenido mínimo:

```json
{
  "run_id": "...",
  "git_commit_sha": "abc123...",
  "git_dirty": false,
  "primary_spec_hash": "sha256:...",
  "dataset_version": "v1.0.0",
  "dataset_manifest_hash": "sha256:...",
  "parameter_set_id": "baseline",
  "tier": "A",
  "run_modes": { "fiscal_conversion_mode": "channel_based", "...": "..." },
  "random_seed": 20240101,
  "python_version": "3.12.x",
  "platform": "Linux-6.1.0-x86_64",
  "timestamp_utc": "2026-07-06T14:32:00Z",
  "dependencies": { "numpy": "1.26.4", "scipy": "1.12.0", "pandas": "2.x", "duckdb": "0.x" },
  "runtime_seconds": 512.3,
  "execution_mode": "clean",
  "outputs": { "fiscal_space_result.csv": "sha256:...", "threshold_inversion_result.csv": "sha256:..." }
}
```

`verify.py` debe:

1. Cargar outputs generados y de referencia.
2. **Validar la integridad del snapshot de input**: `dataset_manifest_hash` del run
   coincide con el snapshot; cada `raw_file_hash` cuadra. (Novedad frente a un
   paquete de simulación: se verifica el *input*, no solo el output.)
3. Validar estructura contra `schemas.yaml`.
4. Fallar claro en filas faltantes, columnas extra/faltantes, tipos inesperados,
   `NaN`/`Inf`.
5. Emparejar filas por llaves explícitas
   (`country_id, policy_id, scenario_id, regime_id, endpoint_year`).
6. Comparar cada columna numérica con la tolerancia del **tier** del output.
7. Reportar pass/fail por archivo, grupo de filas y columna.
8. Validar la tabla de adjudicación (H1–H5) y la clasificación país-política contra
   el pre-registro.
9. Salir con status distinto de cero en fallo numérico o de esquema.

Presupuesto de fallo: los outputs canónicos usan hard-fail. La verificación pasa si
y solo si cada campo requerido está dentro de tolerancia y cada check de esquema
pasa. No hay soft-pass para violaciones "pequeñas". Los campos warning-only se marcan
explícitamente en `schemas.yaml`.

---

## Adjudicación (híbrido)

Como el plan `02` pre-registra hipótesis, el paquete trata **dos** objetos como
canónicos y validados por esquema, con semántica distinta.

**(a) Adjudicación de hipótesis H1–H5** — verdict cualitativo. Estas son
afirmaciones testeables sobre patrones, no predicciones puntuales, así que el
verdict es `HOLDS / VIOLATED / MIXED`, no un número:

```yaml
hypothesis_adjudication.csv:
  tier: A+B
  row_matching_key: [hypothesis_id]
  columns:
    hypothesis_id:
      type: string
      allowed: [H1, H2, H3, H4, H5]
    statement:
      type: string
    evidence_summary:
      type: string
    verdict:
      type: string
      allowed: [HOLDS, VIOLATED, MIXED, NOT_TESTABLE]
```

`NOT_TESTABLE` aplica cuando el diseño no identifica la hipótesis en el margen relevante (p.ej. H2 entre países si `E_prod` usa el fallback regional común — matiz de la sección 5 del plan `02`).

`verify.py` falla si una hipótesis del pre-registro falta en la tabla, y **warn** si
un verdict cambia entre la referencia y una corrida regenerada (señal fuerte de que
código o datos derivaron del estado pre-registrado).

**(b) Clasificación país-política** — escala gradada, **no** un verdict binario.
Preserva el mensaje central del paper (frontera, no pronóstico). Usa la escala del
plan `02` §18.2 con su precedencia determinística:

```yaml
country_policy_classification.csv:
  tier: A+B
  row_matching_key: [country_id, policy_id]
  columns:
    country_id: { type: string, allowed: [PER, CHL, COL, MEX] }
    policy_id:  { type: string, allowed: [PEN, MUT, GMI, PBI, UBI] }
    class:
      type: string
      allowed: [robustly_feasible, conditionally_feasible, fragile_feasible, not_feasible, stress_benchmark_only]
```

Equivalencia de nombres (anti-drift): `country_policy_classification.csv` es la exportación CSV del output canónico `final_country_policy_classification` de la Fase 8 del plan `02` — mismo objeto, mismo esquema; la variante `_preliminary` corresponde a la versión sin Monte Carlo del Paquete A. No existen dos objetos distintos.

La regla `robustly_feasible` exige `prob_v_ge_1_10 >= 0.75` (objeto Tier B): la clasificación FINAL solo se produce y verifica en `reproduce-full`. En Fase A / `reproduce-deterministic` se produce y verifica la CLASIFICACIÓN PRELIMINAR sin Monte Carlo (Paquete A del plan `02`, sección 26), archivada como `country_policy_classification_preliminary.csv` (tier: A) con la pata probabilística marcada `not_evaluated`.

Regla: forzar un verdict binario sobre el resultado país-política traicionaría el
paper. La gradación es el output principal; el verdict H1–H5 es el gancho de
auditoría.

---

## Tolerance tiers

`verify.py` selecciona el tier por el campo `tier` del output. **No todos los tiers
admiten el mismo régimen de tolerancia.**

- **Tier A (determinista):** tolerancia estricta. `V_gross`, `g_AI_level`, y las
  inversiones cerradas son deterministas dados `parameter_set`, versión de NumPy y
  threads. `atol` a nivel de máquina para objetos de forma cerrada; tolerancia
  estricta calibrada para lo que involucre acumulación numérica.
- **Tier B (Monte Carlo):** tolerancia relajada y **documentada**. Las
  probabilidades `prob_v_ge_1*` y percentiles dependen del muestreo. Calibrar desde
  al menos tres corridas semilladas en contenedor y registrar como tolerancia Tier
  B. Se verifica la *forma* (¿la probabilidad cae en la banda esperada?), no un valor
  exacto. La estabilidad se controla con `mc_convergence_report` (criterio
  `|pi_M_k - pi_M_{k-1}| <= 0.01–0.02`).
- **Tier C (snapshot):** **no hay tolerancia numérica**. El check es hash exacto del
  `raw_file_hash`. O coincide el snapshot o no es la misma corrida.
- **Tier D (diagnósticos):** verdict cualitativo `pass/fail` + `rank_change`. No se
  compara con `atol/rtol`; se comprueba que el diagnóstico produce el resultado
  esperado (p.ej. `placebo_ICT_feasibility == FALSE` para celdas amplias).

Las columnas `*_ci_low/high` del bootstrap de percentiles históricos son estocásticas-con-semilla: bajo el seed fijo de `rng_policy.yaml` verifican EXACTAS (tier A con seed); solo con seed distinto aplicaría banda relajada.

Ejemplo ilustrativo:

```yaml
fiscal_space_result:
  tier: A
  row_matching_key: [country_id, policy_id, scenario_id, regime_id, xi, endpoint_year]
  columns:
    v_gross:      { atol: 1.0e-10, rtol: 1.0e-8 }   # ratio determinista
    g_ai_level:   { atol: 1.0e-12, rtol: 0.0 }      # forma cerrada acumulada
    fs_eff:       { atol: 1.0e-10, rtol: 1.0e-8 }

threshold_inversion_result:
  tier: A
  row_matching_key: [country_id, policy_id, scenario_id, regime_id, requirement_basis, xi, endpoint_year]
  columns:
    g_ai_required:     { atol: 1.0e-10, rtol: 1.0e-8 }
    mfc_required_gross:{ atol: 1.0e-10, rtol: 1.0e-8 }
    t_required_H:      { atol: 1.0e-10, rtol: 1.0e-8 }

monte_carlo_result:
  tier: B
  row_matching_key: [country_id, policy_id, scenario_id, regime_id, prob_basis, mc_mode, endpoint_year]
  columns:
    prob_v_ge_1_10:    { atol: 0.0, rtol: 2.0e-2 }  # relajado; calibrado con 3 seeds
    v_p50:             { atol: 0.0, rtol: 1.0e-2 }
```

Política de registro de tolerancias: calibrar sobre el subset determinista (no el
grid completo); usar al menos tres corridas en contenedor para las estrictas; fijar
la tolerancia final en `max(diferencia_observada) * factor`, con factor default 10;
si la diferencia observada es exactamente cero, usar tolerancia de máquina y
documentarlo. No relajar tolerancias para que el grid completo pase: investigar la
causa. Documentar en `METHODS.md` número de corridas, diferencia máxima observada y
factor por tier.

No prometer reproducibilidad bit-a-bit de todo artefacto. Los outputs numéricos del
Tier A se verifican estricto dentro de Docker; los del Tier B en el tier relajado.
Figuras/PDF se verifican regenerándolas sin error y chequeando los datos numéricos
subyacentes (los PDF de matplotlib traen metadata/fuentes/timestamps que hacen
frágiles los checksums estrictos).

---

## Política de actualización de datos de referencia y snapshot

**Outputs de referencia** cambian solo cuando cambia el código/config que los
genera:

- No actualizar por formato, logging, docs o cambios de harness.
- Cada update requiere mensaje de commit explicando por qué cambiaron los valores.
- Si cambia la referencia pero no los valores del paper, documentar que el cambio
  está bajo la precisión de reporte.
- Si cambian los valores del paper, crear un tag de versión nuevo.

**Snapshot de datos (Tier C):** un re-pull **nunca** "actualiza" un snapshot; genera
un `dataset_version` nuevo. El snapshot viejo permanece archivado. El paper cita el
`dataset_version` con el que corrió.

---

## Política de logging

`run_all.py` usa `logging`, no `print()`. Escribe logs line-oriented a
`results/run.log` con formato `ISO_TIMESTAMP | LEVEL | MODULE | MESSAGE`. Loguea:
inicio/fin/duración/hash de cada bloque del grid; pre-flight checks (pass/warn/fail);
si la ejecución es limpia/resumida/restart; el tier y los modos de corrida; y para
Tier C, el `dataset_version` y los hashes consumidos. Registra el path del log en
`manifest.json`.

---

## Política de datos (para el README)

```markdown
## Data policy

Este repositorio distingue cuatro categorías.

### Archivado en el depósito Zenodo
- outputs canónicos de resultado (fiscal_space_result, threshold_inversion_result,
  monte_carlo_result, diagnostic_result)
- tabla de adjudicación de hipótesis H1–H5 y clasificación país-política
- country_policy_classification_preliminary (target de verificación de Fase A)
- figures/*.pdf
- snapshot ligero de datos país-año (WDI/PIP/OECD/GRD/ILOSTAT/IMF/AIPI/ITU/PWT/ASPIRE/WPP)
- derivados agregados de microdatos (poverty_gap / costo GMI por país-año)

### Recomputable (Tier A y Tier B)
- Baseline determinístico e inversiones de umbral -> make reproduce-deterministic
- Monte Carlo -> make reproduce-full (runtime/RAM: TBD)

### Reconstruible desde snapshot (Tier C)
- Anclas procesadas -> make build-from-frozen-dataset (nunca re-descarga)

### Recomputable solo con acceso registrado (microdatos restringidos)
- Costo GMI paper-ready desde ENAHO/CASEN/GEIH-ENCV/ENIGH: el microdato crudo NO se
  redistribuye; se archiva el derivado + script + instrucciones de descarga y el
  hash del archivo obtenido.

Código bajo MIT; datos archivados, derivados y figuras bajo CC-BY-4.0. Los
microdatos crudos se rigen por la licencia de su fuente nacional.
```

---

## Tests

La suite incluye LOS 15 tests canónicos del plan `02` §20 más los tests de harness propios de este plan (determinism, regression, endpoint_scaling, frozen_weight_inversion, figures, verify).

- `test_cost_monotonicity`: si `c_gross` sube y todo lo demás queda fijo, `V_gross`
  baja.
- `test_zero_mfc`: si `MFC_tilde_gross <= 0` con costos positivos, `V_gross < 1` o no
  computable (caso peligroso: `MFC_gross > 0` con `MFC_tilde <= 0` por deducciones ME).
- `test_zero_phi`: `phi_Y_nom = 0` => `g_AI_level = 0`.
- `test_zero_qprod`: `q_prod = 0` => `T = 0`.
- `test_fixed_cost_monotonicity`: si `ac_fix`, `tr_ann` o `leak_fix` suben, `fs_eff`
  baja.
- `test_bilinear_corner`: `MFC_tilde < 0` y `g_AI_level < 0` => falla económica,
  nunca cruce.
- `test_historical_class`: `MFC_required > P90` => la celda no puede ser
  `fiscally_ordinary`.
- `test_debt_guardrail`: cruza `V>=1` pero falla deuda => no `robustly_feasible`.
- `test_stress_only`: cruza solo en `stress+r4` => no `robustly_feasible`.
- `test_phi_raw_blocked`: usar `phi_raw` directo activa `hard_fail`.
- `test_mfc_mode_exclusion`: no se puede sumar MFC histórico con channel-based.
- `test_erosion_companion`: un resultado titular con r>=1 sin corrida companion de erosión conductual (7.4.2) bloquea la exportación.
- `test_static_labeling`: ninguna corrida estática puede tener `static_or_accumulated = accumulated_endpoint`.
- `test_gmi_labeling`: GMI agregado no puede etiquetarse como microdata.
- `test_gap_aipi_overlap`: Gap solapado no residualizado no entra al baseline.
- `test_endpoint_scaling`: comparar `g` acumulado a 2034 contra costos 2024 sin el
  ajuste demográfico activa `hard_fail`.
- `test_frozen_weight_inversion`: las fórmulas cerradas de inversión coinciden con la
  raíz numérica del canal bajo frozen weights.
- `test_determinism`: el mismo seed produce outputs Tier A idénticos.
- `test_regression`: un grid chico coincide con un CSV de referencia commiteado.
- `test_figures`: cada script de figura corre sin error.
- `test_verify`: el verificador pasa en referencia limpia y falla en outputs
  perturbados.

`test_verify` debe incluir al menos: `test_verify_clean_passes`,
`test_verify_perturbed_fails`, `test_verify_missing_rows_fails`,
`test_verify_extra_columns_fails`, `test_verify_nan_values_fails`,
`test_verify_type_mismatch_fails`, `test_verify_missing_manifest_warns`,
`test_verify_missing_hypothesis_in_adjudication_fails`,
`test_verify_tierB_uses_relaxed_tolerance`, y —novedad— **`test_verify_dataset_hash_mismatch_fails`**
(un snapshot con hash distinto al declarado debe fallar).

Los dos tests más importantes son `test_determinism` y `test_regression`.
`test_verify` guarda contra un verificador falso-positivo. `test_bilinear_corner` y
`test_mfc_mode_exclusion` demuestran que el aparato se ejercita, no que es decorativo.

---

## Política de aleatoriedad

Toda aleatoriedad (draws PERT/beta, bootstrap de percentiles, dependencia
rank-correlated) usa:

```python
numpy.random.Generator(numpy.random.PCG64(seed))
```

No usar la API global legacy `np.random.seed()` en el path de reproducción. Cada
experimento define su seed en `rng_policy.yaml`; los seeds son constantes arbitrarias,
no parámetros afinados. Para el bootstrap de percentiles históricos y para la
dependencia del Monte Carlo, el seed o rango de seeds se escribe en el config.

---

## Integración continua

GitHub Actions corre el path rápido dentro de Docker, **usando el mini-snapshot de
fixtures** (`tests/fixtures/mini_snapshot/`), nunca un pull real:

```yaml
name: Reproducibility Check
on: [push, pull_request]
jobs:
  reproduce:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with: { context: ., load: true, tags: ai-usp:test }
      - run: >
          docker run --rm
          -v ${{ github.workspace }}/ci-results:/app/results
          ai-usp:test
          bash -c "make reproduce-deterministic && make test"
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: ci-results, path: ci-results/ }
      - run: docker run --rm ai-usp:test pip-audit -r requirements-lock.txt || true
        continue-on-error: true
```

CI chequea: instalación del paquete, unit tests, mini regresión determinista,
reproducción rápida del Tier A sobre el mini-snapshot, y verificación numérica contra
referencia. El grid completo y el Monte Carlo pesado no corren en CI. CI apunta a
`linux/amd64`. El `pip-audit` es advisory.

---

## Cuando la verificación falla (triage)

```text
Fallo de verificación
+-- hash de snapshot no coincide (Tier C)
|   +-- El dataset_version no es el declarado. Revisar dataset_manifest.json. NO re-descargar para "arreglar".
+-- atol/rtol excedido por < 10x
|   +-- Output Tier B (Monte Carlo)? -> Esperable; revisar seed y mc_mode. Usar tier B relajado.
|   +-- Arquitectura distinta (arm64 vs amd64)? -> Posible; documentar en METHODS.md.
|   +-- Mismo entorno? -> Comparar versiones NumPy/SciPy/pandas contra manifest.json.
+-- atol/rtol excedido por > 10x
|   +-- NaN/Inf presente? -> Probable bug; revisar test_zero_mfc / test_bilinear_corner.
|   +-- Finito pero incorrecto? -> Comparar seeds y rng_policy.yaml.
+-- V_gross o inversión Tier A no coincide
|   +-- Discrepancia real teoría/código. Parar y reconciliar con el plan 02 §7 antes de seguir.
+-- Verdict de hipótesis cambió
|   +-- Código o datos derivaron del pre-registro. Revisar PRIMARY_SPEC_HASH.txt.
+-- Clase país-política cambió sin cambio de referencia
|   +-- Revisar precedencia determinística §18.2 y prob_basis = all_draw.
+-- verify.py mismo da error
    +-- Posible cambio de esquema. Revisar tag Git contra reference_manifest.json.
```

---

## Versionado

Tags Git explícitos por submission y revisión:

```text
v1.0.0-initial-submission
v1.0.1-initial-submission-fix
v1.1.0-revision-1
```

- `v1.0.0`: código/datos del primer submission.
- Patch (`v1.0.1`): fixes que no cambian resultados reportados.
- Minor (`v1.1.0`): cambios de reviewer-response que sí cambian resultados.
- Major: reescritura sustancial del paper o del paquete.
- El DOI Zenodo citado apunta al tag exacto de esa versión del manuscrito.
- **El `dataset_version` es ortogonal al tag de código.** Una corrida se identifica
  por (tag de código, `dataset_version`, `parameter_set_id`). Cambiar cualquiera de
  los tres es una corrida distinta.

---

## Zenodo y GitHub

Incluir `CITATION.cff` y `.zenodo.json`. La metadata debe coincidir con **este**
paper (no reutilizar el título de otro proyecto).

Un único depósito Zenodo versionado contiene código + snapshot ligero + outputs canónicos + derivados de microdatos (un solo DOI por versión); si el snapshot supera el límite de tamaño, se separa en un segundo depósito de datos con DOI propio y ambos se citan en el data availability statement.

```json
{
  "title": "Code and data for: AI, Fiscal Space, and Universal Social Protection in Emerging Economies — A Robust Accounting-Fiscal Threshold Framework",
  "creators": [ { "name": "Scavino, Vicenzo", "orcid": "0000-0000-0000-0000" } ],
  "description": "Reproduction package for the calibrated threshold-accounting framework computing AI-induced effective fiscal space, gross-cost feasibility ratios, threshold inversions, historical fiscal-capture plausibility, and Monte Carlo crossing probabilities for Peru, Chile, Colombia and Mexico. Includes the deterministic core, Monte Carlo uncertainty, a frozen public-data snapshot, and falsification diagnostics.",
  "license": "MIT",
  "upload_type": "software",
  "keywords": ["artificial intelligence", "fiscal space", "universal social protection", "universal basic income", "informality", "fiscal capacity", "labor share", "emerging economies", "Latin America"],
  "related_identifiers": []
}
```

Código bajo MIT; datos/derivados/figuras bajo CC-BY-4.0; microdatos crudos bajo la
licencia de su fuente nacional (documentado en el data policy). Al existir arXiv/DOI
de journal, actualizar `related_identifiers` en un release nuevo. El paper cita el
DOI versión-específico.

---

## Mapeo paper-to-code

El README incluye una tabla que mapea cada afirmación/figura/tabla del paper al
código y al artefacto de verificación, nombrando la ecuación del paper y la hipótesis.

```markdown
| Elemento del paper | Ancla (ecuación/sección) | Hipótesis | Código | Output | Verificación |
| --- | --- | --- | --- | --- | --- |
| Índice de factibilidad V | §Feasibility def. | H1 | src/ai_usp/thresholds.py | fiscal_space_result.csv | verify.py (Tier A) + test_cost_monotonicity |
| Orden PEN/MUT<GMI<PBI<UBI | §Expected pattern | H1 | src/ai_usp/policy_cost.py | policy_feasibility_ranking.csv | hypothesis_adjudication H1 |
| Adopción productiva importa | §Translation | H2 | src/ai_usp/translation.py, adoption.py | threshold_inversion_result.csv | test_zero_qprod + q_prod_required |
| Informalidad por dos vías | §Labor / §Fiscal | H3 | src/ai_usp/adoption.py, fiscal_channels.py | diagnostic_result.csv | ablation adopción-only/fiscal-only |
| El régimen fiscal importa | §Fiscal conversion | H4 | src/ai_usp/fiscal_channels.py | scenario_regime_grid.csv | erosion companion r>=1 |
| Cruce con captura extrema = frágil | §Historical plausibility | H5 | src/ai_usp/historical.py | historical_plausibility_table.csv | test_historical_class |
| Placebo ICT no financia USP | §Falsification | — | src/ai_usp/diagnostics.py | diagnostic_result.csv | run-diagnostics (Tier D) |
```

---

## Contenido de METHODS.md

Secciones requeridas (versión completa para Fase B; versión mínima para Fase A):

1. Por qué el motor es una implementación explícita en `src/ai_usp/` (transparencia
   de las convenciones anti-doble-conteo), no una caja negra.
2. Conversión del shock IA: `phi_raw` -> `phi_Y_nom` (bridges `kappa`, `pi_AI_Y`) y
   por qué `phi_raw` nunca entra a ecuaciones fiscales.
3. Traducción doméstica: `S_NDC`, calibración de `S_frontier` (consistencia
   poblacional con `phi_s`), y el objeto de nivel acumulado `g_AI_level`.
4. **Convención de trayectoria congelada (frozen_anchor_2024)** y por qué hace
   `g=(1+phiT)^H-1` exacta; declaración explícita de la dirección del sesgo de
   congelar T en 2024.
5. Construcción de los pesos de canal `omega_L/K/C` y `lambda_AI` (frozen weights) y
   la regla frozen-weight vs endógeno.
6. Convención endpoint de costos (H=10, 2024->2034): escalado demográfico UN WPP y
   por qué `Y0_2034` nunca se necesita en niveles.
7. Modo channel-based vs historical reduced-form; disciplina de percentiles.
8. Captura histórica: `MFC_hist_gross`, soporte positivo, mezcla incondicional con
   `p^-`.
9. Guardrail de deuda `sPB` y la separación `R_req` / `R_req_DC`.
10. Monte Carlo: distribuciones PERT/beta, dependencia rank-correlated, política de
    seed y convergencia.
11. Tolerancias por tier y por qué son aceptables (tabla, no prosa).
12. La arquitectura de cuatro tiers y qué es reproducible en cada uno, incluido el
    contrato de snapshot congelado.
13. Diferencia entre `reproduce-deterministic`, `reproduce-full`, `run-diagnostics` y
    `build-from-frozen-dataset`.
14. Política de snapshot de datos, licencias y microdatos restringidos.
15. Mecanismos separados de informalidad (adopción + captura fiscal; partición índice/techo; base-o-tasa).
16. GMI: cuatro versiones canónicas y carga theta_target; regla de ranking.
17. Companion de erosión conductual (7.4.2): ecuación de base erosionada, epsilon=0 en r0, grilla declarada, restricción epsilon*tau < 1.

Target de detalle: convención endpoint, tiers y modos de reproducción, un párrafo
cada uno; construcción de canales y calibración de `S_frontier`, uno a dos párrafos
más ecuaciones; tolerancias, tabla por tier. Longitud objetivo Fase B: 8–12 páginas.

---

## Secuencia de implementación

| # | Fase | Tarea | Estimado | Criterio de salida |
|---|---|---|---|---|
| 1 | A | Repo limpio con el layout objetivo | 1–2 h | Repo vacío con la estructura. |
| 2 | A | `pyproject.toml`, Dockerfile simple, `.dockerignore`, `Makefile`, `.gitignore`, `PRIMARY_SPEC_HASH.txt` | 3–5 h | `docker build` OK y paquete instala. |
| 3 | A | Capa de ingesta mínima + `build_snapshot.py` (freezing + hashes) para el MVP ejecutable del plan 01 (corte vertical: primero `PER` end-to-end como piloto, plan 01 §23; el benchmark frontier y los insumos globales se descargan siempre completos) | 1–2 d | `dataset_manifest.json` con hashes; snapshot piloto reconstruible. |
| 4 | A | Motor `src/ai_usp/`: shock, translation, adoption, labor_share, fiscal_channels, policy_cost, fiscal_space, thresholds, historical | 3–5 d | Paquete importable, sin ejecución global. |
| 5 | A | Fórmulas cerradas de threshold inversion (`thresholds.py`) | 1–2 d | `g_ai_required`, `MFC_required`, `T_required`, flags computables. |
| 6 | A | `experiments/phase2`, `phase3`, `phase4` y `phase5`; wire `run_all.py --tier A` | 4–8 h | `make reproduce-deterministic` produce outputs canónicos Tier A. |
| 7 | A | Referencia mínima + `tests/fixtures/mini_snapshot/` | 2–4 h | CSV de referencia pequeños; mini-snapshot para CI. |
| 8 | A | `schemas.yaml`, `tolerances.yaml` (Tier A + C), `verify.py` con check de hash de input | 1–2 d | `make verify` hard-falla en mismatch numérico/esquema/hash. |
| 9 | A | Tests núcleo: determinism, regression, bilinear_corner, mfc_mode_exclusion, endpoint_scaling, verify | 1 d | Tests núcleo pasan en Docker. |
| 10 | A | Pre-flight (incl. dataset-hash y primary-spec-hash) | 2–4 h | Env/hash malos abortan antes de computar. |
| 11 | A | `manifest.json` con commit, dataset_version, run_modes, hashes de output | 3–5 h | Cada corrida registra provenance. |
| 12 | A | `README.md`, `METHODS.md` mínimo, borradores `CITATION.cff`/`.zenodo.json`, adjudicación H1–H5 borrador | 4–8 h | Revisor puede correr y entender el MVP. |
| 13 | A | Correr `reproduce-deterministic` + `verify` desde build Docker limpio | 2–4 h | MVP Tier A reproduce desde checkout limpio. |
| 14 | B | Tier B: `phase6` Monte Carlo (independiente + rank-correlated) + `mc_convergence_report` + tolerancia Tier B | 2–3 d | Outputs Tier B verifican en tier relajado; convergencia OK. |
| 15 | B | Tier D: `phase7` placebo ICT (pipeline completo era-consistente), negative controls, LOSO, ablation | 2–3 d | `run-diagnostics` produce verdicts esperados. |
| 16 | B | Checkpoint/resume por celda; logging estructurado | 1–2 d | Corrida interrumpida resume desde bloques completos. |
| 17 | B | Endurecer `verify.py`, completar `test_verify` (incl. dataset-hash y tier B) | 1 d | Filas/columnas/NaN/tipos/manifest/hipótesis/hash testeados. |
| 18 | B | `reference_manifest.json` + workflow de update de referencia y snapshot | 3–5 h | Referencia registra tag, commit, dataset_version, hashes. |
| 19 | B | Calibrar tolerancias finales desde 3 corridas por tier | 2–4 h | Tolerancias documentan diferencia máxima y factor. |
| 20 | B | GitHub Actions (Docker, artifacts, `pip-audit` advisory, mini-snapshot) | 4–8 h | CI corre Tier A sin cuenta externa y sube artifacts. |
| 21 | B | `METHODS.md` completo, `CONTRIBUTING.md`, `LICENSE-DATA`, `CITATION.cff`/`.zenodo.json` finales | 1–2 d | Documentación archival completa. |
| 22 | B | `.pre-commit-config.yaml` (incl. large-file guard para `data/raw/`) | 2–4 h | Formato/lint y guard de archivos grandes disponibles. |
| 23 | B | Pinear Docker por digest; re-correr `reproduce-full` | dependiente de hardware | Imagen de release y outputs completos verificados juntos. |
| 24 | B | Tag GitHub, conectar Zenodo, insertar DOI versión-específico, recompilar paper | 2–4 h + Zenodo | El manuscrito cita el release exacto de código/datos/snapshot. |

Fase A ocurre antes o junto a la preparación final del manuscrito. Fase B ocurre
después de que la historia numérica es estable y antes del archivo público.

---

## Paso inmediato

Antes de agregar experimentos, completar los pasos 1–6 de la Fase A: repo limpio,
Docker simple, capa de ingesta + freezing del **MVP ejecutable** (plan 01 §23.2),
motor `src/ai_usp/` con los bloques del baseline, fórmulas cerradas de inversión, y
`make reproduce-deterministic` generando los outputs Tier A (Fases 2-5). El
argumento de aceptación central del paper es la frontera de factibilidad y sus
umbrales requeridos, así que el **Tier A determinista** es el entregable de
reproducibilidad que carga más peso y debe quedar sólido primero. El Tier B (Monte
Carlo con convergencia) y el Tier D (diagnósticos/falsificación) se agregan dentro de
la misma estructura reproducible en la Fase B.

> **Recordatorio de secuencia global.** Este documento se redacta ahora para que
> guíe, pero su implementación es el último eslabón: el go/no-go real sigue siendo
> cerrar el gate de Fase 0 del plan 02 (`labor_share_anchor`, `S_frontier`,
> `q_use_target`) y escribir el motor determinístico. No dejes que montar la
> reproducibilidad completa desplace ese frente.
