# 01 — Plan de construcción de base de datos
## AI, Fiscal Space, and Universal Social Protection in Emerging Economies — Framework v2.5

**Documento:** plan de construcción de base de datos, no ejecución del modelo.  
**Paper leído:** `AI_USP_Threshold_Framework_v2_5_corrected.tex`  
**Versión del paper:** v2.5, junio 2026  
**Versión de este plan:** v6, versión más actual con trazabilidad, parámetros de política, calidad de datos, separación base/reproducción, matriz variable-fuente, benchmark frontier, costos administrativos y de transición, nivel de gobierno, ventana histórica, correcciones de consistencia contra el paper v2.5 corregido y correcciones finales C1-C7 aplicadas, consistencia cruzada con el plan de diseño (endpoint 2034/WPP, canonicidad de esquemas, scenario_id stress, draw_parameter_value, p_negative_capture) y dos rondas de revisión externa aplicadas.  
**Países cubiertos:** Perú, Chile, Colombia y México.  
**Año base recomendado:** 2024.  

---

# 0. Propósito exacto de este documento

Este documento **solo diseña la base de datos** necesaria para probar después el framework teórico-económico-matemático del paper.

No ejecuta:

- simulaciones finales;
- Monte Carlo;
- threshold inversion;
- figuras finales;
- tablas de resultados del paper;
- diagnósticos causales o placebos.

Sí define:

- qué datos públicos bajar;
- qué países cubrir;
- qué variables observar, construir o parametrizar;
- qué tablas raw, interim y processed crear;
- cómo documentar fuentes y transformaciones;
- cómo preparar la base para que un plan posterior de reproducción pueda correr el modelo sin ambigüedad;
- qué tablas de resultados serán necesarias más adelante, pero sin ejecutarlas aquí.

Separación metodológica:

| Documento | Función |
|---|---|
| `00_master_replication_plan.md` | Mapa general del proyecto reproducible. Define carpetas, scripts, outputs, orden de ejecución y estándares. |
| `01_database_construction_plan.md` | Este documento. Construye, armoniza y audita la base. No corre el modelo. |
| `02_ESD_AI_USP_v6.md` | Estrategia empírica y diseño de simulación (ESD): especificación primaria, horizonte acumulado, fases 0-9 con gates, threshold inversion, Monte Carlo y reglas de reporte. Ejecuta el framework con la base construida. |

Regla central:

> La base de datos debe dejar listos los insumos observados, construidos y parametrizados. La reproducción del modelo debe usar esos insumos, pero pertenece a otro plan.

---

# 1. Lectura ejecutiva del framework

El paper no intenta demostrar que la inteligencia artificial financiará automáticamente una renta básica universal. Su contribución es construir una **frontera contable-fiscal de factibilidad** para preguntar bajo qué combinaciones mínimas de productividad inducida por IA, adopción productiva, captura fiscal, reducción de informalidad, distribución funcional del ingreso y costo de política social una política universal o semi-universal podría ser fiscalmente cubierta.

La unidad lógica central es:

$$
fs^{eff}_{i,p,s,r,t} \geq c_{i,p,t}
$$

con índice de factibilidad:

$$
V_{i,p,s,r,t}=\frac{fs^{eff}_{i,p,s,r,t}}{c_{i,p,t}}
$$

La política cruza el umbral contable cuando:

$$
V_{i,p,s,r,t}\geq 1
$$

Donde:

| Símbolo | Significado |
|---|---|
| `i` | País. |
| `p` | Política social. |
| `s` | Escenario de IA. |
| `r` | Régimen fiscal. |
| `t` | Año. |
| `fs_eff` | Espacio fiscal efectivo inducido por IA como porcentaje del PIB. |
| `c` | Costo anual de la política como porcentaje del PIB. |
| `V` | Índice de factibilidad contable-fiscal. |

La base debe permitir construir, para cada celda país-política-escenario-régimen-año:

$$
\left(A_i,E^{prod}_i,q^{prod}_{i,s,t},I_i,MFC^{gross}_{i,s,r,t},fs^{eff}_{i,p,s,r,t},c_{i,p,t},V_{i,p,s,r,t}\right)
$$

Pero este documento llega solo hasta dejar la base lista para que esas celdas puedan calcularse después.

---

# 2. Alcance empírico

## 2.1 Países incluidos

El paper menciona una aplicación piloto regional. La primera base no debe expandirse a todos los países.

| País | ISO3 | Rol | Motivo |
|---|---|---|---|
| Perú | `PER` | Caso principal | Alta informalidad, baja presión tributaria, restricción fiscal fuerte. |
| Chile | `CHL` | Comparador superior regional | Mayor capacidad institucional/fiscal y mejor preparación relativa. |
| Colombia | `COL` | Comparador andino | Sistema social más grande, informalidad persistente. |
| México | `MEX` | Comparador grande | Economía grande, integración productiva más profunda, baja recaudación relativa OCDE. |

Decisión:

> La primera base debe cubrir únicamente Perú, Chile, Colombia y México.

## 2.2 Año de armonización

Año base:

$$
t_0=2024
$$

Reglas:

1. Si existe dato 2024, se usa 2024.
2. Si el dato más cercano es anterior, se arrastra y se marca con `carried_forward_flag=TRUE` y `carried_forward_from_year`.
3. Si se usa dato posterior a 2024, se marca con `non_harmonized_robustness=TRUE`, salvo que todos los anclajes macro también se actualicen al mismo año.
4. No se mezclan años silenciosamente.
5. Toda variable final debe tener `year_original` y `year_harmonized` cuando aplique.

## 2.3 Caso especial: Colombia 2026

El valor de informalidad de Colombia para enero-marzo 2026 puede servir como sensibilidad, pero no como baseline 2024 si el resto de la base está anclada en 2024.

Tratamiento recomendado:

| Uso | Regla |
|---|---|
| Baseline | Buscar informalidad 2024 en DANE/GEIH, SEDLAC o ILOSTAT. |
| Robustez | Usar Colombia 2026 solo con `non_harmonized_robustness=TRUE`. |
| Reporte | Explicar que no está temporalmente armonizado con el baseline si se usa como sensibilidad. |

---


## 2.4 Cobertura temporal de las descargas

El año base 2024 aplica a la armonización del baseline, NO al rango de descarga. Todas las series país-año se descargan como panel 2000-2024 como mínimo, porque:

1. `MFC_hist` requiere la ventana 2000-último año disponible, con robustez 2010- y 2015-.
2. El placebo ICT del paper requiere inputs era-consistentes 2010-2018: adopción ICT histórica, costos de política históricos, informalidad histórica y distribuciones fiscales históricas.
3. Los percentiles históricos deben poder recalcularse con y sin 2020-2021.

Los proxies del placebo ICT (`q_ICT`, `E_ICT`) se construyen desde las series históricas ITU/WDI ya cubiertas por esta ventana y se mapean en `variable_source_map` como cualquier variable final.

Convención endpoint del plan de diseño (H=10, endpoint 2034): descargar además proyecciones de población UN WPP (variante media) 2024-2035, total y grupos quinquenales de edad (65+, 15-64 y 18+ como derivados), por país, en una tabla `raw_wpp_projections` (mismos campos que `raw_wdi_indicator` más un campo `variant`). Son el insumo del ratio demográfico de elegibilidad al endpoint, crítico para `PEN` por el envejecimiento acelerado de Chile y Colombia hacia 2034. Las líneas de pobreza y los beneficios al endpoint se manejan por convención declarada en el plan de diseño, no por proyección de datos.

---

# 3. Valores semilla del paper

Estos valores pueden ayudar a inicializar la base, pero no reemplazan la reconstrucción desde fuentes públicas.

| País | AIPI | PIB 2024 USD bn | PIB pc 2024 USD | Tax/GDP | Informalidad semilla |
|---|---:|---:|---:|---:|---|
| Perú | 0.49 | 289.22 | 8,452.4 | 17.0% | 72.2% empleo informal adulto, 2022, arrastrado a 2024; estimaciones amplias >70%. |
| Chile | 0.59 | 330.27 | 16,709.9 | 20.6% | 27.5% tasa de ocupación informal, 2024. |
| Colombia | 0.49 | 418.82 | 7,919.2 | 22.1% | 55.3% trabajadores ocupados informales, ene-mar 2026; usar como robustez no armonizada. |
| México | 0.53 | 1,856.37 | 14,185.8 | 17.7% | 54.3% informalidad laboral, T2 2024. |

Tabla sugerida:

## `seed_paper_values`

| Campo | Tipo | Descripción |
|---|---|---|
| `country_id` | TEXT | ISO3. |
| `variable_name` | TEXT | Variable reportada en el paper. |
| `value` | DOUBLE | Valor semilla. |
| `unit` | TEXT | Unidad. |
| `year_original` | INTEGER | Año original. |
| `year_harmonized` | INTEGER | Año al que se quiere armonizar. |
| `paper_location` | TEXT | Tabla, sección o nota del paper. |
| `use_status` | TEXT | seed_only / baseline_if_verified / robustness_only. |
| `notes` | TEXT | Comentario metodológico. |

Regla:

> Los valores semilla sirven para comprobar que la base va en la dirección correcta, pero la base final debe reconstruirlos desde fuentes públicas siempre que sea posible.

---

# 4. Políticas sociales que debe cubrir la base

El paper usa cinco instrumentos.

| Código | Política | Interpretación |
|---|---|---|
| `PEN` | Universal Social Pension | Pensión social universal para población sobre una edad umbral. |
| `MUT` | Minimum Universal Transfer | Transferencia universal mínima, usualmente una fracción de línea de pobreza. |
| `GMI` | Guaranteed Minimum Income | Ingreso mínimo garantizado que cubre una fracción de la brecha de pobreza. |
| `PBI` | Partial Basic Income | Renta básica parcial, intermedia entre MUT y UBI. |
| `UBI` | Full UBI benchmark | Benchmark de estrés fiscal, no política base recomendada. |

## 4.1 Fórmulas de costo

Costo bruto:

$$
C^{gross}_{i,p,t}=B_{i,p,t}N_{i,p,t}
$$

Costo bruto como porcentaje del PIB sin IA:

$$
c^{gross,0}_{i,p,t}=\frac{C^{gross}_{i,p,t}}{Y^0_{i,t}}
$$

Costo neto:

$$
C^{net}_{i,p,t}=\max\{0,C^{gross}_{i,p,t}-C^{exist}_{i,p,t}\}
$$

$$
c^{net,0}_{i,p,t}=\frac{C^{net}_{i,p,t}}{Y^0_{i,t}}
$$

Costos por política:

$$
C^{PEN,gross}_{i,t}=B^{PEN}_{i,t}Pop^{a\geq a^*}_{i,t}
$$

$$
C^{MUT,gross}_{i,t}=\eta_{MUT}PL_{i,t}N^{MUT}_{i,t}
$$

$$
C^{GMI,gross}_{i,t}=\chi_{GMI}\sum_h w_{h,i,t}n_{h,i,t}\max\{0,z_{i,t}-y^{pc}_{h,i,t}\}
$$

$$
C^{PBI,gross}_{i,t}=\eta_{PBI}PL_{i,t}N^{PBI}_{i,t}
$$

$$
C^{UBI,gross}_{i,t}=\eta_{UBI}PL_{i,t}Pop_{i,t}
$$

---

# 5. GMI: dos niveles obligatorios

El `GMI` no debe quedar como “si hay tiempo” en la versión final si el paper quiere presentarlo con seriedad.

Debe haber cuatro valores canónicos de `gmi_version`:

| Versión | Método | Uso permitido |
|---|---|---|
| `GMI_ideal_aggregate` | Poverty gap agregado de PIP/SEDLAC/fuente nacional. | Baseline mínimo, aproximación agregada. |
| `GMI_loaded_aggregate` | Poverty gap agregado de PIP/SEDLAC/fuente nacional con `theta_target`. | Robustez conservadora agregada. |
| `GMI_ideal_microdata` | Microdatos de hogares con pesos muestrales e ingreso/consumo per cápita. | Estimación fuerte para paper. |
| `GMI_loaded_microdata` | Microdatos de hogares con pesos muestrales e ingreso/consumo per cápita con `theta_target`. | Robustez conservadora con microdatos. |

Nota: Nombres canónicos del plan de diseño; el MVP agregado corresponde a `GMI_ideal_aggregate` y el paper-ready con microdatos a `GMI_ideal_microdata`.

Regla de reporte:

> Si no se usan microdatos, el GMI debe reportarse como aproximación agregada, no como microsimulación completa.

Regla adicional de reporte:

> Ambas versiones del GMI deben reportarse en dos variantes: focalización ideal (baseline) y cargada con `theta_target` en [1.0, 1.5]. El costeo por brecha de pobreza asume identificación perfecta, tapering perfecto y cero respuesta conductual (TMR implícita de 100% bajo el umbral z), y el ranking GMI-antes-que-UBI es parcialmente mecánico sin esta carga.

Tabla de control:

## `gmi_estimation_status`

| Campo | Tipo | Descripción |
|---|---|---|
| `country_id` | TEXT | País. |
| `year` | INTEGER | Año. |
| `gmi_version` | TEXT | GMI_ideal_aggregate / GMI_loaded_aggregate / GMI_ideal_microdata / GMI_loaded_microdata. |
| `microdata_used` | BOOLEAN | TRUE/FALSE. |
| `survey_name` | TEXT | ENAHO, CASEN, GEIH, ENCV, ENIGH, etc. |
| `poverty_gap_used` | BOOLEAN | TRUE/FALSE. |
| `income_or_consumption` | TEXT | income / consumption. |
| `welfare_concept` | TEXT | Concepto de bienestar. |
| `limitation_notes` | TEXT | Limitaciones. |

---

# 6. Tipos de variables: observadas, construidas y parámetros

La base debe etiquetar cada variable según su naturaleza.

| Tipo | Ejemplos | Tratamiento |
|---|---|---|
| Observada | PIB, población, impuestos, AIPI, informalidad, labor share, pobreza agregada. | Se traza a fuente pública. |
| Construida | costos de política, `MFC_hist`, percentiles históricos, digital gap. | Se traza a script + fuentes + fórmula. |
| Parámetro de política | edad umbral, beneficio, eta, chi, regla de elegibilidad. | Se guarda en `policy_parameter`. |
| Parámetro de escenario | shock IA, captura de rentas IA, leakage, elasticidades. | Se guarda en `assumption_registry` y luego en `parameter_set`. |
| Resultado de corrida | `fs_eff`, `V`, Monte Carlo, threshold inversion. | No pertenece a base observada; requiere `run_id` y `model_version`. |

Regla:

> Datos observados llevan trazabilidad de fuente. Resultados del modelo llevan trazabilidad de corrida.

---

# 7. Bloques de datos necesarios

## 7.1 Macro

| Variable | Uso | Fuente principal |
|---|---|---|
| PIB nominal | Denominador de costos y espacio fiscal | WDI, cuentas nacionales. |
| PIB real / crecimiento real | Robustez macro y acumulación | WDI, Penn World Table. |
| PIB per cápita | Ancla comparativa | WDI. |
| Población total | UBI, MUT, PBI | WDI. |
| Población por edad | PEN y elegibilidad | WDI, UN WPP, institutos nacionales. |
| Tipo de cambio | Conversión moneda local/USD | WDI, bancos centrales. |
| Deflactor PIB / IPC | Armonización nominal-real | WDI, bancos centrales, institutos estadísticos. |

## 7.2 Pobreza y distribución

| Variable | Uso | Fuente |
|---|---|---|
| Línea de pobreza nacional | Beneficio MUT/PBI/UBI y umbral GMI | PIP, SEDLAC, fuentes nacionales. |
| Línea internacional PPP | Robustez comparativa | World Bank PIP. |
| Headcount poverty | Validación de población objetivo | PIP, SEDLAC. |
| Poverty gap | Aproximación agregada del GMI | PIP, SEDLAC. |
| Ingreso/consumo per cápita de hogares | GMI exacto | ENAHO, CASEN, GEIH/ENCV, ENIGH. |
| Pesos muestrales | GMI exacto | Encuestas de hogares. |
| Tamaño del hogar | GMI exacto | Encuestas de hogares. |

## 7.3 Fiscal

| Variable | Uso | Fuente |
|---|---|---|
| Tax revenue/GDP | Ancla de capacidad fiscal | OECD Revenue Statistics, GRD, WDI. |
| Total revenue/GDP | Capacidad fiscal amplia | GRD, IMF WEO/GFS. |
| Social contributions/GDP | Separar impuestos de contribuciones | OECD/GRD. |
| Direct taxes | Canal laboral/capital | OECD/GRD. |
| Indirect taxes / VAT | Canal consumo | OECD/GRD. |
| Corporate/profit taxes | Canal capital/profit | OECD/GRD, administraciones tributarias. |
| Resource revenue | Ajuste no-recurso | GRD, IMF, fuentes nacionales. |
| Primary balance | Guardrail de deuda | IMF WEO, ministerios de finanzas. |
| Public debt/GDP | Guardrail de deuda | IMF WEO, ministerios de finanzas. |
| Exenciones IVA / gasto tributario (`exempt_C`) | Canal consumo | Informes de gasto tributario: SUNAT (Perú), DIPRES/Hacienda (Chile), DIAN (Colombia), SHCP (México). |

Nota: El `tau_C_eff` puede construirse como C-efficiency del IVA: recaudación de IVA / (consumo final x tasa estándar), con insumos ya planificados (OECD RevStats + `NE.CON.TOTL.ZS`).

## 7.4 Mercado laboral, informalidad y distribución funcional

| Variable | Uso | Fuente |
|---|---|---|
| Informalidad laboral total | Fricción fiscal y adopción | ILOSTAT, SEDLAC, LABLAC, fuentes nacionales. |
| Informalidad por sector | Canal sectorial y fiscal | Encuestas nacionales, ILOSTAT. |
| Empleo por ocupación | Exposición IA | ILOSTAT, encuestas laborales. |
| Empleo por sector | Exposición sectorial | ILOSTAT, cuentas nacionales. |
| Labor share | Canal distribución funcional | Penn World Table, cuentas nacionales. |
| Formación/reskilling | Proxy de `RST` | ILOSTAT, OCDE, fuentes nacionales. |

## 7.5 Preparación digital e IA

| Variable | Uso | Fuente |
|---|---|---|
| AIPI agregado | Preparación IA `A_i` | IMF AI Preparedness Index. |
| Infraestructura digital | Reconstrucción alternativa de AIPI | IMF AIPI, ITU, WDI. |
| Capital humano / política laboral | Reconstrucción alternativa | IMF AIPI, WDI, ILOSTAT. |
| Innovación / integración económica | Reconstrucción alternativa | IMF AIPI, WDI, WIPO, OECD. |
| Regulación / ética | Reconstrucción alternativa | IMF AIPI, GovTech, WGI, IMF. |
| Brecha digital `Gap` | Techo de adopción | ITU, WDI, encuestas TIC. |
| Momento ancla de adopción (`q_use_target`) | Módulo de adopción | Encuestas TIC/firmas nacionales (ENDUTIH-INEGI; encuestas TIC INEI/INE/DANE), WB Firm-level Adoption of Technology (FAT), OECD ICT/AI use in enterprises. |

## 7.6 Exposición a IA

| Variable | Uso | Fuente |
|---|---|---|
| Exposición productiva `Eprod` | Traducción de shock IA | World Bank-ILO, task-based exposure datasets. |
| Exposición displacement `Edisp` | Riesgo de automatización/labor share | World Bank-ILO, occupational mapping. |
| Exposición total | Control | World Bank-ILO. |
| Exposición por ocupación | Versión fuerte | Encuestas laborales + matriz ocupación-tarea. |
| Exposición por sector | Negative controls y robustez | ILOSTAT, cuentas nacionales. |

Fallback regional para América Latina:

| Medida | Rango usado como soporte inicial |
|---|---:|
| Exposición total a GenAI | 26%–38% de empleos. |
| Transformación productiva | 8%–14%. |
| Riesgo de automatización completa | 2%–5%. |

---

# 8. Fuentes públicas y factibilidad real

| Bloque | ¿Existe dato público? | Dificultad | Comentario práctico |
|---|---:|---:|---|
| PIB, población, PIB pc | Sí | Baja | WDI resuelve casi todo. |
| Pobreza agregada | Sí | Media | PIP/SEDLAC; cuidado con líneas y unidades. |
| Microdatos hogares para GMI | Sí, pero pesado | Alta | Necesario para GMI fuerte. |
| Recaudación tributaria | Sí | Baja-media | OECD/GRD para los cuatro países. |
| Estructura tributaria | Sí | Media | OECD Revenue Statistics es clave. |
| Balance primario y deuda | Sí | Media | IMF WEO + ministerios. |
| Informalidad agregada | Sí | Media | Definiciones no idénticas; etiquetar fuente. |
| Informalidad por sector/base fiscal | Parcial | Alta | Requiere encuestas o supuestos. |
| Labor share | Sí | Baja-media | Penn World Table. |
| AIPI | Sí | Baja | Usar valor publicado o reconstrucción, no mezclar. |
| Brecha digital | Sí | Media | ITU/WDI/encuestas TIC. |
| Exposición IA país-específica | Parcial | Alta | Ideal: ocupaciones nacionales + matriz de exposición. |
| Adopción productiva `qprod` | No directamente | Alta | Variable calibrada del modelo. |
| Captura de rentas IA | No directamente | Alta | Escenario/régimen, no dato observado. |
| Profit shifting / leakage | Parcial | Alta | Parámetro y robustez. |

Conclusión:

> La base pública es factible, pero no todo será dato observado. Las variables no observables deben entrar como parámetros, escenarios o Monte Carlo, no como “datos reales”.

---

# 9. Arquitectura recomendada

## 9.1 Motor

Usar:

- DuckDB como base local reproducible.
- Parquet para tablas limpias e intermedias.
- CSV solo para descargas raw o outputs legibles.
- Python/R para ETL.

## 9.2 Estructura de carpetas

```text
project/
  data/
    raw/
      wdi/
      pip/
      sedlac/
      oecd_revenue/
      grd/
      imf_weo/
      aipi/
      ilostat/
      pwt/
      itu/
      frontier/
      wpp/
      aspire/
      national/
        peru/
        chile/
        colombia/
        mexico/
    interim/
    processed/
    model_inputs/
    model_outputs/        # vacío o no generado en este plan; usado por reproducción posterior
  db/
    ai_usp_threshold.duckdb
  scripts/
    00_config/
    01_download/
    02_clean/
    03_construct_database/
    04_validate_database/
    05_export_model_inputs/
  docs/
    01_database_construction_plan.md
    data_dictionary.md
    source_registry.md
    assumptions_registry.md
    variable_source_map.md
  outputs/
    database_reports/
    logs/
```

Nota:

> Las carpetas `model_outputs` y scripts de simulación pueden existir como placeholders, pero este plan no los ejecuta.

---

# 10. Convenciones de trazabilidad

## 10.1 Tablas observadas y procesadas de datos

Para tablas de datos observados o anclas procesadas, usar:

| Campo | Tipo | Uso |
|---|---|---|
| `dataset_version` | TEXT | Versión de la base de datos construida. |
| `build_id` | TEXT | ID de construcción de la base. |
| `source_id` | TEXT | Fuente principal. |
| `download_date` | DATE | Fecha de descarga. |
| `created_at` | TIMESTAMP | Fecha de creación de la tabla. |
| `created_by_script` | TEXT | Script que generó la tabla. |

No usar `run_id` en tablas puramente observadas como `macro_anchor`, `fiscal_anchor`, `poverty_distribution_anchor`, `labor_informality_anchor` o `ai_preparedness_anchor`, porque todavía no son resultados del modelo.

## 10.2 Tablas derivadas por corrida del modelo

Para tablas que dependan de una corrida, escenario, sensibilidad o Monte Carlo, usar:

| Campo | Tipo | Uso |
|---|---|---|
| `run_id` | TEXT | ID único de corrida. |
| `model_version` | TEXT | Versión del modelo/código. |
| `parameter_set_id` | TEXT | Set de parámetros usado. |
| `dataset_version` | TEXT | Versión de la base de datos usada como input. |
| `created_at` | TIMESTAMP | Momento de creación. |
| `created_by_script` | TEXT | Script que generó el resultado. |

Aplicar a:

- `policy_cost`, si se calcula con supuestos de política;
- `adoption_module`, si depende de parámetros de adopción;
- `fiscal_conversion_module`, si depende de régimen y elasticidades;
- `fiscal_space_result`;
- `monte_carlo_result`;
- `threshold_inversion_result`;
- `diagnostic_result`.

Matiz importante:

> Si `policy_cost` se construye solo con datos observados y reglas normativas fijas, puede vivir como tabla construida de base con `dataset_version` y `assumption_id`. Si se recalcula bajo escenarios alternativos de beneficio/elegibilidad, también debe llevar `run_id` y `parameter_set_id`.

---

# 11. Tablas de dimensiones

## 11.1 `dim_country`

| Campo | Tipo | Descripción |
|---|---|---|
| `country_id` | TEXT | ISO3: PER, CHL, COL, MEX. |
| `country_name` | TEXT | Nombre del país. |
| `region` | TEXT | Latin America. |
| `income_group_2024` | TEXT | Clasificación Banco Mundial. |
| `pilot_role` | TEXT | primary_case / comparator. |

## 11.2 `dim_policy`

| Campo | Tipo | Descripción |
|---|---|---|
| `policy_id` | TEXT | PEN, MUT, GMI, PBI, UBI. |
| `policy_name` | TEXT | Nombre completo. |
| `policy_type` | TEXT | pension / transfer / guaranteed_income / basic_income / stress_benchmark. |
| `default_eligible_population_rule` | TEXT | Regla general. |
| `default_benefit_rule` | TEXT | Regla general. |
| `default_cost_formula` | TEXT | Fórmula base. |
| `is_stress_benchmark` | BOOLEAN | TRUE para UBI. |

## 11.3 `dim_ai_scenario`

| Campo | Tipo | Descripción |
|---|---|---|
| `scenario_id` | TEXT | low, mid, high, stress. |
| `scenario_label` | TEXT | Nombre; para `stress`, el scenario_label es 'Disruptive stress' (etiqueta del paper). |
| `raw_unit` | TEXT | TFP, LP o Y. |
| `phi_raw_low` | DOUBLE | Límite inferior. |
| `phi_raw_high` | DOUBLE | Límite superior. |
| `kappa_to_y_convention` | TEXT | Puente de unidad a GDP-equivalente (identidad si unidad=Y; <=1 baseline para LP y TFP). |
| `pi_ai_y_convention` | TEXT | Ajuste nominal del shock (puede ser negativo). |
| `interpretation` | TEXT | Forecast, central, stress, etc. |
| `source_discipline` | TEXT | Acemoglu/OECD/stress. |

Nota de semillas: Soportes del paper (siembra de la dimensión): low [0.0003, 0.0007] TFP-equivalente; mid [0.0025, 0.0060] TFP-equivalente; high [0.0040, 0.0130] LP-equivalente ANTES del puente `kappa_LP_to_Y`; stress [0.0100, 0.0200] GDP/TFP stress. Deterministas: 0.0005, 0.00425, 0.0085 (LP), 0.015. El shock que entra a las ecuaciones fiscales es siempre `phi_Y_nom` (tras puente de unidades y ajuste nominal), nunca `phi_raw`.

## 11.4 `dim_fiscal_regime`

| Campo | Tipo | Descripción |
|---|---|---|
| `regime_id` | INTEGER | 0,1,2,3,4. |
| `regime_code` | TEXT | r0...r4. |
| `regime_name` | TEXT | Nombre. |
| `description` | TEXT | Qué cambia. |
| `changes_tax_rates` | BOOLEAN | Sí/no. |
| `changes_ai_rent_capture` | BOOLEAN | Sí/no. |
| `changes_base_broadening` | BOOLEAN | Sí/no. |

Régimen fiscal:

| Régimen | Nombre | Descripción |
|---:|---|---|
| 0 | Status quo | Estructura tributaria efectiva actual, sin nueva captura de rentas IA. |
| 1 | Improved compliance | Mejor administración/reporte, sin cambio legal amplio. |
| 2 | Base broadening | Menores exenciones y bases laborales/capital/consumo más amplias. |
| 3 | AI-rent capture | Tributación explícita de rentas digitales o IA. |
| 4 | Combined reform | Cumplimiento + base broadening + captura de rentas IA. |

## 11.5 `dim_source`

| Campo | Tipo | Descripción |
|---|---|---|
| `source_id` | TEXT | Identificador interno. |
| `source_name` | TEXT | WDI, PIP, OECD Revenue, etc. |
| `provider` | TEXT | World Bank, OECD, IMF, etc. |
| `url_or_api` | TEXT | URL/API si aplica. |
| `download_date` | DATE | Fecha de descarga. |
| `license_notes` | TEXT | Notas de uso. |
| `raw_file_path` | TEXT | Ruta del archivo crudo. |
| `citation_text` | TEXT | Cita bibliográfica o institucional. |

---

# 12. Tabla operacional de parámetros de política

## `policy_parameter`

Esta tabla es indispensable. Las políticas no deben quedar como nombres en `dim_policy`; deben tener parámetros normativos observables o asumidos.

| Campo | Tipo | Descripción |
|---|---|---|
| `policy_parameter_id` | TEXT | Clave explícita del registro paramétrico (la referencia `policy_cost.policy_parameter_id` apunta a este campo). |
| `country_id` | TEXT | País. |
| `policy_id` | TEXT | PEN, MUT, GMI, PBI, UBI. |
| `year` | INTEGER | Año. |
| `age_threshold` | INTEGER | Edad mínima si aplica. |
| `eta_policy` | DOUBLE | Fracción de línea de pobreza o beneficio base. |
| `chi_gmi` | DOUBLE | Fracción de brecha cubierta por GMI. |
| `theta_target` | DOUBLE | Factor de carga de focalización y comportamiento del GMI, soporte [1.0, 1.5]. El costo cargado `C_GMI_load = theta_target x C_GMI_gross` debe reportarse junto al baseline de focalización ideal. |
| `benefit_formula` | TEXT | Fórmula de beneficio. |
| `eligible_population_rule` | TEXT | Regla de población elegible. |
| `gross_or_net_convention` | TEXT | gross / net / both. |
| `existing_spending_treatment` | TEXT | none / subtract_social_assistance / subtract_noncontributory_pensions / custom. Regla del paper: `C^exist` solo puede incluir gasto de protección social sustituible y NO contributivo; las pensiones contributivas y los beneficios con derechos adquiridos quedan excluidos del offset. |
| `poverty_line_convention` | TEXT | national / international_ppp / official_extreme / custom. |
| `indexation_rule` | TEXT | none / inflation / poverty_line_growth / wage_growth. |
| `source_id` | TEXT | Fuente normativa o estadística. |
| `assumption_id` | TEXT | Si el parámetro no es observado. |
| `dataset_version` | TEXT | Versión de base. |
| `created_at` | TIMESTAMP | Creación. |
| `created_by_script` | TEXT | Script. |

Justificación:

- `PEN` depende de edad mínima, monto de pensión y población elegible.
- `MUT` depende de fracción de línea de pobreza y población cubierta.
- `GMI` depende de línea de pobreza, brecha, ingreso objetivo y cobertura.
- `PBI` depende de monto parcial y población objetivo.
- `UBI` depende de población total y beneficio per cápita.

Regla:

> Ningún parámetro de política debe quedar escondido en el código.

---

# 13. Tablas raw

Las tablas raw guardan datos casi sin transformar.

## 13.1 `raw_wdi_indicator`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `year` | INTEGER |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |
| `download_date` | DATE |

Indicadores candidatos:

| Indicador | Uso |
|---|---|
| `NY.GDP.MKTP.CD` | PIB nominal USD. |
| `NY.GDP.MKTP.CN` | PIB nominal moneda local. |
| `NY.GDP.MKTP.KD.ZG` | Crecimiento real PIB. |
| `NY.GDP.PCAP.CD` | PIB per cápita USD. |
| `SP.POP.TOTL` | Población total. |
| `SP.POP.65UP.TO.ZS` | Población 65+ como porcentaje. |
| `FP.CPI.TOTL` | IPC. |
| `NY.GDP.DEFL.ZS` | Deflactor PIB. |
| `PA.NUS.FCRF` | Tipo de cambio oficial. |
| `NE.IMP.GNFS.ZS` | Importaciones como porcentaje del PIB. |
| `NE.CON.TOTL.ZS` | Consumo final como porcentaje del PIB. |

Nota:

> Verificar códigos exactos con metadata de WDI antes de congelar el pipeline.

## 13.2 `raw_oecd_revenue`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `tax_category_code` | TEXT |
| `tax_category_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |

Debe cubrir:

- Tax revenue/GDP.
- Total tax revenue.
- Personal income tax.
- Corporate income tax.
- Social security contributions.
- Taxes on goods and services.
- VAT/GST.
- Other taxes.

## 13.3 `raw_grd_revenue`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `variable_code` | TEXT |
| `variable_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `resource_adjusted` | BOOLEAN |
| `source_id` | TEXT |

Uso:

- Comparar OECD vs GRD.
- Construir ancla no-recurso.
- Evitar que commodities inflen artificialmente capacidad fiscal.

## 13.4 `raw_pip_poverty`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `poverty_line` | DOUBLE |
| `poverty_line_type` | TEXT |
| `unit` | TEXT |
| `currency` | TEXT (USD_PPP / LCU) |
| `periodicity` | TEXT (daily / monthly / annual) |
| `ppp_version` | TEXT (p.ej. `2017`) |
| `price_base_year` | INTEGER |
| `reporting_level` | TEXT (national / urban / rural) |
| `headcount` | DOUBLE |
| `poverty_gap` | DOUBLE |
| `mean_income_or_consumption` | DOUBLE |
| `welfare_type` | TEXT |
| `source_id` | TEXT |

Las líneas de PIP vienen en USD PPP POR DÍA (p.ej. 3.00/4.20/8.30 en PPP 2021 según versión); toda conversión a LCU anual ocurre en la fase de armonización con convención declarada en `variable_source_map`, nunca implícita. Confundir línea diaria PPP con anual LCU produce errores de tres órdenes de magnitud.

## 13.5 `raw_sedlac`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `survey_name` | TEXT |
| `source_id` | TEXT |

Priorizar:

- pobreza;
- poverty gap;
- desigualdad;
- informalidad;
- ingreso laboral;
- distribución del ingreso.

## 13.6 `raw_household_survey_microdata`

Tabla larga para microdatos armonizados. Puede ser muy grande.

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `survey_name` | TEXT |
| `household_id` | TEXT |
| `person_id` | TEXT |
| `record_grain` | TEXT (`person` / `household`) |
| `household_weight` | DOUBLE |
| `person_weight` | DOUBLE |
| `household_size` | INTEGER |
| `age` | INTEGER |
| `income_total` | DOUBLE |
| `income_pc` | DOUBLE |
| `consumption_total` | DOUBLE |
| `consumption_pc` | DOUBLE |
| `labor_status` | TEXT |
| `informal_status` | BOOLEAN |
| `occupation_code` | TEXT |
| `sector_code` | TEXT |
| `region_code` | TEXT |
| `currency` | TEXT |
| `frequency` | TEXT |
| `source_id` | TEXT |

Regla de grano (anti doble conteo GMI): la tabla es UNA FILA POR PERSONA; `income_total`, `consumption_total` y `household_size` son totales del HOGAR repetidos en cada miembro. Toda agregación de costo GMI se calcula a grano hogar: deduplicar por (`country_id`, `year`, `survey_name`, `household_id`) y ponderar con `household_weight`; `person_weight` se usa solo para conteos de personas. Sumar variables de hogar con `person_weight` sin deduplicar infla el costo por el tamaño medio del hogar. Test asociado en `data_quality_report`: la suma de `household_weight` deduplicado debe aproximar el número de hogares del país-año. (Separar en `raw_household` y `raw_person` queda como refactor opcional futuro, igual que el rename de `labor_informality_anchor`.)

Fuentes nacionales:

| País | Microdatos recomendados |
|---|---|
| Perú | ENAHO. |
| Chile | CASEN. |
| Colombia | GEIH / ENCV, según variable objetivo. |
| México | ENIGH para ingresos/gasto; ENOE para informalidad laboral. |

## 13.7 `raw_aipi`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `aipi_total` | DOUBLE |
| `digital_infrastructure` | DOUBLE |
| `human_capital_labor` | DOUBLE |
| `innovation_integration` | DOUBLE |
| `regulation_ethics` | DOUBLE |
| `source_id` | TEXT |

Reglas:

- Usar AIPI publicado como baseline.
- Reconstrucción geométrica solo como robustez.
- No mezclar AIPI publicado para unos países y reconstruido para otros.

## 13.8 `raw_ilostat`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `sex` | TEXT |
| `age_group` | TEXT |
| `sector_code` | TEXT |
| `occupation_code` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |

Uso:

- informalidad;
- empleo por ocupación;
- empleo por sector;
- formación/reskilling si existe.

## 13.9 `raw_pwt`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `rgdpo` | DOUBLE |
| `rgdpe` | DOUBLE |
| `pop` | DOUBLE |
| `emp` | DOUBLE |
| `avh` | DOUBLE |
| `labsh` | DOUBLE |
| `rtfpna` | DOUBLE |
| `source_id` | TEXT |

Uso principal:

- labor share `LS`;
- productividad;
- robustez macro.

Nota: la última versión de Penn World Table (10.01) llega aproximadamente hasta 2019. El `labor_share` para `t0=2024` será un carried-forward de ~5 años y debe marcarse con `carried_forward_flag` y `carried_forward_from_year`; complementar el LS raw reciente con cuentas nacionales (compensación de asalariados / PIB) de INEI, INE Chile/BCCh, DANE e INEGI.

## 13.10 `raw_aspire_social_protection`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `program_type` | TEXT |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |

Uso:

- gasto existente en asistencia social;
- gasto existente en pensiones/social insurance;
- cobertura;
- adecuación;
- transfer incidence.

## 13.11 `raw_imf_weo`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `variable_code` | TEXT |
| `variable_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |

Debe incluir:

- gross debt/GDP;
- primary balance/GDP;
- overall balance/GDP;
- nominal GDP;
- real GDP growth;
- inflation.

## 13.12 `raw_itu`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `value` | DOUBLE |
| `unit` | TEXT |
| `source_id` | TEXT |
| `download_date` | DATE |

Uso: conectividad, banda ancha, TIC histórica (incluye insumos `q_ICT` del placebo 2010-2018).

## 13.13 `raw_wpp_projections`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `indicator_code` | TEXT |
| `indicator_name` | TEXT |
| `year` | INTEGER |
| `value` | DOUBLE |
| `unit` | TEXT |
| `variant` | TEXT |
| `source_id` | TEXT |
| `download_date` | DATE |

Indicadores mínimos: `population_total` y población por grupos quinquenales de edad estándar (0-4, ..., 95-99, 100+), variante media, 2024-2035. Las series `population_65_plus`, `population_15_64` y `population_18_plus` se CONSTRUYEN como derivados de los grupos quinquenales; convención declarada para 18+: suma de los grupos 20+ más 2/5 del grupo 15-19 (interpolación uniforme), o edades simples si el script las descarga. Esto permite cualquier `age_threshold` de `policy_parameter` (p.ej. 60 o 65 para PEN) y la población adulta de UBI/PBI.

---

# 14. Tablas procesadas de base

Estas tablas sí pertenecen al plan de base de datos. Son insumos observados o construidos antes de correr el modelo.

## 14.1 `macro_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `gdp_nominal_usd` | DOUBLE |
| `gdp_nominal_lcu` | DOUBLE |
| `gdp_constant_lcu` | DOUBLE |
| `gdp_growth_real` | DOUBLE |
| `gdp_pc_usd` | DOUBLE |
| `population_total` | DOUBLE |
| `population_65_plus` | DOUBLE |
| `population_15_64` | DOUBLE |
| `exchange_rate_lcu_per_usd` | DOUBLE |
| `cpi_index` | DOUBLE |
| `gdp_deflator` | DOUBLE |
| `harmonization_flag` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

## 14.2 `poverty_distribution_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `poverty_line_national_lcu_annual` | DOUBLE |
| `poverty_line_ppp_annual` | DOUBLE |
| `poverty_headcount` | DOUBLE |
| `poverty_gap` | DOUBLE |
| `welfare_type` | TEXT |
| `source_priority` | TEXT |
| `harmonization_flag` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

## 14.3 `fiscal_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `tax_revenue_gdp` | DOUBLE |
| `total_revenue_gdp` | DOUBLE |
| `social_contrib_gdp` | DOUBLE |
| `direct_tax_gdp` | DOUBLE |
| `indirect_tax_gdp` | DOUBLE |
| `cit_gdp` | DOUBLE |
| `pit_gdp` | DOUBLE |
| `vat_gdp` | DOUBLE |
| `resource_revenue_gdp` | DOUBLE |
| `non_resource_revenue_gdp` | DOUBLE |
| `government_level` | TEXT |
| `source_priority` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

## 14.4 `debt_guardrail_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `gross_debt_gdp` | DOUBLE |
| `primary_balance_gdp` | DOUBLE |
| `nominal_interest_rate` | DOUBLE |
| `nominal_growth_rate` | DOUBLE |
| `pb_stabilizing_gdp` | DOUBLE |
| `pb_gap_gdp` | DOUBLE |
| `source_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

Guardrail posterior:

$$
PB_{i,p,s,r,t}\geq PB^{stab}_{i,t}
$$

## 14.5 `ai_preparedness_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `aipi_total` | DOUBLE |
| `digital_infrastructure` | DOUBLE |
| `human_capital_labor` | DOUBLE |
| `innovation_integration` | DOUBLE |
| `regulation_ethics` | DOUBLE |
| `aipi_convention` | TEXT |
| `source_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

## 14.6 `digital_gap_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `internet_use_rate` | DOUBLE |
| `broadband_rate` | DOUBLE |
| `mobile_broadband_rate` | DOUBLE |
| `digital_skills_proxy` | DOUBLE |
| `gap_index` | DOUBLE |
| `normalization_method` | TEXT |
| `gap_construction_convention` | TEXT |
| `aipi_overlap_flag` | BOOLEAN |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

Regla de exclusión Gap-vs-AIPI (obligatoria del paper): `Gap` debe construirse solo con indicadores EXCLUIDOS del AIPI. Internet, banda ancha y suscripciones móviles pertenecen al pilar de infraestructura digital del AIPI, de modo que no pueden entrar directo al `gap_index` baseline. Opciones admisibles: (a) identificar los indicadores exactos que componen el AIPI y usar solo indicadores excluidos (`gap_construction_convention = excluded_indicators`), que es el BASELINE; o (b) residualizar el índice contra el AIPI, `Gap_perp = Gap - Proj_A(Gap)`, solo como robustez (`gap_construction_convention = residualized`), estimando la proyección sobre la muestra internacional completa disponible del panel ITU/AIPI y nunca sobre los cuatro países del estudio. Si hay solapamiento sin residualizar, `aipi_overlap_flag = TRUE` y la variable no puede entrar al baseline.

## 14.7 `labor_informality_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `informality_total` | DOUBLE |
| `informality_labor_tax_base` | DOUBLE |
| `informality_consumption_tax_base` | DOUBLE |
| `informality_capital_tax_base` | DOUBLE |
| `almp_spending_gdp` | DOUBLE |
| `training_participation_rate` | DOUBLE |
| `rst_proxy` | DOUBLE |
| `definition` | TEXT |
| `source_id` | TEXT |
| `harmonization_flag` | TEXT |
| `non_harmonized_robustness` | BOOLEAN |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

Nota de nombre: esta tabla contiene las TRES informalidades por base gravable del paper (I^L laboral, I^F de firmas/capital, I^C de consumo) más los proxies de reskilling; el prefijo 'labor' es legado. No se separa en tres tablas ni se renombra en esta versión para no romper referencias; un rename a `informality_anchor` solo procede como refactor único al crear la base física.

## 14.8 `labor_share_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `labor_share_raw` | DOUBLE |
| `labor_share_adjusted` | DOUBLE |
| `source_id` | TEXT |
| `adjustment_notes` | TEXT |
| `year_original` | INTEGER |
| `carried_forward_flag` | BOOLEAN |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

## 14.9 `ai_exposure_anchor`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `exposure_total` | DOUBLE |
| `exposure_productive` | DOUBLE |
| `exposure_displacement` | DOUBLE |
| `exposure_source_type` | TEXT |
| `occupation_mapping_version` | TEXT |
| `is_lac_fallback` | BOOLEAN |
| `source_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

Regla de construcción por etapas: MVP = fallback regional LAC (evidencia World Bank–ILO: exposición productiva ~8-14% del empleo) con `is_lac_fallback = TRUE` obligatorio y el MISMO rango para los cuatro países. Paper-ready = intentar exposición país-específica por ocupación: crosswalk de exposición ocupacional (Felten / Webb / ILO) × la distribución ocupacional nacional — los microdatos de 13.6 traen `occupation_code` (ENAHO/CASEN/GEIH/ENIGH), que es el insumo exacto — como mínimo para PER y un comparador. Si no se logra exposición país-específica, el baseline mantiene el fallback y H2 se reporta como escenario condicional (matiz de la sección 5 del plan de diseño), nunca como test empírico entre países.

---


## 14.10 `frontier_benchmark_anchor`

El factor de traducción del paper, `T = min{1, S/S^frontier}`, requiere un benchmark EXTERNO de economías frontera. Sin esta tabla el plan de reproducción no puede computar `T`. La base solo cubre PER/CHL/COL/MEX, así que estos datos deben descargarse para economías benchmark adicionales.

| Campo | Tipo |
|---|---|
| `benchmark_set_id` | TEXT |
| `benchmark_country_id` | TEXT |
| `year` | INTEGER |
| `scenario_id` | TEXT |
| `aipi_total` | DOUBLE |
| `exposure_productive` | DOUBLE |
| `adoption_proxy` | DOUBLE |
| `s_frontier_score` | DOUBLE |
| `score_convention` | TEXT |
| `elasticities_used` | TEXT |
| `population_consistency_note` | TEXT |
| `source_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

Reglas obligatorias (consistencia poblacional del paper):

1. Las economías benchmark deben ser la MISMA población para la que se estimó el shock `phi_s` del escenario: si `phi_mid` es un promedio de economías avanzadas (OCDE), `S^frontier` se calibra sobre ese promedio, no sobre el mejor país individual.
2. Usar un benchmark más estricto que la población de estimación descuenta la adopción dos veces; solo se permite como cuña conservadora etiquetada.
3. `S^frontier` queda FIJO dentro de cada inversión de umbral; no se recalcula con la celda invertida.
4. El set de economías benchmark y el año de referencia se documentan en `dim_source` y `variable_source_map`.
5. El score frontier se computa con la MISMA fórmula y elasticidades que el score del país: `S^NDC` baseline sin AIPI (`alpha=0`; `score_convention=NDC_baseline`, `elasticities_used` registra beta y gamma). Un frontier computado con AIPI (`full_score_robustness`) solo alimenta la robustez full-score y nunca se compara contra scores país sin AIPI.

# 15. Definición exacta de captura fiscal histórica

Este punto debe quedar perfectamente definido porque el modelo compara `MFCgross` con percentiles históricos.

## 15.1 Definición principal recomendada

Usar como métrica principal:

$$
MFC^{hist,gross}_{i,t}=\frac{\Delta Revenue_{i,t}}{\Delta GDP_{i,t}}
$$

Donde:

$$
\Delta Revenue_{i,t}=Revenue_{i,t}-Revenue_{i,t-1}
$$

$$
\Delta GDP_{i,t}=GDP_{i,t}-GDP_{i,t-1}
$$

Ambas magnitudes deben estar en la misma unidad monetaria y base nominal.

Recomendación práctica:

> Usar moneda local corriente para la definición principal, porque los ingresos fiscales y el PIB presupuestario se expresan fiscalmente en términos nominales.

## 15.2 Variantes obligatorias

Crear variantes separadas:

| Variable | Definición | Uso |
|---|---|---|
| `mfc_tax_hist_gross` | Δ tax revenue / Δ GDP | Captura tributaria estricta. |
| `mfc_total_revenue_hist_gross` | Δ total revenue / Δ GDP | Captura fiscal amplia. |
| `mfc_nonresource_hist_gross` | Δ non-resource revenue / Δ GDP | Robustez sin recursos naturales. |
| `mfc_smoothed_3y` | Promedio móvil 3 años | Robustez contra ruido anual. |
| `buoyancy_hist` | Δln revenue / Δln GDP (diferencias logarítmicas, como en el paper) | Comparador de elasticidad, no métrica principal. |

## 15.3 Reglas de limpieza

- Usar un solo nivel de gobierno por país-ventana (`government_level`): OECD Revenue Statistics LAC reporta gobierno general, mientras las series de SUNAT/SII/DIAN/SAT suelen ser gobierno central; no mezclar niveles dentro de la serie histórica de un mismo país.
- Ventana histórica preferida: 2000-último año disponible; ventanas de robustez: 2010- y 2015-; reportar percentiles con y sin años pandemia 2020-2021.
- Excluir o marcar años con `delta_gdp <= 0`.
- Marcar años de crisis macro/fiscal.
- Marcar shocks de commodities cuando afecten ingresos de recursos.
- Winsorizar los ratios crudos en P1/P99 o reportar medianas robustas en el BASELINE (regla de limpieza del paper contra artefactos de denominador), reportando siempre también la distribución raw sin winsorizar.
- Calcular percentiles por país.
- Si hay pocos años, calcular también percentiles regionales, pero etiquetarlos como soporte adicional.

## 15.4 `historical_capture_distribution`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `year` | INTEGER |
| `revenue_concept` | TEXT |
| `revenue_lcu` | DOUBLE |
| `gdp_lcu` | DOUBLE |
| `delta_revenue_lcu` | DOUBLE |
| `delta_gdp_lcu` | DOUBLE |
| `mfc_hist_gross` | DOUBLE |
| `mfc_tax_hist_gross` | DOUBLE |
| `mfc_total_revenue_hist_gross` | DOUBLE |
| `mfc_nonresource_hist_gross` | DOUBLE |
| `mfc_smoothed_3y` | DOUBLE |
| `buoyancy_hist` | DOUBLE |
| `is_non_negative_capture` | BOOLEAN |
| `delta_gdp_positive` | BOOLEAN |
| `crisis_year_flag` | BOOLEAN |
| `commodity_shock_flag` | BOOLEAN |
| `pandemic_flag` | BOOLEAN |
| `government_level` | TEXT |
| `source_mix` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |
| `created_by_script` | TEXT |

## 15.5 `historical_capture_percentiles`

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `government_level` | TEXT |
| `revenue_concept` | TEXT |
| `percentile_sample` | TEXT |
| `p10_mfc_hist_positive` | DOUBLE |
| `p25_mfc_hist_positive` | DOUBLE |
| `p50_mfc_hist_positive` | DOUBLE |
| `p50_ci_low` | DOUBLE |
| `p50_ci_high` | DOUBLE |
| `p75_mfc_hist_positive` | DOUBLE |
| `p75_ci_low` | DOUBLE |
| `p75_ci_high` | DOUBLE |
| `p90_mfc_hist_positive` | DOUBLE |
| `p90_ci_low` | DOUBLE |
| `p90_ci_high` | DOUBLE |
| `ci_method` | TEXT (bootstrap percentil, B=2000, seed declarada) |
| `n_years_total` | INTEGER |
| `n_years_positive` | INTEGER |
| `p_negative_capture` | DOUBLE |
| `p10_mfc_hist_negative` | DOUBLE |
| `p50_mfc_hist_negative` | DOUBLE |
| `p90_mfc_hist_negative` | DOUBLE |
| `support_warning` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |

con ~20-24 observaciones por ventana, P75/P90 tienen error muestral material; los CI se reportan siempre y alimentan el flag de frontera del plan de diseño.

---


Nota: El campo `percentile_sample` codifica ventana y variante: `2000plus` / `2010plus` / `2015plus` / `excl_pandemic_2020_2021`.

`p_negative_capture` = proporción de años con captura negativa (el p^- de la mezcla incondicional del plan de diseño); los percentiles negativos caracterizan el componente `MFC_hist_gross_negative` del que sortea la mezcla.

# 16. Costos de política como insumo construido

Changelog Etapa 4B.2: `government_level` se documenta como extensión legítima de `historical_capture_percentiles` para trazar el contraste GRD y la decisión central/general. No reemplaza los campos canónicos de 15.5 ni cambia el vocabulario de `revenue_concept` o `percentile_sample`.

## `policy_cost`

Esta tabla pertenece al plan de base si se calcula como costo normativo con parámetros documentados. Si luego se recalcula dentro de sensibilidad o Monte Carlo, debe existir también una versión con `run_id`.

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `year` | INTEGER |
| `eligible_population` | DOUBLE |
| `benefit_amount_lcu` | DOUBLE |
| `poverty_line_annual_lcu` | DOUBLE |
| `eta_policy` | DOUBLE |
| `chi_gmi` | DOUBLE |
| `policy_cost_gross_lcu` | DOUBLE |
| `existing_spending_lcu` | DOUBLE |
| `policy_cost_net_lcu` | DOUBLE |
| `policy_cost_gross_gdp` | DOUBLE |
| `policy_cost_net_gdp` | DOUBLE |
| `cost_convention` | TEXT |
| `microdata_used` | BOOLEAN |
| `gmi_version` | TEXT |
| `policy_parameter_id` | TEXT |
| `assumption_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |
| `run_id` | TEXT, nullable |
| `model_version` | TEXT, nullable |
| `parameter_set_id` | TEXT, nullable |

Regla:

> En la fase de base, `run_id` puede quedar NULL. En la fase de reproducción, cualquier recalibración de costos debe llenar `run_id`, `model_version` y `parameter_set_id`.

---


## 16.1 `policy_admin_transition_cost`

Insumo requerido por el espacio fiscal efectivo del paper (`fs_eff` resta costos administrativos netos, transición anualizada y leakage fijo). Sin esta tabla la reproducción no puede computar `fs_eff`.

| Campo | Tipo |
|---|---|
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT (NULL = todos) |
| `regime_id` | INTEGER (NULL = todos) |
| `year` | INTEGER |
| `admin_cost_new_gdp` | DOUBLE |
| `admin_savings_existing_gdp` | DOUBLE |
| `admin_included_in_existing_spending` | BOOLEAN |
| `layering_mode` | TEXT |
| `transition_oneoff_gdp` | DOUBLE |
| `transition_recurring_gdp` | DOUBLE |
| `transition_horizon_years` | INTEGER |
| `transition_discount_rate` | DOUBLE |
| `leakage_fixed_gdp` | DOUBLE |
| `source_id` | TEXT |
| `assumption_id` | TEXT |
| `dataset_version` | TEXT |
| `build_id` | TEXT |
| `created_by_script` | TEXT |

`ac`, `tr` y `leak` llevan índices (s, r) en el modelo (7.5 del plan de diseño): los regímenes r1-r4 tienen costos de implementación y transición distintos. Regla de resolución: el más específico gana (espejo de `parameter_set_item`).

Reglas del paper:

1. Si `C^exist` ya incluye el gasto administrativo del programa reemplazado, `admin_savings_existing_gdp = 0` (anti doble conteo).
2. Si `layering_mode = pure_layering` (el instrumento se añade sin terminar programas existentes), `admin_savings_existing_gdp = 0`.
3. Costos administrativos por beneficiario ordenados: means-tested > categórico > universal. Prohibido aplicar un ratio administrativo uniforme entre instrumentos (compondría el sesgo de focalización ideal del GMI).
4. Fuentes: ASPIRE (conceptos de gasto administrativo) y presupuestos nacionales; lo no observable entra en `assumption_registry` con soporte declarado.
5. Los costos one-off se anualizan con el factor de anualidad `a(H_tr, r_tr)` en la fase de reproducción; esta tabla solo guarda los insumos.

# 17. Trazabilidad por variable procesada

`dim_source` no basta. Se necesita saber qué fuente alimentó cada variable final.

## `variable_source_map`

| Campo | Tipo | Descripción |
|---|---|---|
| `table_name` | TEXT | Tabla final. |
| `variable_name` | TEXT | Variable final. |
| `country_id` | TEXT | País. |
| `year` | INTEGER | Año. |
| `source_id` | TEXT | Fuente usada. |
| `raw_table` | TEXT | Tabla raw de origen. |
| `raw_indicator_code` | TEXT | Código original. |
| `raw_variable_name` | TEXT | Nombre original. |
| `transformation_script` | TEXT | Script que creó la variable. |
| `transformation_notes` | TEXT | Transformación aplicada. |
| `harmonization_flag` | TEXT | observed_2024 / carried_forward / interpolated / robustness. |
| `priority_rank` | INTEGER | Fuente primaria/secundaria. |
| `source_conflict_flag` | BOOLEAN | TRUE si hubo discrepancia entre fuentes. |
| `dataset_version` | TEXT | Versión de base. |
| `build_id` | TEXT | ID de construcción. |

Ejemplo de uso:

| Variable | Registro esperado |
|---|---|
| `tax_revenue_gdp` Perú 2024 | OECD si es fuente primaria; GRD como contraste. |
| `informality_total` Colombia 2024 | DANE/GEIH, SEDLAC o ILOSTAT; 2026 solo robustez. |
| `poverty_gap` México 2024 | PIP/SEDLAC/fuente nacional según disponibilidad. |
| `aipi_total` Chile | IMF AIPI publicado, no reconstruido si el baseline usa publicado. |

---

# 18. Reporte de calidad y missingness

## `data_quality_report`

Tabla obligatoria para mezclar fuentes internacionales y nacionales sin perder control.

| Campo | Tipo | Descripción |
|---|---|---|
| `country_id` | TEXT | País. |
| `year` | INTEGER | Año. |
| `module` | TEXT | macro / fiscal / poverty / informality / ai / policy_cost / etc. |
| `table_name` | TEXT | Tabla afectada. |
| `variable_name` | TEXT | Variable evaluada. |
| `missing_flag` | BOOLEAN | TRUE si falta. |
| `imputed_flag` | BOOLEAN | TRUE si fue imputada. |
| `carried_forward_flag` | BOOLEAN | TRUE si se arrastró de año previo. |
| `carried_forward_from_year` | INTEGER | Año original. |
| `interpolated_flag` | BOOLEAN | TRUE si se interpoló. |
| `source_conflict_flag` | BOOLEAN | TRUE si fuentes no coinciden. |
| `unit_conflict_flag` | BOOLEAN | TRUE si hay conflicto de unidad. |
| `definition_conflict_flag` | BOOLEAN | TRUE si hay conflicto de definición. |
| `non_harmonized_robustness` | BOOLEAN | TRUE si se usa fuera del baseline temporal. |
| `quality_score` | DOUBLE | 0 a 1. |
| `notes` | TEXT | Comentario. |
| `dataset_version` | TEXT | Versión de base. |
| `build_id` | TEXT | ID de construcción. |

Regla:

> Ninguna variable final debe entrar al modelo sin un registro mínimo en `variable_source_map` y `data_quality_report`.

---

# 19. Registro de supuestos y sets de parámetros

## 19.1 `assumption_registry`

| Campo | Tipo |
|---|---|
| `assumption_id` | TEXT |
| `module` | TEXT |
| `parameter_name` | TEXT |
| `baseline_value` | DOUBLE |
| `low_value` | DOUBLE |
| `high_value` | DOUBLE |
| `distribution` | TEXT |
| `justification` | TEXT |
| `source_id` | TEXT |
| `is_observed` | BOOLEAN |
| `is_scenario` | BOOLEAN |
| `is_structural_unobserved` | BOOLEAN |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

## 19.2 `parameter_set`

| Campo | Tipo | Descripción |
|---|---|---|
| `parameter_set_id` | TEXT | ID del set. |
| `parameter_set_name` | TEXT | baseline / conservative / optimistic / stress. |
| `description` | TEXT | Descripción. |
| `model_version` | TEXT | Versión del modelo para la que fue creado. |
| `dataset_version` | TEXT | Versión de base compatible. |
| `created_at` | TIMESTAMP | Fecha. |
| `created_by_script` | TEXT | Script. |

## 19.3 `parameter_set_item`

| Campo | Tipo |
|---|---|
| `parameter_set_id` | TEXT |
| `assumption_id` | TEXT |
| `parameter_name` | TEXT |
| `country_id` | TEXT (NULL = todos) |
| `policy_id` | TEXT (NULL = todas) |
| `scenario_id` | TEXT (NULL = todos) |
| `regime_id` | INTEGER (NULL = todos) |
| `parameter_value` | DOUBLE |
| `distribution` | TEXT |
| `draw_rule` | TEXT |
| `notes` | TEXT |

Regla de resolución de ámbito: el valor más específico gana (celda > país > global); está prohibido que dos filas del mismo `parameter_set_id` y `parameter_name` resuelvan ambiguamente a la misma celda — test de unicidad en Fase 4.

---

# 20. Tablas preparadas para reproducción posterior

Estas tablas pueden definirse en el diccionario de datos, pero no se generan en la fase de construcción base salvo como placeholders vacíos o interfaces.

Regla de canonicidad: los esquemas de las secciones 20-22 son interfaces indicativas. El esquema CANÓNICO de las tablas de corrida es el del plan de diseño (`02_ESD_AI_USP_v6.md`, sección 19), que añade `requirement_basis`, `horizon_H`, `static_or_accumulated` y `mc_mode`, y usa `v_gross`, `cell_result_class` y `mc_n_draws`, renombra `year` a `endpoint_year` y añade `anchor_year`/`endpoint_year` a `run_manifest` y `prob_basis` a `monte_carlo_result`, junto con las familias `failure_severity_mean_*` (medida principal) y el campo `xi` en `threshold_inversion_result`. En caso de conflicto, gobierna el plan de diseño. Las tablas de gobernanza pre-run (`value_assignment_table`, `threshold_assignment_table`, `threshold_rule_registry`, `input_audit_report`) tienen esquema canónico en el plan de diseño, sección 19.7; este plan no las define.

## 20.1 `adoption_module`

Depende de parámetros de adopción y escenarios. Por eso debe llevar trazabilidad de corrida si se genera.

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `scenario_id` | TEXT |
| `year` | INTEGER |
| `aipi_total` | DOUBLE |
| `informality` | DOUBLE |
| `gap_index` | DOUBLE |
| `q_bar` | DOUBLE |
| `q_use_target` | DOUBLE |
| `q_use` | DOUBLE |
| `q_prod_lagged` | DOUBLE |
| `q_prod` | DOUBLE |
| `lambda_q` | DOUBLE |
| `mu` | DOUBLE |
| `nu_a` | DOUBLE |
| `nu_i` | DOUBLE |
| `nu_gap` | DOUBLE |
| `adoption_flag` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

## 20.2 `fiscal_conversion_module`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `year` | INTEGER |
| `omega_labor` | DOUBLE |
| `omega_capital` | DOUBLE |
| `omega_consumption` | DOUBLE |
| `lambda_ai_rent` | DOUBLE |
| `tau_labor_eff` | DOUBLE |
| `tau_capital_eff` | DOUBLE |
| `tau_consumption_eff` | DOUBLE |
| `tau_ai_eff` | DOUBLE |
| `mfc_gross` | DOUBLE |
| `admin_cost_me` | DOUBLE |
| `transition_cost_me` | DOUBLE |
| `leakage_me` | DOUBLE |
| `mfc_eff` | DOUBLE |
| `fixed_cost_gdp` | DOUBLE |
| `regime_convention` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

## 20.3 `fiscal_space_result`

Resultado del modelo. No pertenece al armado básico de datos, pero debe estar definido para el plan de reproducción.

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `year` | INTEGER |
| `g_ai_level` | DOUBLE |
| `mfc_gross` | DOUBLE |
| `mfc_eff` | DOUBLE |
| `fixed_cost_gdp` | DOUBLE |
| `fs_gross` | DOUBLE |
| `fs_eff` | DOUBLE |
| `cost_gdp` | DOUBLE |
| `v_index` | DOUBLE |
| `crosses_v1` | BOOLEAN |
| `buffer_xi` | DOUBLE |
| `crosses_buffer` | BOOLEAN |
| `fiscal_plausibility_flag` | TEXT |
| `debt_guardrail_pass` | BOOLEAN |
| `result_class` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

Clasificación sugerida para reproducción posterior:

| Condición | Clase |
|---|---|
| `V < 1` | not_feasible |
| `V >= 1` y `MFCgross <= P50` | fiscally_ordinary |
| `V >= 1` y `P50 < MFCgross <= P75` | fiscally_moderate |
| `V >= 1` y `P75 < MFCgross <= P90` | fiscally_demanding |
| `MFCgross > P90` | extreme_or_outside_historical_support |
| Violación hard gate | impossible |

---

# 21. Monte Carlo: diseño correcto de tablas

La tabla `monte_carlo_draw` no debe mezclar variables globales, país-específicas y política-específicas sin llaves claras.

## 21.1 Opción recomendada: tablas separadas

### `global_scenario_draw`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `draw_id` | BIGINT |
| `seed` | INTEGER |
| `scenario_id` | TEXT |
| `year` | INTEGER |
| `phi_raw` | DOUBLE |
| `kappa_to_y` | DOUBLE |
| `pi_ai_y` | DOUBLE |
| `phi_y_real` | DOUBLE |
| `phi_y_nominal` | DOUBLE |

### `country_scenario_draw`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `parameter_set_id` | TEXT |
| `draw_id` | BIGINT |
| `country_id` | TEXT |
| `scenario_id` | TEXT |
| `year` | INTEGER |
| `q_prod` | DOUBLE |
| `q_use` | DOUBLE |
| `translation_factor` | DOUBLE |
| `g_ai_level` | DOUBLE |
| `informality_adjustment` | DOUBLE |

### `policy_cost_draw`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `parameter_set_id` | TEXT |
| `draw_id` | BIGINT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `year` | INTEGER |
| `benefit_amount_lcu` | DOUBLE |
| `eligible_population` | DOUBLE |
| `policy_cost_gross_gdp` | DOUBLE |
| `gross_or_net_convention` | TEXT |

### `fiscal_conversion_draw`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `parameter_set_id` | TEXT |
| `draw_id` | BIGINT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `year` | INTEGER |
| `mfc_gross` | DOUBLE |
| `mfc_tilde_gross` | DOUBLE |
| `mfc_eff` | DOUBLE |
| `admin_cost` | DOUBLE |
| `leakage` | DOUBLE |
| `transition_cost` | DOUBLE |

`admin_cost`, `leakage` y `transition_cost` son específicos de cada política (`ac_net_fix`, `tr_ann`); `mfc_gross` y `mfc_tilde_gross` NO dependen de la política; `mfc_eff` SÍ depende de la política (paper, eq. mfc_eff: `MFC_eff_{i,p,s,r,t} = fs_eff_{i,p,s,r,t} / g_AI_{i,s,t}`, porque `fs_eff` resta costos fijos específicos de la política). `mfc_eff` es objeto de REPORTE derivado: nunca se sortea independientemente ni se restan los mismos costos dentro de `mfc_eff` y de `fs_eff` a la vez (regla del paper); en simulación el objeto primario es `fs_eff`.

### `draw_parameter_value`

Tabla larga que persiste TODOS los primitivos sorteados de cada draw, para reproducibilidad paper-ready y auditoría; las tablas de draws anteriores guardan derivados por conveniencia.

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `parameter_set_id` | TEXT |
| `draw_id` | BIGINT |
| `country_id` | TEXT, nullable (NULL para primitivos globales) |
| `scenario_id` | TEXT, nullable |
| `policy_id` | TEXT, nullable (NULL si el primitivo no es policy-específico; p.ej. `theta_target`, costos admin lo son) |
| `regime_id` | INTEGER, nullable (NULL si no aplica; p.ej. `tau_r`, `epsilon_ero` son regime-específicos) |
| `parameter_name` | TEXT |
| `value` | DOUBLE |
| `block` | TEXT (shock / adopcion / canales / costos / GMI) |

### `monte_carlo_result`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `year` | INTEGER |
| `n_draws` | INTEGER |
| `prob_basis` | TEXT |
| `v_p05` | DOUBLE |
| `v_p25` | DOUBLE |
| `v_p50` | DOUBLE |
| `v_p75` | DOUBLE |
| `v_p95` | DOUBLE |
| `prob_v_ge_1` | DOUBLE |
| `prob_v_ge_1_00` | DOUBLE |
| `prob_v_ge_1_05` | DOUBLE |
| `prob_v_ge_1_10` | DOUBLE |
| `prob_v_ge_1_25` | DOUBLE |
| `prob_v_ge_1_50` | DOUBLE |
| `prob_debt_consistent_1_00` | DOUBLE |
| `prob_debt_consistent_1_05` | DOUBLE |
| `prob_debt_consistent_1_10` | DOUBLE |
| `prob_debt_consistent_1_25` | DOUBLE |
| `prob_debt_consistent_1_50` | DOUBLE |
| `failure_severity_mean_1_00` | DOUBLE |
| `failure_severity_mean_1_05` | DOUBLE |
| `failure_severity_mean_1_10` | DOUBLE |
| `failure_severity_mean_1_25` | DOUBLE |
| `failure_severity_mean_1_50` | DOUBLE |
| `failure_severity_median_1_00` | DOUBLE |
| `failure_severity_median_1_05` | DOUBLE |
| `failure_severity_median_1_10` | DOUBLE |
| `failure_severity_median_1_25` | DOUBLE |
| `failure_severity_median_1_50` | DOUBLE |
| `valid_support_share` | DOUBLE |
| `threshold_computability_share` | DOUBLE |
| `requirement_already_covered_share` | DOUBLE |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

Nota: `prob_v_ge_1` se conserva solo como alias de `prob_v_ge_1_00`; las columnas debt-consistent y failure-severity usan la misma grilla congelada de xi que las probabilidades de cruce.

## 21.2 Opción simple alternativa

Si se mantiene una sola tabla `monte_carlo_draw`, debe tener como mínimo:

| Campo obligatorio | Motivo |
|---|---|
| `country_id` | `q_prod`, informalidad y traducción IA son país-específicas. |
| `policy_id` | `policy_cost_gdp` cambia por política. |
| `year` | Los costos y anclajes cambian por año. |
| `scenario_id` | Shock IA. |
| `regime_id` | Conversión fiscal. |
| `draw_id` | Identificador del sorteo. |
| `parameter_set_id` | Set de supuestos. |
| `run_id` | Corrida reproducible. |
| `model_version` | Versión de modelo. |

Recomendación:

> Para el paper-ready package, usar tablas separadas. Para un prototipo rápido, una sola tabla es aceptable solo si incluye país, política y año.

---

# 22. Diagnósticos y threshold inversion: solo esquema posterior

Estas tablas son de reproducción, no de construcción básica.

## 22.1 `diagnostic_result`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `diagnostic_id` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `diagnostic_type` | TEXT |
| `baseline_v` | DOUBLE |
| `diagnostic_v` | DOUBLE |
| `rank_change` | DOUBLE |
| `passes_diagnostic` | BOOLEAN |
| `notes` | TEXT |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

Diagnósticos posteriores:

1. Temporal placebo mecánico.
2. Placebo ICT pre-GenAI.
3. Negative control sectorial.
4. Leave-one-source-out.
5. Channel ablation.
6. Robustez con/sin recycling de transferencias.
7. Robustez gross vs net cost.
8. Robustez real vs nominal bridge.

## 22.2 `threshold_inversion_result`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `xi` | DOUBLE |
| `year` | INTEGER |
| `required_revenue_gdp` | DOUBLE |
| `g_ai_required` | DOUBLE |
| `mfc_required_gross` | DOUBLE |
| `t_required_H` | DOUBLE (T^{req,H} de 7.7; la versión estática solo en corridas one_period_static) |
| `tau_ai_required` | DOUBLE |
| `q_prod_required` | DOUBLE |
| `q_use_required` | DOUBLE |
| `aipi_required` | DOUBLE |
| `exposure_required` | DOUBLE |
| `existence_condition_pass` | BOOLEAN |
| `impossibility_reason` | TEXT |
| `floor_driven_flag` | BOOLEAN |
| `epsilon_used` | DOUBLE |
| `created_at` | TIMESTAMP |
| `created_by_script` | TEXT |

---

# 23. Núcleo mínimo de construcción inicial

El plan completo es fuerte, pero no conviene intentar todo a la vez.

## 23.1 MVP de ingesta (no ejecutable)

Primero construir:

1. `dim_country`
2. `dim_policy`
3. `dim_ai_scenario`
4. `dim_fiscal_regime`
5. `dim_source`
6. `macro_anchor`
7. `fiscal_anchor`
8. `poverty_distribution_anchor`
9. `ai_preparedness_anchor`
10. `labor_informality_anchor`
11. `policy_parameter`
12. `policy_cost`
13. `historical_capture_distribution`
14. `historical_capture_percentiles`
15. `assumption_registry`
16. `parameter_set`
17. `variable_source_map`
18. `data_quality_report`
19. `policy_admin_transition_cost`
20. `frontier_benchmark_anchor`
21. `seed_paper_values`

No incluir todavía en el MVP base:

- `fiscal_space_result`;
- `monte_carlo_result`;
- `diagnostic_result`;
- `threshold_inversion_result`.

Esas tablas se definen como interfaz para el plan de reproducción.

## 23.2 Segunda fase de base ampliada

Agregar después:

1. `debt_guardrail_anchor`
2. `labor_share_anchor`
3. `digital_gap_anchor`
4. `ai_exposure_anchor`
5. `gmi_estimation_status`
6. microdatos para GMI fuerte;
7. exposición IA por ocupación;
8. informalidad por sector/base fiscal.

MVP EJECUTABLE: el baseline primario channel-based del plan de diseño NO puede correrse con el MVP de ingesta; requiere además los ítems 1-4 de esta lista (`debt_guardrail_anchor`, `labor_share_anchor`, `digital_gap_anchor`, `ai_exposure_anchor`). MVP ejecutable = 23.1 + esos cuatro anchors. Los ítems 6-8 (microdatos GMI fuerte, exposición por ocupación, informalidad por sector) solo son necesarios para el GMI microdata-strong y las desagregaciones, no para el baseline primario.

Orden real de arranque (obligatorio, sin saltos): (1) construir el MVP de ingesta (23.1); (2) añadir los cuatro anchors del MVP ejecutable (`debt_guardrail_anchor`, `labor_share_anchor`, `digital_gap_anchor`, `ai_exposure_anchor`); (3) correr la Fase 0 del plan de diseño (input audit + double_counting_audit + tablas de gobernanza 19.7) hasta `run_readiness_flag = TRUE`; (4) recién entonces el baseline determinístico (Fase 2). El Monte Carlo (Fase 6) queda bloqueado por los gates de las Fases 1-5 del roadmap 12.1: saltar directo al MC viola el diseño.

Corte vertical piloto (recomendado): los pasos (1)-(4) se ejecutan primero para UN solo país — `PER` — de punta a punta, y recién entonces se escala a `CHL`/`COL`/`MEX`. Racional: los conflictos de armonización (fuentes discrepantes, `government_level` central vs general, carried-forwards, unidades) se depuran a tamaño 1 con el pipeline completo funcionando, en vez de aparecer multiplicados por cuatro. Reglas del piloto: (a) los scripts de ingesta se escriben parametrizados por país desde el inicio (`--countries PER,CHL,COL,MEX`), de modo que el piloto no requiere código aparte — solo una lista más corta; (b) el snapshot del piloto se etiqueta como versión piloto (p.ej. `dataset_version = v0.1.0-pilot-per`) y el snapshot oficial de 4 países es una versión NUEVA completa; (c) toda corrida del piloto lleva `run_label = pilot` y sus outputs NO entran al paper ni a las tablas de referencia; (d) el piloto NO autoriza cambios de especificación: la especificación primaria ya está congelada (hash de pre-registro) y cualquier cambio posterior al piloto queda expuesto como mismatch del `PRIMARY_SPEC_HASH`. `PER` es el país piloto por acceso a fuentes (INEI/ENAHO de descarga abierta, SUNAT) y por coherencia con la regla de exposición por etapas de 14.9, que ya prioriza a `PER`. (e) El filtro por país aplica SOLO a los países de estudio: el set de economías benchmark del frontier (14.10) y los insumos globales de escenario (`phi_raw`, bridges, `pi_AI_Y`) se descargan SIEMPRE completos, también en el piloto — sin el benchmark externo no se puede computar `T` ni correr la Fase 2. (f) La Fase 0 del plan de diseño acepta el subconjunto piloto declarado (nota de corrida piloto en su sección 12.2), pero ese `run_readiness_flag` no habilita el baseline oficial de cuatro países.

## 23.3 Fase de reproducción posterior

Recién después construir/llenar:

1. `adoption_module`
2. `fiscal_conversion_module`
3. `global_scenario_draw`
4. `country_scenario_draw`
5. `policy_cost_draw`
6. `fiscal_conversion_draw`
7. `fiscal_space_result`
8. `monte_carlo_result`
9. `diagnostic_result`
10. `threshold_inversion_result`

---

# 24. Pipeline de construcción de la base

## Fase 0 — Congelar alcance y convenciones

Entregables:

- `country_list.csv`: PER, CHL, COL, MEX.
- `policy_list.csv`: PEN, MUT, GMI, PBI, UBI.
- `scenario_ladder.csv`: low, mid, high, stress (label del stress: Disruptive stress).
- `fiscal_regime_list.csv`: r0-r4.
- `data_conventions.yml`: unidades, años, moneda, denominador, costos gross/net.
- `dataset_version.yml`: versión de la base.

Decisiones fijas:

1. Baseline usa denominador `Y0`, PIB sin IA.
2. Costos de política se expresan anualizados.
3. Beneficios y líneas de pobreza deben estar en la misma frecuencia anual.
4. `UBI` se reporta como stress benchmark.
5. `GMI` tiene versión agregada y versión microdata.
6. `MFC_hist_gross` usa definición ΔRevenue/ΔGDP en moneda local corriente como baseline.

## Fase 1 — Descargar raw data pública

Rango temporal: 2000-2024 mínimo para todas las series país-año.

Prioridad alta:

1. WDI: macro, población, precios, exchange rate.
2. OECD Revenue Statistics / GRD: fiscal.
3. IMF WEO: deuda y balance primario.
4. AIPI: preparación IA.
5. ILOSTAT / fuentes nacionales: informalidad y empleo.
6. PWT: labor share.
7. PIP / SEDLAC: pobreza.
8. ASPIRE: gasto social existente.

Prioridad media:

1. ITU / WDI digital indicators.
2. Encuestas TIC nacionales.
3. Occupational employment para exposición IA.
4. Microdatos hogares.

## Fase 2 — Limpieza y armonización

Reglas:

- Convertir todo a formato largo.
- Mantener moneda local y USD separados.
- Crear `unit`, `frequency`, `price_basis`, `source_id` para cada variable.
- No sobrescribir raw data.
- Toda interpolación debe guardar `imputation_method`.
- Toda variable arrastrada debe guardar `carried_forward_from_year`.
- Toda variable final debe registrarse en `variable_source_map`.
- Todo problema de calidad debe registrarse en `data_quality_report`.

## Fase 3 — Construir anclas procesadas

Orden:

1. `macro_anchor`
2. `poverty_distribution_anchor`
3. `fiscal_anchor`
4. `labor_informality_anchor`
5. `ai_preparedness_anchor`
6. `policy_parameter`
7. `policy_cost`
8. `historical_capture_distribution`
9. `historical_capture_percentiles`
10. `policy_admin_transition_cost`
11. `frontier_benchmark_anchor`
12. `seed_paper_values`
13. `variable_source_map`
14. `data_quality_report`

## Fase 4 — Validar base

Validaciones mínimas:

- Países cubiertos: exactamente PER, CHL, COL, MEX.
- Año base: 2024 o flags correctos.
- No hay unidades mezcladas.
- `policy_cost` tiene `policy_parameter_id` o `assumption_id`.
- `MFC_hist_gross` usa ΔRevenue/ΔGDP y marca años inválidos.
- `GMI` indica si es agregado o microdata.
- Colombia 2026 no entra al baseline sin flag de robustez.
- Cada variable final tiene fuente y script.
- Cada missing/imputación tiene reporte.
- Cada serie fiscal histórica usa un solo `government_level` por país.
- Las anclas construidas se comparan contra `seed_paper_values`; toda desviación relevante se reporta con tolerancia declarada y explicación.

## Fase 5 — Exportar insumos para reproducción

Exportar a `data/model_inputs/`:

- `country_panel.parquet`
- `policy_cost.parquet`
- `historical_capture_percentiles.parquet`
- `policy_admin_transition_cost.parquet`
- `frontier_benchmark_anchor.parquet`
- `policy_parameter.parquet`
- `assumption_registry.parquet`
- `parameter_set.parquet`
- `data_quality_report.parquet`

No exportar resultados del modelo en esta fase.

---

# 25. Reglas de calidad de datos

## 25.1 No mezclar unidades

Cada variable final debe tener o estar trazada a:

- `unit`
- `currency`
- `price_basis`
- `frequency`
- `source_id`
- `year_original`
- `year_harmonized`

## 25.2 No doble conteo

Reglas duras:

1. No meter informalidad dos veces en adopción y captura fiscal sin etiquetar la convención.
2. No meter profit shifting base-side y rate-side simultáneamente.
3. No usar AIPI dentro de `qprod` y luego volver a multiplicar por AIPI en el score completo, salvo robustez etiquetada.
4. No usar PIB post-IA como denominador baseline si el paper usa `Y0`.
5. No meter shocks TFP/LP crudos directamente en ecuaciones fiscales.
6. No incluir pensiones contributivas ni beneficios con derechos adquiridos en `C^exist` ni en ningún netting-out de costos.

## 25.3 Raw data nunca se edita

Todo cambio va en:

- `interim/`
- `processed/`
- tablas derivadas de DuckDB.

## 25.4 Fuentes contradictorias

Si dos fuentes difieren:

1. No promediar automáticamente.
2. Elegir una fuente primaria por variable.
3. Guardar la fuente secundaria como contraste.
4. Activar `source_conflict_flag=TRUE`.
5. Explicar decisión en `transformation_notes`.

---

# 26. Checklist operativo actualizado

## 26.1 Checklist de configuración

- [ ] Crear `dataset_version`.
- [ ] Crear `build_id`.
- [ ] Definir países: PER, CHL, COL, MEX.
- [ ] Definir año base: 2024.
- [ ] Definir políticas: PEN, MUT, GMI, PBI, UBI.
- [ ] Definir regímenes fiscales r0-r4 como dimensiones, no ejecución.
- [ ] Definir escenarios IA como dimensiones, no ejecución.
- [ ] Crear `data_conventions.yml`.

## 26.2 Checklist de descarga

- [ ] WDI macro para PER/CHL/COL/MEX.
- [ ] PIP pobreza y poverty gap.
- [ ] SEDLAC pobreza/distribución/informalidad.
- [ ] OECD Revenue Statistics.
- [ ] GRD revenue.
- [ ] IMF WEO deuda y balance primario.
- [ ] IMF AIPI.
- [ ] IMF AIPI descargado para TODOS los países (benchmark frontier), no solo el piloto.
- [ ] ILOSTAT empleo/informalidad/ocupación.
- [ ] PWT labor share.
- [ ] ASPIRE social protection.
- [ ] Fuentes nacionales de pobreza, informalidad y presupuesto.
- [ ] Microdatos ENAHO/CASEN/GEIH-ENCV/ENIGH para GMI paper-ready.
- [ ] Encuestas TIC/firmas para el momento ancla de adopción (`q_use_target`).
- [ ] Informes nacionales de gasto tributario (exenciones IVA).
- [ ] UN WPP proyecciones de población 2024-2035 (variante media, total y 65+).

## 26.3 Checklist de construcción base

- [ ] Crear dimensiones.
- [ ] Crear raw tables.
- [ ] Crear `macro_anchor`.
- [ ] Crear `fiscal_anchor`.
- [ ] Crear `poverty_distribution_anchor`.
- [ ] Crear `ai_preparedness_anchor`.
- [ ] Crear `labor_informality_anchor`.
- [ ] Crear `policy_parameter`.
- [ ] Crear `policy_cost`.
- [ ] Crear `historical_capture_distribution`.
- [ ] Crear `historical_capture_percentiles`.
- [ ] Crear `assumption_registry`.
- [ ] Crear `parameter_set`.
- [ ] Crear `seed_paper_values`.
- [ ] Crear `variable_source_map`.
- [ ] Crear `data_quality_report`.
- [ ] Crear `policy_admin_transition_cost`.
- [ ] Crear `frontier_benchmark_anchor` con nota de consistencia poblacional.

## 26.4 Checklist de validación

- [ ] No hay países extra.
- [ ] No hay años mezclados sin flag.
- [ ] Colombia 2026 está fuera del baseline o marcado como robustez.
- [ ] GMI indica versión agregada o microdata.
- [ ] `MFC_hist_gross` tiene definición exacta.
- [ ] Costos de política tienen parámetros explícitos.
- [ ] Cada variable final tiene fuente y transformación.
- [ ] Cada missing/imputación/conflicto está reportado.
- [ ] Las tablas de resultado tienen schema definido, pero no se llenan en este plan.

---

# 27. Qué NO debe hacer este plan

No debe:

- correr `V` final;
- reportar factibilidad fiscal;
- ejecutar Monte Carlo;
- llenar `fiscal_space_result` como resultado final;
- llenar `threshold_inversion_result`;
- afirmar que UBI/PBI/GMI/PEN/MUT son viables o inviables;
- expandir a más países;
- esconder supuestos en scripts;
- usar datos 2026 como baseline 2024 sin marcarlo;
- presentar GMI agregado como microsimulación.

---

# 28. Resultado final esperado de este plan

Al terminar la construcción de base, debe existir una base DuckDB/Parquet que permita al plan de reproducción responder después:

1. Qué cuesta cada política como porcentaje del PIB.
2. Qué parte del costo es gross y net.
3. Qué supuestos normativos definen cada política.
4. Qué tan fuerte es la capacidad fiscal histórica de cada país.
5. Cuáles son los percentiles históricos de captura fiscal.
6. Qué variables son observadas, construidas o parametrizadas.
7. Qué fuente alimenta cada variable final.
8. Qué datos faltan, se imputaron o se arrastraron.
9. Qué versión de base alimenta cada corrida posterior.
10. Qué insumos están listos para reproducir el framework.

La base debe quedar lista para que el siguiente documento, `02_ESD_AI_USP_v6.md`, pueda correr:

- adopción productiva;
- shocks IA;
- conversión fiscal;
- índice `V`;
- Monte Carlo;
- diagnósticos;
- threshold inversion;
- tablas y figuras del paper.

---


# 29. Appendix A — Variable-by-source download matrix

Este apéndice convierte el plan conceptual en una guía operativa de descarga. Su función es indicar, para cada variable final necesaria, **de qué institución debe salir**, cuál es la fuente primaria, cuál es la fuente secundaria, qué código/API se intentará usar y en qué tabla procesada terminará.

Regla central:

> Ninguna variable final debe quedar sin fuente primaria, fuente secundaria o decisión explícita de supuesto.

Este apéndice no ejecuta descargas. Solo define el mapa de extracción que después deberán implementar los scripts de ingesta.

---

## A.1 Jerarquía de fuentes

Cuando existan varias fuentes para una misma variable, se debe aplicar esta jerarquía:

1. **Fuente internacional armonizada**, si la variable requiere comparabilidad entre Perú, Chile, Colombia y México.
2. **Fuente nacional oficial**, si la variable internacional está rezagada, falta o usa una definición demasiado agregada.
3. **Fuente regional especializada**, si mejora comparabilidad latinoamericana, por ejemplo SEDLAC, ASPIRE, CEPAL, CIAT/OECD.
4. **Construcción propia**, solo si la variable no existe directamente y puede derivarse mecánicamente de variables observadas.
5. **Supuesto/calibración**, solo si no existe dato observado directo.

Convención de prioridad:

| Prioridad | Significado |
|---|---|
| P1 | Fuente primaria para baseline. |
| P2 | Fuente secundaria para contraste/robustez. |
| P3 | Fuente nacional para actualización o validación. |
| P4 | Construcción propia desde variables observadas. |
| P5 | Supuesto/calibración; no debe presentarse como dato observado. |

---

## A.2 Instituciones fuente por país

| País | Estadística nacional | Banco central | Finanzas públicas | Tributación | Pobreza/social | Encuestas hogar/laborales |
|---|---|---|---|---|---|---|
| Perú | INEI | BCRP | MEF | SUNAT | MIDIS, MEF, INEI | ENAHO, EPE/EPEN, encuestas INEI |
| Chile | INE Chile | Banco Central de Chile | DIPRES, Ministerio de Hacienda | SII | Ministerio de Desarrollo Social y Familia | CASEN, ENE |
| Colombia | DANE | Banco de la República | Ministerio de Hacienda y Crédito Público | DIAN | Prosperidad Social, DNP, DANE | GEIH, ENCV |
| México | INEGI | Banco de México | SHCP | SAT | CONEVAL, Secretaría de Bienestar | ENIGH, ENOE |

Estas fuentes nacionales deben registrarse en `dim_source` y conectarse con `variable_source_map` cuando se usen como baseline, validación o robustez.

---

## A.3 Fuentes internacionales principales

| Fuente | Institución | Uso principal | Tipo de dato | Rol recomendado |
|---|---|---|---|---|
| WDI | World Bank | PIB, población, tipo de cambio, deflactores, internet, algunos indicadores fiscales | País-año | P1 macro/digital; P2 fiscal/pobreza |
| PIP | World Bank Poverty and Inequality Platform | Pobreza, poverty gap, Gini, líneas internacionales | País-año / encuesta | P1 pobreza agregada |
| SEDLAC | CEDLAS + World Bank | Pobreza, ingresos, distribución, mercado laboral, informalidad LATAM | País-año / encuesta armonizada | P1/P2 distribución e informalidad |
| ASPIRE | World Bank | Protección social, cobertura, transferencias, asistencia social | País-año / encuesta | P2/P3 gasto y cobertura social |
| OECD Revenue Statistics | OECD / CEPAL / CIAT / BID | Recaudación tributaria y estructura tributaria | País-año | P1 tax/GDP si cubre país-año |
| GRD | ICTD / UNU-WIDER | Ingresos públicos, impuestos, recursos naturales | País-año | P2 fiscal y contraste histórico |
| IMF WEO | IMF | Deuda, balance fiscal, PIB nominal, series macro-fiscales | País-año | P1 deuda/balance si disponible |
| IMF GFS | IMF | Gobierno general, ingresos, gastos, deuda, clasificación fiscal | País-año | P2/P3 fiscal detallado |
| IMF AIPI | IMF | AI Preparedness Index y componentes | País / índice | P1 preparación IA |
| ILOSTAT | ILO | Empleo, informalidad, ocupación, desempleo, fuerza laboral | País-año | P1/P2 laboral |
| LABLAC | BID | Mercado laboral LATAM | País-año / encuesta | P2 laboral |
| ITU | International Telecommunication Union | Brecha digital, internet, banda ancha, telefonía | País-año | P1/P2 digital |
| Penn World Table | Groningen Growth and Development Centre / UC Davis | Labor share, productividad, TFP, capital, empleo | País-año | P1 labor share/productividad histórica |
| UN WPP | United Nations | Población total, por edad, proyecciones | País-año | P2/P3 población por edad |
| CEPALSTAT | CEPAL | Indicadores sociales, fiscales, digitales y regionales LATAM | País-año | P2/P3 contraste regional |

---

## A.4 Matriz operativa de descarga por variable final

### A.4.1 Identificadores y dimensiones

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `country_id` | `dim_country` | ISO 3166 | WDI metadata | ISO / World Bank | PER, CHL, COL, MEX | País | 4 países | Llave principal |
| `country_name` | `dim_country` | WDI metadata | ISO | World Bank / ISO | metadata country endpoint | País | 4 países | Etiquetas |
| `region` | `dim_country` | WDI metadata | CEPAL | World Bank / CEPAL | LAC metadata | País | 4 países | Agrupación |
| `income_group` | `dim_country` | WDI metadata | World Bank country classification | World Bank | country metadata | País-año/clasificación | 4 países | Contexto |
| `policy_id` | `dim_policy` | Paper | Construcción propia | Autor | PEN, MUT, GMI, PBI, UBI | Política | Todas | Dimensión política |
| `scenario_id` | `dim_ai_scenario` | Paper | Construcción propia | Autor | scenario labels | Escenario | Todas | Dimensión IA |
| `regime_id` | `dim_fiscal_regime` | Paper | Construcción propia | Autor | r0-r4 | Régimen | Todas | Dimensión fiscal |

### A.4.2 Macro anchors

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `gdp_nominal_lcu` | `macro_anchor` | WDI | Cuentas nacionales nacionales | World Bank / bancos centrales / INE | `NY.GDP.MKTP.CN` | País-año | 4 países | Denominador fiscal y MFC |
| `gdp_nominal_usd` | `macro_anchor` | WDI | IMF WEO | World Bank / IMF | `NY.GDP.MKTP.CD` | País-año | 4 países | Comparabilidad y tabla descriptiva |
| `gdp_constant_lcu` | `macro_anchor` | WDI | cuentas nacionales | World Bank / bancos centrales | `NY.GDP.MKTP.KN` | País-año | 4 países | Crecimiento real/robustez |
| `gdp_growth_real` | `macro_anchor` | WDI | IMF WEO | World Bank / IMF | `NY.GDP.MKTP.KD.ZG` | País-año | 4 países | Validación macro |
| `gdp_deflator` | `macro_anchor` | WDI | bancos centrales | World Bank / bancos centrales | `NY.GDP.DEFL.ZS` | País-año | 4 países | Precios/transformaciones |
| `population_total` | `macro_anchor` | WDI | UN WPP / institutos nacionales | World Bank / UN / INE | `SP.POP.TOTL` | País-año | 4 países | UBI/PBI/MUT |
| `population_65_plus` | `macro_anchor` | WDI | UN WPP / censos nacionales | World Bank / UN / INE | `SP.POP.65UP.TO` | País-año | 4 países | PEN |
| `population_15_64` | `macro_anchor` | WDI | UN WPP | World Bank / UN | `SP.POP.1564.TO` revisar metadata | País-año | 4 países | Mercado laboral/adopción |
| `exchange_rate_lcu_per_usd` | `macro_anchor` | WDI | bancos centrales | World Bank / bancos centrales | `PA.NUS.FCRF` | País-año | 4 países | Conversiones monetarias |
| `cpi_index` | `macro_anchor` | WDI | bancos centrales / institutos estadísticos | World Bank / nacionales | `FP.CPI.TOTL` revisar metadata | País-año | 4 países | Deflactar beneficios si aplica |

Regla: para `MFC_hist_gross`, `gdp_nominal_lcu` debe venir de la misma convención temporal que la serie de ingresos fiscales. No mezclar PIB en USD con recaudación en moneda local.

### A.4.3 Fiscal anchors

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `tax_revenue_gdp` | `fiscal_anchor` | OECD Revenue Statistics | WDI / GRD / fuentes nacionales | OECD / World Bank / ICTD / SUNAT-SII-DIAN-SAT | OECD dataset; WDI `GC.TAX.TOTL.GD.ZS` como contraste | País-año | 4 países si disponible | Capacidad tributaria baseline |
| `total_revenue_gdp` | `fiscal_anchor` | IMF WEO/GFS | GRD / WDI / MEF-DIPRES-MHCP-SHCP | IMF / ICTD / nacionales | WEO/GFS revenue; WDI `GC.REV.XGRT.GD.ZS` revisar | País-año | 4 países | MFC total revenue |
| `nonresource_revenue_gdp` | `fiscal_anchor` | GRD | IMF GFS / nacionales | ICTD / IMF / nacionales | GRD non-resource revenue | País-año | 4 países si disponible | MFC no recurso |
| `tax_revenue_lcu` | `fiscal_anchor` | Fuentes nacionales | OECD / GFS | SUNAT/SII/DIAN/SAT + ministerios | tabla nacional anual | País-año | 4 países | Numerador MFC tax |
| `total_revenue_lcu` | `fiscal_anchor` | Fuentes nacionales / IMF GFS | GRD | ministerios / IMF | tabla presupuestal anual | País-año | 4 países | Numerador MFC total |
| `direct_tax_gdp` | `fiscal_anchor` | OECD Revenue Statistics | fuentes nacionales | OECD / tax authorities | OECD tax categories | País-año | 4 países | Estructura fiscal |
| `indirect_tax_gdp` | `fiscal_anchor` | OECD Revenue Statistics | fuentes nacionales | OECD / tax authorities | VAT/excise categories | País-año | 4 países | Estructura fiscal |
| `social_contributions_gdp` | `fiscal_anchor` | OECD Revenue Statistics | GFS / nacionales | OECD / IMF / ministerios | social contributions category | País-año | 4 países | Convención gross/net |
| `public_debt_gdp` | `fiscal_anchor` | IMF WEO | ministerios / bancos centrales | IMF / nacionales | WEO general government gross debt | País-año | 4 países | Guardrail fiscal |
| `primary_balance_gdp` | `fiscal_anchor` | IMF WEO | ministerios | IMF / nacionales | WEO primary net lending/borrowing | País-año | 4 países | Guardrail fiscal |
| `overall_balance_gdp` | `fiscal_anchor` | IMF WEO | ministerios | IMF / nacionales | WEO net lending/borrowing | País-año | 4 países | Guardrail fiscal |
| `social_protection_spending_gdp` | `fiscal_anchor` | ASPIRE / nacionales | CEPALSTAT / OECD SOCX si aplica | World Bank / ministerios | ASPIRE indicators; national budget functions | País-año | 4 países | Costo neto/política existente |
| `vat_exemptions_share` | `fiscal_anchor` | Informes nacionales de gasto tributario | OECD tax expenditure references si aplica | SUNAT, DIPRES/Hacienda, DIAN, SHCP | tax expenditure VAT/exemptions reports | País-año | 4 países | Exenciones IVA / gasto tributario (`exempt_C`) |

Regla: si OECD, GRD, WDI e IMF no coinciden, `variable_source_map` debe registrar la fuente elegida y `data_quality_report.source_conflict_flag=TRUE`.

### A.4.4 Poverty and distribution anchors

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `poverty_headcount_intl` | `poverty_distribution_anchor` | PIP | WDI poverty indicators | World Bank | PIP API: headcount by poverty line | País-año/encuesta | 4 países | Diagnóstico pobreza |
| `poverty_gap_intl` | `poverty_distribution_anchor` | PIP | WDI / SEDLAC | World Bank / CEDLAS | PIP API: poverty gap by poverty line | País-año/encuesta | 4 países | GMI MVP |
| `poverty_headcount_national` | `poverty_distribution_anchor` | Fuentes nacionales | SEDLAC / PIP | INEI, MDSF, DANE, CONEVAL | national poverty reports | País-año | 4 países | Validación local |
| `poverty_gap_national` | `poverty_distribution_anchor` | SEDLAC / nacionales | PIP | CEDLAS/WB + nacionales | SEDLAC poverty gap; national reports | País-año/encuesta | 4 países | GMI alternativo |
| `gini` | `poverty_distribution_anchor` | PIP / SEDLAC | WDI | World Bank / CEDLAS | PIP Gini; WDI `SI.POV.GINI` | País-año/encuesta | 4 países | Distribución / robustez |
| `income_share_bottom40` | `poverty_distribution_anchor` | WDI / SEDLAC | PIP | World Bank / CEDLAS | WDI distribution indicators; SEDLAC | País-año | 4 países | Distribución |
| `income_deciles` | `poverty_distribution_anchor` | SEDLAC | microdatos nacionales | CEDLAS / nacionales | SEDLAC deciles or computed from microdata | País-año/deciles | 4 países | GMI más fuerte |
| `poverty_line_value` | `poverty_distribution_anchor` | PIP / nacionales | SEDLAC | World Bank / nacionales | PIP poverty line metadata; national poverty line | País-año | 4 países | MUT/GMI |
| `welfare_concept` | `poverty_distribution_anchor` | PIP metadata | SEDLAC metadata | World Bank / CEDLAS | income/consumption flag | País-año | 4 países | Comparabilidad |

Regla GMI:

- `GMI_ideal_aggregate`: puede usar `poverty_gap_intl` o `poverty_gap_national`, pero debe marcarse como aproximación agregada.
- `GMI_ideal_microdata`: debe usar microdatos o distribución por deciles/ventiles claramente documentada.

### A.4.5 Labor, informality and productive structure

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `informal_employment_rate_total` | `labor_informality_anchor` | ILOSTAT / SEDLAC | fuentes nacionales | ILO / CEDLAS / INEI-INE-DANE-INEGI | ILOSTAT informality indicators; SEDLAC labor | País-año | 4 países | Fricción fiscal/adopción |
| `informal_employment_rate_nonagri` | `labor_informality_anchor` | ILOSTAT | SEDLAC/nacionales | ILO / CEDLAS / nacionales | ILOSTAT non-agri informality | País-año | 4 países | Robustez |
| `employment_total` | `labor_informality_anchor` | ILOSTAT | WDI / nacionales | ILO / World Bank / nacionales | ILOSTAT employment; WDI employment indicators | País-año | 4 países | Escala laboral |
| `labor_force_total` | `labor_informality_anchor` | ILOSTAT | WDI | ILO / World Bank | WDI `SL.TLF.TOTL.IN` revisar | País-año | 4 países | Mercado laboral |
| `unemployment_rate` | `labor_informality_anchor` | ILOSTAT | WDI / nacionales | ILO / World Bank / nacionales | WDI `SL.UEM.TOTL.ZS` | País-año | 4 países | Contexto laboral |
| `employment_by_sector` | `labor_informality_anchor` | ILOSTAT | WDI / nacionales | ILO / World Bank / nacionales | agriculture/industry/services employment shares | País-sector-año | 4 países | Exposición IA sectorial |
| `employment_by_occupation` | `labor_informality_anchor` | ILOSTAT / microdatos | nacionales | ILO / INEI-INE-DANE-INEGI | ISCO occupation tables | País-ocupación-año | 4 países | Exposición IA task-based |
| `labor_share` | `labor_informality_anchor` | Penn World Table | AMECO/OECD/nacionales si aplica | PWT / nacionales | PWT `labsh` | País-año | 4 países | Distribución funcional |
| `rst_proxy` | `labor_informality_anchor` | ILOSTAT participación en formación | gasto ALMP OCDE/CEPAL; robustez: componente capital humano del AIPI residualizado contra A | ILO / OECD / CEPAL / IMF | training participation / ALMP spending / residualized AIPI human capital | País-año | 4 países | Reskilling (`RST`) |
| `tfp_level` | `macro_anchor` o `productivity_anchor` | Penn World Table | WDI/Conference Board | PWT | PWT TFP variables | País-año | 4 países | Contexto productividad, no shock IA directo |
| `output_per_worker` | `macro_anchor` o `productivity_anchor` | WDI / PWT | ILOSTAT | World Bank / PWT / ILO | GDP per person employed indicators | País-año | 4 países | Productividad laboral |

Regla: la informalidad debe usarse una sola vez por convención. Si afecta adopción y captura fiscal, debe existir un flag que explique si se usa como fricción de adopción, fricción fiscal o ambas en análisis de robustez.

### A.4.6 Digital readiness and AI preparedness

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `aipi_total` | `ai_preparedness_anchor` | IMF AIPI | Paper seed values | IMF | AIPI total index | País / año índice | 4 países | Preparación IA |
| `aipi_infrastructure` | `ai_preparedness_anchor` | IMF AIPI | ITU/WDI reconstruction | IMF / ITU / World Bank | AIPI component | País / año índice | 4 países | Descomposición |
| `aipi_labor_skills` | `ai_preparedness_anchor` | IMF AIPI | education/labor proxies | IMF / WB / ILO | AIPI component | País / año índice | 4 países | Descomposición |
| `aipi_innovation` | `ai_preparedness_anchor` | IMF AIPI | WDI R&D/proxies | IMF / WB | AIPI component | País / año índice | 4 países | Descomposición |
| `aipi_regulation_ethics` | `ai_preparedness_anchor` | IMF AIPI | Oxford/Stanford AI indices si se usa robustez | IMF / terceros | AIPI component | País / año índice | 4 países | Descomposición |
| `internet_users_pct` | `ai_preparedness_anchor` | WDI | ITU | World Bank / ITU | `IT.NET.USER.ZS` | País-año | 4 países | Brecha digital |
| `mobile_subscriptions_per100` | `ai_preparedness_anchor` | WDI | ITU | World Bank / ITU | `IT.CEL.SETS.P2` | País-año | 4 países | Brecha digital |
| `fixed_broadband_per100` | `ai_preparedness_anchor` | WDI | ITU | World Bank / ITU | `IT.NET.BBND.P2` | País-año | 4 países | Brecha digital |
| `secure_internet_servers` | `ai_preparedness_anchor` | WDI | ITU | World Bank / ITU | `IT.NET.SECR.P6` revisar | País-año | 4 países | Infraestructura digital |
| `electricity_access_pct` | `ai_preparedness_anchor` | WDI | nacionales | World Bank / nacionales | `EG.ELC.ACCS.ZS` | País-año | 4 países | Infraestructura mínima |
| `rd_expenditure_gdp` | `ai_preparedness_anchor` | WDI/UNESCO | nacionales | World Bank / UNESCO / nacionales | `GB.XPD.RSDV.GD.ZS` revisar | País-año | 4 países | Innovación |
| `q_use_target_moment` | `digital_gap_anchor` / módulo de adopción | Encuestas TIC/firmas nacionales | WB Firm-level Adoption of Technology (FAT), OECD ICT/AI use in enterprises | INEGI, INEI, INE, DANE, World Bank, OECD | ENDUTIH / TIC firmas / FAT / OECD ICT | País-año | 4 países | Momento ancla de adopción (`q_use_target`), P3 nacional / P5 supuesto etiquetado si no hay dato |

Regla: `AIPI` puede alimentar preparación IA, pero no debe duplicarse dentro de `q_prod` y luego otra vez como multiplicador sin una convención explícita. Regla adicional: los indicadores usados para `gap_index` deben estar excluidos del AIPI o residualizarse contra el AIPI (`Gap - Proj_A(Gap)`); internet, banda ancha y móvil están dentro del pilar digital del AIPI y no pueden entrar directo al Gap baseline.

### A.4.7 Policy parameters and social protection costs

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `age_threshold` | `policy_parameter` | diseño del paper / ley nacional | supuestos | Autor / ministerios | edad legal o escenario | País-política-año | 4 países | PEN |
| `benefit_formula` | `policy_parameter` | paper / ley / presupuesto | supuestos | Autor / ministerios | fórmula textual versionada | País-política-año | 4 países | Todas las políticas |
| `eta_policy` | `policy_parameter` | paper / supuesto | robustez | Autor | eta_MUT, eta_PBI, eta_UBI | País-política-año | 4 países | MUT/PBI/UBI |
| `chi_gmi` | `policy_parameter` | paper / supuesto | robustez | Autor | chi_gmi | País-política-año | 4 países | GMI |
| `theta_target` | `policy_parameter` | paper / supuesto | robustez | Autor | theta_target [1.0, 1.5] | País-política-año | 4 países | GMI cargado |
| `eligible_population_rule` | `policy_parameter` | paper / ley / microdata | supuestos | Autor / nacionales | regla SQL/documentada | País-política-año | 4 países | Población elegible |
| `gross_or_net_convention` | `policy_parameter` | paper | construcción propia | Autor | gross/net | País-política-año | 4 países | Transparencia |
| `existing_spending_treatment` | `policy_parameter` | presupuesto nacional / ASPIRE | supuestos | ministerios / World Bank | budget function/social protection | País-política-año | 4 países | Costo neto |
| `existing_social_transfer_spending` | `policy_cost` | ASPIRE / presupuestos nacionales | CEPALSTAT | World Bank / ministerios | ASPIRE + budget categories | País-año-política | 4 países | Netting-out |
| `benefit_amount_lcu` | `policy_cost` | policy_parameter + poverty line | nacionales / PIP | construido | fórmula versionada | País-política-año | 4 países | Costo bruto |
| `eligible_population` | `policy_cost` | WDI/UN WPP/microdata | nacionales | construido | population filters | País-política-año | 4 países | Costo bruto |
| `policy_cost_gross_lcu` | `policy_cost` | construcción propia | — | Autor | formula script | País-política-año | 4 países | Costo |
| `policy_cost_gross_gdp` | `policy_cost` | construcción propia | — | Autor | formula script | País-política-año | 4 países | Umbral `c` |
| `policy_cost_net_gdp` | `policy_cost` | construcción propia | — | Autor | formula script | País-política-año | 4 países | Umbral neto |

Regla: `policy_cost` es un insumo construido, no una simulación de factibilidad. Debe tener `dataset_version`, `build_id`, `parameter_set_id`, `assumption_id` y `created_by_script`. Si luego se recalcula dentro de una corrida Monte Carlo, la versión de resultado sí debe usar `run_id`.

### A.4.8 Microdata for paper-ready GMI

| País | Microdato principal | Institución | Uso | Prioridad |
|---|---|---|---|---|
| Perú | ENAHO | INEI | Ingresos, pobreza, hogares, elegibilidad GMI | P1 nacional |
| Chile | CASEN | Ministerio de Desarrollo Social y Familia | Ingresos, pobreza, transferencias, hogares | P1 nacional |
| Colombia | GEIH / ENCV | DANE | Ingresos, empleo, informalidad, hogares | P1 nacional |
| México | ENIGH | INEGI | Ingresos, pobreza, transferencias, hogares | P1 nacional |

Variables mínimas para GMI con microdatos:

| Variable micro | Uso |
|---|---|
| ingreso per cápita del hogar/persona | Calcular brecha individual/hogar respecto a línea |
| factor de expansión | Expandir a población nacional |
| línea de pobreza | Definir umbral GMI |
| tamaño del hogar | Equivalencias y costo total |
| edad | PEN y segmentación |
| condición laboral | informalidad y elegibilidad si aplica |
| transferencias existentes | netting-out |
| área/geografía | urbano/rural y sensibilidad |

Regla: si no se usan microdatos, el GMI debe reportarse como `GMI_ideal_aggregate`, no como microsimulación.

### A.4.9 Historical capture distribution

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Código/API candidato | Nivel | Países | Uso |
|---|---|---|---|---|---|---|---|---|
| `delta_gdp_lcu` | `historical_capture_distribution` | WDI / cuentas nacionales | IMF WEO | World Bank / nacionales / IMF | Δ `NY.GDP.MKTP.CN` | País-año | 4 países | Denominador MFC |
| `delta_tax_revenue_lcu` | `historical_capture_distribution` | nacional / OECD / GFS | GRD | tax authorities / OECD / IMF | Δ tax revenue LCU | País-año | 4 países | Numerador tax MFC |
| `delta_total_revenue_lcu` | `historical_capture_distribution` | nacional / IMF GFS | GRD | ministerios / IMF / ICTD | Δ total revenue LCU | País-año | 4 países | Numerador total MFC |
| `MFC_hist_gross_tax` | `historical_capture_distribution` | construcción propia | — | Autor | ΔTaxRevenue/ΔGDP | País-año | 4 países | Percentiles históricos |
| `MFC_hist_gross_total_revenue` | `historical_capture_distribution` | construcción propia | — | Autor | ΔTotalRevenue/ΔGDP | País-año | 4 países | Percentiles históricos |
| `MFC_hist_gross_nonresource` | `historical_capture_distribution` | construcción propia desde GRD | — | Autor / GRD | ΔNonResourceRevenue/ΔGDP | País-año | 4 países | Robustez |
| `MFC_hist_gross_smoothed_3y` | `historical_capture_distribution` | construcción propia | — | Autor | promedio móvil 3 años | País-año | 4 países | Robustez contra ruido |
| `mfc_p50` | `historical_capture_percentiles` | construcción propia | — | Autor | percentile 50 | País | 4 países | Comparador histórico |
| `mfc_p75` | `historical_capture_percentiles` | construcción propia | — | Autor | percentile 75 | País | 4 países | Comparador histórico fuerte |
| `mfc_p90` | `historical_capture_percentiles` | construcción propia | — | Autor | percentile 90 | País | 4 países | Comparador histórico extremo |

Definición mecánica baseline:

$$
MFC^{hist,gross}_{i,t}=\frac{Revenue_{i,t}-Revenue_{i,t-1}}{GDP_{i,t}-GDP_{i,t-1}}
$$

Condiciones obligatorias:

1. `Revenue` y `GDP` deben estar en la misma moneda y misma base temporal.
2. Años con `ΔGDP <= 0` deben marcarse como inválidos para percentiles baseline.
3. Años de crisis deben conservarse, pero marcarse con `crisis_flag`.
4. Extremos deben reportarse con y sin winsorización.
5. La variante usada en el paper debe estar identificada como `mfc_variant_baseline=TRUE`.

### A.4.10 Variables que NO son datos observados directos

Estas variables no deben descargarse como si fueran datos públicos observados. Deben registrarse en `assumption_registry` o `parameter_set`.

| Variable | Naturaleza | Tabla | Tratamiento |
|---|---|---|---|
| `q_prod` | Adopción productiva de IA, calibrada o simulada por el módulo de adopción (no es productividad ni dato observado) | `parameter_set` / reproducción | Escenario o calibración, no dato observado |
| `phi_raw` | Shock crudo de productividad IA en unidad fuente (TFP/LP/Y), disciplinado por la literatura; nunca entra directo a ecuaciones fiscales | `parameter_set` / reproducción | Escenario disciplinado por literatura (soportes del paper); se convierte vía `kappa_u_to_Y` y `pi_AI_Y` antes de cualquier ecuación fiscal |
| `mfc_gross_future` | Conversión fiscal futura | reproducción | Escenario/regímenes r0-r4 |
| `leakage_rate` | Supuesto institucional/fiscal | `assumption_registry` | Sensibilidad |
| `profit_shifting_rate` | Supuesto fiscal internacional | `assumption_registry` | Sensibilidad |
| `adoption_elasticity` | Parámetro de adopción | `parameter_set` | Sensibilidad |
| `informality_reduction_from_ai` | Supuesto de canal IA | `parameter_set` | Sensibilidad |
| `task_exposure_ai` | Puede ser construido desde datasets externos | `productivity_anchor` o reproducción | Documentar fuente y mapping ocupacional |
| `phi_ict_placebo` | Ancla de literatura growth-accounting para la contribución ICT 2010-2018 (placebo temporal) | `assumption_registry` | Anclar a estimaciones publicadas; comparabilidad `beta_ICT=beta`, `gamma_ICT=gamma` |
| `epsilon_ero` | Elasticidad de erosión conductual de bases gravables por canal | `assumption_registry` | Companion obligatorio para regímenes `r>=1`; grilla/soporte declarado |
| `fs_eff` | Resultado del modelo | `fiscal_space_result` | No pertenece a base observada |
| `V` | Resultado del modelo | `fiscal_space_result` | No pertenece a base observada |

---


### A.4.11 Frontier benchmark (economías externas al piloto)

| Variable final | Tabla final | Fuente primaria | Fuente secundaria | Institución | Nivel | Uso |
|---|---|---|---|---|---|---|
| `aipi_total` (benchmark) | `frontier_benchmark_anchor` | IMF AIPI (cubre 174 economías) | — | IMF | País benchmark | Score frontier |
| `exposure_productive` (benchmark) | `frontier_benchmark_anchor` | IMF/OECD exposure estimates (Cazzaniga et al. 2024; Filippucci et al. 2025) | task-based datasets | IMF / OECD | País benchmark | Score frontier |
| `adoption_proxy` (benchmark) | `frontier_benchmark_anchor` | OECD ICT/AI use in enterprises | Eurostat; US Census AI Supplement | OECD / Eurostat / Census | País benchmark | Score frontier |

Nota operativa: el script `10_download_aipi.py` debe descargar TODOS los países del AIPI, no solo los cuatro del piloto, precisamente para poder construir el benchmark frontier.

## A.5 Matriz de scripts de descarga sugerida

| Script | Fuente | Método | Endpoint / procedimiento resuelto | Salida raw | Variables principales |
|---|---|---|---|---|---|
| `01_download_wdi.py` | World Bank WDI API | `api` | `https://api.worldbank.org/v2/country/{iso}/indicator/{indicator}?format=json&per_page=20000` | `raw/wdi/wdi_country_year.parquet` | PIB, población, FX, deflactores, internet, WDI fiscal fallback |
| `02_download_pip.py` | World Bank PIP | `api` | `https://api.worldbank.org/pip/v1/pip?country={iso}&povline={line}&format=json` | `raw/pip/pip_poverty.parquet` | pobreza, poverty gap, Gini, líneas internacionales |
| `03_download_sedlac.py` | SEDLAC/CEDLAS | `manual_registered` | Sin API pública; registrar descarga manual de estadísticas Excel CEDLAS/SEDLAC con hash pendiente. | `raw/sedlac/sedlac_lac.parquet` | distribución, ingreso, pobreza, informalidad armonizada |
| `04_download_oecd_revenue.py` | OECD Data Explorer / Revenue Statistics LAC | `api` | Estructura: `https://sdmx.oecd.org/public/rest/dataflow/OECD.CTP.TPS/DSD_REV_COMP_LAC@DF_RSLAC/1.1?references=all`; datos CSV: `https://sdmx.oecd.org/public/rest/data/OECD.CTP.TPS,DSD_REV_COMP_LAC@DF_RSLAC/PER......` con `Accept: text/csv`. | `raw/oecd/oecd_revenue.parquet` | tax/GDP, estructura tributaria |
| `05_download_grd.py` | ICTD/UNU-WIDER GRD | `bulk` / `manual_registered` | HDX CKAN: `https://data.humdata.org/api/3/action/package_show?id=government-revenue-dataset`; usar solo recurso GRD 2025 Excel/Stata. Si HDX no expone 2025, registrar descarga manual UNU-WIDER. | `raw/grd/grd_revenue.parquet` | ingresos, impuestos, non-resource revenue |
| `06_download_imf_weo_gfs.py` | IMF WEO/GFS DataMapper | `api` / `manual_registered` | `https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso}` con User-Agent de navegador; si persiste 403, registrar WEO Database bulk manual. | `raw/imf/imf_fiscal_macro.parquet` | deuda, balance, ingresos, gasto |
| `07_download_ilostat.py` | ILOSTAT | `api` | `https://rplumber.ilo.org/data/ref_area?id={iso}_A&format=.csv.gz` | `raw/ilostat/ilostat_labor.parquet` | empleo, informalidad, ocupaciones |
| `08_download_pwt.py` | Penn World Table | `bulk` | DataverseNL API datafile PWT 10.01 (`.dta`). | `raw/pwt/pwt_country_year.parquet` | labor share, TFP, productividad |
| `09_download_itu.py` | ITU / WDI fallback | `api` | `https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=20000`; sin filtro país para benchmark frontier. | `raw/itu/itu_digital.parquet` | conectividad, banda ancha, TIC |
| `10_download_aipi.py` | IMF AIPI | `api` | `https://data360api.worldbank.org/data360/data?DATABASE_ID=IMF_AI`; descargar todos los países. | `raw/imf/aipi.parquet` | AIPI total y componentes |
| `11_download_national_sources.py` | fuentes nacionales PER | `api` / `manual_registered` | BCRPData: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigos}/json/{inicio}/{fin}`; SUNAT cuadros estadísticos Excel queda manual registrado. | `raw/national/{country}/...` | contrastes macro-fiscales PER, presupuesto, recaudación |
| `12_register_manual_sources.py` | manual metadata | `manual_registered` | `metadata/manual_source_registry.yml`; registra SEDLAC, SUNAT, GRD manual fallback y benchmarks no-UE con instrucciones y hash pendiente. | `metadata/manual_source_registry.yml` | URLs, documentos, notas, supuestos |
| `13_download_frontier_benchmark.py` | Eurostat AI adoption; benchmarks no-UE manuales | `api` / `manual_registered` | Eurostat `isoc_eb_ai`: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/isoc_eb_ai?format=JSON`; USA/no-UE manual registrado; elección del set benchmark se difiere a calibración Fase 1. | `raw/frontier/frontier_benchmark.parquet` | exposición y adopción de economías benchmark para `frontier_benchmark_anchor` |
| `14_download_wpp_projections.py` | UN World Population Prospects 2024 (variante media) | `bulk` | `https://population.un.org/wpp/assets/downloads.json` -> `assets/Excel Files/1_Indicator (Standard)/CSV_FILES/WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz`; filtrar PER/CHL/COL/MEX y 2024-2035. | `raw/wpp/wpp_projections.parquet` | población por edad simple y sexo proyectada; grupos quinquenales y derivados 65+/15-64/18+ se construyen después en anchors |

Regla: cada script debe escribir un archivo `metadata.json` con:

```yaml
source_id:
download_date:
source_url:
query_or_endpoint:
country_filter:
year_filter:
raw_file_hash:
script_name:
script_version:
notes:
```

---

## A.6 Tabla `source_candidate_catalog`

Además de `dim_source`, conviene crear una tabla auxiliar no analítica llamada `source_candidate_catalog`. Esta tabla no alimenta directamente el modelo; sirve para que el equipo sepa qué se intentó descargar y qué quedó pendiente.

| Campo | Tipo | Descripción |
|---|---|---|
| `candidate_id` | TEXT | ID de fuente candidata. |
| `variable_name` | TEXT | Variable final que podría alimentar. |
| `country_id` | TEXT | ISO3 o `ALL`. |
| `source_name` | TEXT | Nombre de fuente. |
| `institution` | TEXT | Institución responsable. |
| `source_url` | TEXT | URL o endpoint. |
| `api_available` | BOOLEAN | Tiene API programática. |
| `bulk_download_available` | BOOLEAN | Tiene descarga masiva. |
| `manual_download_required` | BOOLEAN | Requiere descarga manual. |
| `access_restriction` | TEXT | open / registration / restricted / unclear. |
| `priority` | TEXT | P1-P5. |
| `status` | TEXT | planned / downloaded / failed / replaced / not_needed. |
| `notes` | TEXT | Comentarios. |

Esta tabla ayuda a evitar perder trazabilidad cuando una fuente internacional falla y se cambia a fuente nacional.

---

## A.7 Reglas para `variable_source_map`

Cada variable final debe mapearse con una fila mínima como esta:

| Campo | Ejemplo |
|---|---|
| `table_name` | `fiscal_anchor` |
| `variable_name` | `tax_revenue_gdp` |
| `country_id` | `PER` |
| `year` | 2024 |
| `source_id` | `OECD_REVSTAT_LAC` |
| `raw_table` | `raw_oecd_revenue` |
| `raw_indicator_code` | `tax_revenue_pct_gdp` |
| `transformation_script` | `21_build_fiscal_anchor.py` |
| `transformation_notes` | `OECD chosen over WDI because it provides harmonized LAC tax categories.` |
| `harmonization_flag` | `TRUE` |
| `source_conflict_flag` | `FALSE` |

Regla:

> Si una variable aparece en una tabla final y no aparece en `variable_source_map`, la base no debe considerarse reproducible.

---

## A.8 Checklist de descarga variable-fuente

Antes de cerrar la base, debe verificarse:

- [ ] Cada variable de `macro_anchor` tiene fuente primaria y secundaria.
- [ ] Cada variable de `fiscal_anchor` tiene fuente primaria, secundaria y convención gobierno central/general.
- [ ] Cada variable de pobreza distingue línea nacional vs internacional.
- [ ] Cada variable laboral distingue definición armonizada internacional vs nacional.
- [ ] Cada variable digital distingue WDI/ITU/AIPI.
- [ ] Cada política tiene `policy_parameter` explícito.
- [ ] Cada costo de política tiene fórmula, población elegible y denominador PIB.
- [ ] Cada variable construida tiene script de transformación.
- [ ] El benchmark frontier tiene set documentado, año de referencia y consistencia poblacional con `phi_s`.
- [ ] Cada supuesto está en `assumption_registry`.
- [ ] Cada dato arrastrado tiene `carried_forward_flag`.
- [ ] Cada conflicto de fuente está en `data_quality_report`.
- [ ] Cada fuente manual tiene URL, fecha de acceso y hash del archivo descargado.

---

## A.9 Decisión práctica para el MVP

Para no hacer el proyecto inmanejable, el MVP de descarga debe priorizar:

1. WDI: macro, población, FX, deflactores, conectividad básica.
2. OECD Revenue Statistics o GRD: tax/GDP e ingresos históricos.
3. IMF WEO/GFS: deuda y balance fiscal.
4. PIP/SEDLAC: pobreza, poverty gap, Gini.
5. ILOSTAT/SEDLAC/nacional: informalidad.
6. IMF AIPI: preparación IA.
7. PWT: labor share.
8. Fuentes nacionales solo para rellenar o validar variables críticas.

Luego, para la versión paper-ready:

1. microdatos ENAHO/CASEN/GEIH-ENCV/ENIGH;
2. presupuesto social nacional;
3. series tributarias nacionales en moneda local;
4. mappings ocupacionales para exposición IA;
5. documentación legal/normativa de políticas sociales existentes.

Conclusión del apéndice:

> El plan ya no solo dice qué variables necesita el modelo; ahora indica de qué institución debe salir cada variable, cómo debe registrarse, qué fuente usar como contraste y qué variables no deben confundirse con datos observados.

---

# 30. Conclusión práctica

La recomendación recibida es correcta y mejora mucho el diseño.

Cambios incorporados:

1. Separación explícita entre base observada, insumos construidos y resultados del modelo.
2. `run_id`, `model_version`, `parameter_set_id`, `created_at` y `created_by_script` para tablas de corrida.
3. `dataset_version` y `build_id` para tablas observadas/procesadas.
4. Tabla `policy_parameter` para evitar parámetros escondidos en código.
5. Definición mecánica exacta de `MFC_hist_gross`.
6. Tabla `variable_source_map` para trazabilidad por variable.
7. Tabla `data_quality_report` para missingness, imputación y conflictos.
8. Tratamiento prudente de Colombia 2026.
9. GMI separado en versión MVP agregada y versión paper-ready con microdatos.
10. Monte Carlo dividido en tablas globales, país-específicas, política-específicas y fiscales.
11. Priorización de un núcleo mínimo antes de tablas de ejecución.
12. v4: benchmark frontier con consistencia poblacional, tabla de costos administrativos y de transición, nivel de gobierno y ventana histórica 2000-2024, `theta_target` del GMI, regla de exclusión Gap-AIPI, pensiones contributivas fuera del offset, y corrección de etiquetas (`phi_raw`, `q_prod`).

El orden correcto del proyecto queda así:

1. Construir y auditar la base.
2. Exportar insumos reproducibles.
3. Ejecutar el modelo en un plan separado.
4. Recién después reportar resultados.
