# 02 — ESD: Estrategia empírica y diseño de simulación
## AI, Fiscal Space, and Universal Social Protection in Emerging Economies — Framework v2.5

**Nombre abreviado:** `02_ESD_AI_USP_v6.md`  
**ESD:** *Empirical and Simulation Design*  
**Versión de este documento:** v6, alineada con el paper v2.5 corregido: modo channel-based como especificación primaria (histórico como plausibilidad y robustez), horizonte acumulado H con convención endpoint, regla de informalidad corregida, separación R_req/R_req_DC, inversión de adopción con transformación inversa del piso, mezcla incondicional de captura fiscal, companion de erosión conductual para r>=1, y renumeración de secciones.  
**Documento anterior:** `01_database_construction_plan_AI_USP_threshold_framework_v6.md`  
**Función:** ejecutar el framework con la base ya construida, producir resultados, diagnósticos, simulaciones, umbrales, robustez y tablas finales.  
**Países:** Perú (`PER`), Chile (`CHL`), Colombia (`COL`) y México (`MEX`).  
**Año base principal:** 2024.  
**Unidad de análisis:** país-política-escenario-régimen, evaluada en `endpoint_year` (= `anchor_year` 2024 + H).  

---

# 0. Propósito del documento

Este documento define la estrategia empírica y el diseño de simulación para reproducir el framework del paper.

No es un diseño experimental tipo RCT ni una estrategia causal clásica. Es un diseño de **calibración, simulación, inversión de umbrales, auditoría de supuestos y robustez**.

La pregunta central no es:

> ¿La IA financiará automáticamente una política universal?

La pregunta correcta es:

> Bajo qué combinaciones de productividad inducida por IA, adopción productiva, preparación institucional, informalidad, captura fiscal, costos administrativos, transición, leakage y costo de política social se cruza o no se cruza el umbral fiscal de factibilidad.

El objeto central del diseño es:

$$
V^{gross}_{i,p,s,r,t}=\frac{fs^{eff}_{i,p,s,r,t}}{c^{gross}_{i,p,t}}.
$$

El umbral estructural principal es:

$$
V^{gross}_{i,p,s,r,t}\geq 1.
$$

El resultado principal debe reportarse en versión **gross-cost**. La versión net-cost se reporta solo como robustez cuando el costo neto incremental está bien medido, es estrictamente positivo y no descuenta gasto no sustituible.

---

# 0.1 Control de versión respecto a v3

Esta versión conserva las mejoras metodológicas y operativas de v3 e incorpora una mejora central: una metodología explícita para asignar valores, soportes, distribuciones, umbrales de interpretación y gates de decisión. En conjunto, el documento incluye:

1. especificación primaria explícita;
2. regla final agregada país-política;
3. fórmulas cerradas de threshold inversion;
4. protocolo de Monte Carlo con dependencia;
5. tabla formal de calibración de parámetros no observados;
6. disciplina del modo channel-based;
7. pruebas de convergencia Monte Carlo;
8. hard gates en tres niveles;
9. unit tests y toy examples;
10. protocolo de disciplina de resultados;
11. tratamiento reforzado de GMI;
12. minimum publishable package;
13. separación de tablas principales y appendix;
14. registro de riesgos del modelo;
15. regla **no result without audit**;
16. metodología explícita de asignación de valores y umbrales;
17. fases operativas secuenciales con dependencias, gates y outputs esperados.
18. v5-v6: alineación de modos con el paper, horizonte acumulado, construcción explícita de pesos de canal y correcciones de consistencia.

---

# 1. Posición metodológica

## 1.1 Qué tipo de evidencia produce el paper

El paper produce evidencia de cuatro tipos:

1. **Factibilidad contable:** si el espacio fiscal efectivo inducido por IA alcanza el costo bruto de la política.
2. **Plausibilidad histórica:** si la captura fiscal requerida es ordinaria, demandante o extrema respecto a la historia fiscal del país.
3. **Condiciones mínimas:** qué valores de crecimiento IA, adopción productiva, captura fiscal o captura de rentas IA serían necesarios para cruzar el umbral.
4. **Robustez bajo incertidumbre:** qué proporción de simulaciones cruza el umbral bajo draws consistentes de parámetros.

## 1.2 Qué no debe afirmar

No debe afirmar:

- que la IA financiará de hecho una política universal;
- que el modelo predice crecimiento futuro;
- que el escenario alto o disruptivo es el baseline;
- que el GMI agregado es una microsimulación;
- que una política es fiscalmente viable sin pasar por buffers, plausibilidad histórica y guardrails;
- que `Vnet` reemplaza a `Vgross`;
- que los regímenes fiscales son reformas políticamente probables;
- que los resultados son causales;
- que una celda favorable equivale automáticamente a una política robustamente factible.

---

# 2. Primary specification

Esta sección fija la especificación primaria del paper. Todo lo que no esté en esta tabla se reporta como robustez, diagnóstico o sensibilidad.

| Bloque | Especificación primaria | Robustez / diagnóstico |
|---|---|---|
| Resultado principal | `Vgross` | `Vnet` |
| Denominador macro | costos y fiscal space sobre `Y0` | PIB post-IA como sensibilidad etiquetada |
| Costo de política | costo bruto anual sobre `Y0` | costo neto incremental cuando `Cexist` es sustituible |
| Conversión fiscal | channel-based fiscal mode con frozen weights (único modo que representa los regímenes r0-r4 nativamente); los percentiles históricos disciplinan vía flag de plausibilidad | historical reduced-form positive-capture como corrida de robustez etiquetada |
| Adopción | anchored simulated adoption | full-score con AIPI; adopción observada si existe |
| Shock IA | `phi_Y_nom` | bridges TFP/LP alternativos |
| Gap digital | excluded-indicators (baseline); residualized solo robustez (muestra internacional, regla de 11.2) | alternative Gap |
| Informalidad | mecanismos separados: adopción (partición entre índice y techo si es la misma variable) + captura fiscal (`I_marg` por base, base o tasa) | adopción-only / fiscal-only como ablaciones |
| Deuda | guardrail separado | integrated debt-consistent specification |
| GMI | agregado + microdata si existe | `theta_target` cargado; focalización imperfecta |
| UBI | stress benchmark | no baseline policy |
| Monte Carlo | independent baseline por transparencia | rank-correlated y block-correlated stress |
| Plausibilidad fiscal | `MFCgross` vs percentiles históricos positivos | non-resource, excl. pandemia, ventanas 2010-/2015- |

Regla:

> La narrativa principal del paper debe basarse en la especificación primaria. Las variantes favorables solo pueden fortalecer la conclusión si no contradicen la especificación primaria.

---

# 3. Relación exacta con la base de datos

El documento `01_database_construction_plan.md` deja listas las tablas observadas, construidas y parametrizadas. Este documento empieza recién cuando existen, como mínimo, las siguientes tablas:

| Bloque | Tablas requeridas |
|---|---|
| Dimensiones | `dim_country`, `dim_policy`, `dim_ai_scenario`, `dim_fiscal_regime`, `dim_source` |
| Macro/fiscal | `macro_anchor`, `fiscal_anchor`, `debt_guardrail_anchor` |
| Pobreza/costos | `poverty_distribution_anchor`, `policy_parameter`, `policy_cost`, `policy_admin_transition_cost`, `gmi_estimation_status` |
| IA/adopción | `ai_preparedness_anchor`, `digital_gap_anchor`, `ai_exposure_anchor`, `frontier_benchmark_anchor` |
| Trabajo/fiscalidad | `labor_informality_anchor`, `labor_share_anchor`, `historical_capture_distribution`, `historical_capture_percentiles` |
| Trazabilidad | `assumption_registry`, `parameter_set`, `parameter_set_item`, `variable_source_map`, `data_quality_report` |

Regla metodológica:

> La base de datos entrega insumos. Este documento genera resultados con `run_id`, `model_version`, `parameter_set_id` y `dataset_version`.

Ninguna tabla de resultados puede existir sin esos identificadores.

---

# 4. Coverage matrix: claims del paper y pruebas empíricas

| Claim del paper | Módulo / variable | Test principal | Robustez |
|---|---|---|---|
| La factibilidad depende del umbral `V` | `fiscal_space_result` | `Vgross >= 1` | `Vnet`, buffers `xi` |
| Las políticas baratas cruzan antes | `policy_cost`, `fiscal_space_result` | ranking `PEN/MUT/GMI/PBI/UBI` | gross vs net cost |
| UBI es benchmark extremo | `dim_policy`, `policy_cost` | clasificación `stress_benchmark_only` | stress + r4 |
| La adopción productiva importa | `adoption_module` | `q_prod`, `T`, `g_AI_level` | threshold `q_prod_required` |
| La captura fiscal importa tanto como productividad | `fiscal_conversion_module` | `MFCgross`, regímenes `r0-r4` | historical reduced-form robustness run |
| La informalidad limita factibilidad | `labor_informality_anchor` | mecanismos separados declarados (adopción + fiscal) | adopción-only, fiscal-only |
| La historia fiscal disciplina el modelo | `historical_capture_percentiles` | `MFCgross <= P50/P75/P90` | non-resource, excl. pandemia |
| GMI puede ser más viable que UBI | `policy_cost`, `gmi_estimation_status` | GMI agregado/microdata | `theta_target` |
| El resultado no debe depender de una fuente | `diagnostic_result` | leave-one-source-out | source conflict flags |
| El resultado no debe ser artefacto mecánico | `diagnostic_result` | ICT placebo, negative controls | channel ablation |

---

# 5. Hipótesis y expectativas empíricas

Estas hipótesis no son hipótesis causales. Son hipótesis de factibilidad bajo escenarios.

## H1 — Gradiente de factibilidad por política

Las políticas con menor costo bruto deben cruzar el umbral antes que las políticas de mayor costo.

Orden esperado de dificultad fiscal:

$$
PEN/MUT < GMI < PBI < UBI.
$$

`UBI` debe tratarse como benchmark de estrés fiscal, no como política base recomendada.

## H2 — Preparación institucional y adopción productiva importan más que exposición total

La exposición total a IA no debe usarse como equivalente de productividad. El canal relevante es exposición productiva más adopción productiva.

La expectativa es que países con mayor preparación y menor fricción institucional generen mayor traducción doméstica del shock IA.

Matiz obligatorio: si `E_prod` usa el fallback regional común LAC (rango 0.08-0.14 idéntico para los cuatro países, `is_lac_fallback=TRUE`), la variación entre países de `T` proviene de preparación y adopción POR CONSTRUCCIÓN, y H2 no es testeable como hipótesis entre países en ese margen: se reporta como propiedad condicional del diseño, y solo se testea donde exista exposición país-específica.

## H3 — Alta informalidad reduce factibilidad por dos vías separadas

La informalidad puede afectar:

1. adopción productiva;
2. captura fiscal efectiva.

Son mecanismos separados y ambos operan en baseline; la partición obligatoria es dentro de adopción (índice vs techo) cuando la misma variable alimenta ambos márgenes, y en fiscal la penalización va en base o en tasa, nunca en ambas.

Hipótesis operativa:

> Perú y Colombia deberían mostrar mayor sensibilidad a la convención de informalidad que Chile.

## H4 — La factibilidad depende críticamente del régimen fiscal

El mismo shock IA puede no cruzar bajo `r0` pero sí cruzar bajo `r2`, `r3` o `r4`.

Regímenes:

| Régimen | Interpretación |
|---|---|
| `r0` | status quo |
| `r1` | mejor cumplimiento |
| `r2` | ampliación de base |
| `r3` | captura explícita de rentas IA |
| `r4` | reforma combinada |

## H5 — Cruces que requieren captura fiscal histórica extrema deben clasificarse como frágiles

Una celda puede tener `V >= 1`, pero si requiere `MFCgross > P90` de la distribución histórica positiva del país, no debe presentarse como factibilidad ordinaria.

---

# 6. Notación mínima usada en el diseño

| Símbolo | Definición |
|---|---|
| `i` | país |
| `p` | política social |
| `s` | escenario IA |
| `r` | régimen fiscal |
| `t` | año |
| `H` | horizonte de acumulación; baseline H=10, endpoint |
| `phi_raw` | shock IA en unidad original: TFP, LP o GDP-equivalent |
| `phi_Y_nom` | shock IA convertido a equivalente nominal de PIB |
| `T` | factor de traducción doméstica |
| `S_NDC` | score no-double-counting de traducción doméstica |
| `S_frontier` | benchmark frontier del escenario |
| `g_AI_level` | ganancia de nivel de PIB inducida por IA |
| `MFCgross` | captura fiscal marginal bruta |
| `MFCtilde_gross` | captura bruta neta de costos marginales equivalentes, si aplica |
| `fs_eff` | espacio fiscal efectivo inducido por IA |
| `c_gross` | costo bruto de política como % del PIB base `Y0` |
| `c_net` | costo neto incremental como % del PIB base `Y0` |
| `Vgross` | índice de factibilidad sobre costo bruto |
| `Vnet` | índice de factibilidad sobre costo neto; solo robustez |
| `xi` | buffer prudencial |
| `sPB` | ajuste por brecha de balance primario estabilizador |
| `F_fix` | costos fijos totales: admin neto, transición anualizada y leakage fijo |
| `R_req` | requerimiento fiscal total para cruzar el umbral |

---

# 7. Ecuaciones operativas del diseño

## 7.1 Conversión del shock IA

El shock crudo nunca entra directamente en las ecuaciones fiscales.

Primero se convierte a shock de PIB nominal equivalente:

$$
\phi^{Y,nom}_{s}=f(\phi^{raw}_{s,u},\kappa^{u\to Y},\pi^{AI,Y}).
$$

Regla:

> Todo resultado fiscal usa `phi_Y_nom`, nunca `phi_raw`.

## 7.2 Traducción doméstica del shock y horizonte de acumulación

El score baseline debe ser no-double-counting:

$$
S^{NDC}_{i,s,t}=\mathbf{1}\{q^{prod}_{i,s,t}>0,E^{prod}_{i,t}>0\}
(\tilde E^{prod}_{i,t})^{\beta}(\tilde q^{prod,num}_{i,s,t})^{\gamma}.
$$

$$
T_{i,s,t}=\min\left\{1,\frac{S^{NDC}_{i,s,t}}{S^{frontier}_{s,t}}\right\}.
$$

El objeto que se compara con costos recurrentes anuales es el objeto de NIVEL acumulado, no el flujo anual:

$$
g^{AI,level}_{i,s,H}=\prod_{\tau=1}^{H}\left(1+\phi^{Y,nom}_{s,\tau}T_{i,s,\tau}\right)-1,
$$

que con `phi` y `T` constantes se reduce a:

$$
g^{AI,level}_{i,s,H}=(1+\phi^{Y,nom}_{s}T_{i,s})^H-1.
$$

Convención endpoint del paper: la ganancia de nivel al horizonte `H` se interpreta como el incremento anual permanente de base fiscal disponible en el año endpoint, y los costos de política se miden o proyectan para ese mismo año endpoint.

Horizonte baseline: `H=10` (`t0=2024`, endpoint 2034), anclado a los horizontes de la literatura que disciplina los escenarios. Sensibilidad: `H` en `{5,15}`.

Convención de trayectoria congelada (static-structure), OBLIGATORIA en baseline: todos los primitivos estructurales — `T_{i,s}`, `phi_Y_nom_s`, AIPI, Gap digital, informalidad, tasas efectivas por canal y parámetros de adopción (los pesos `omega` y `lambda_AI` NO son observables 2024: se construyen por escenario según la regla temporal de 7.4.1 y quedan congelados una vez construidos) — se congelan en sus valores del año ancla 2024 (`data_harmonization_year`) durante los diez períodos. Bajo esta convención `g_AI_level = (1+phi*T)^H - 1` es EXACTA, no una aproximación. Única excepción: la demografía al endpoint (ratio de elegibilidad proyectado UN WPP), gobernada por la sección 10.9. Cualquier trayectoria anual variable (`T_t` recalculado, `phi_t` variable) es una corrida de sensibilidad etiquetada `trajectory_sensitivity` y NUNCA baseline: usar `T_2024` constante, `T_2034` constante o una senda anual produce ganancias acumuladas distintas, y la convención congelada-en-ancla es la declarada. Dirección de sesgo declarada: congelar `T` en su valor 2024 (adopción temprana baja) SUBESTIMA la ganancia endpoint frente a una senda de difusión donde `q_prod` crece hacia `q_use` durante la década (margen conservador); el compounding de 10 años es generoso en el margen de acumulación. Los dos sesgos interactúan y no se cancelan por construcción; `trajectory_sensitivity` (senda de difusión explícita con `lambda_q`) acota el primero por arriba. Esta fila entra al ledger de sesgos del reporte final, espejo del ledger de supuestos del paper.

La fórmula estática de un período:

$$
g=\phi^{Y,nom}T
$$

se usa SOLO como diagnóstico etiquetado `one-period static`, nunca como baseline: con shocks anuales de `0.0005-0.006` y `T<=1`, un solo año no puede financiar costos recurrentes y el resultado sería trivialmente infactible por construcción.

Regla:

> Si `qprod` se simula desde AIPI, el baseline no vuelve a multiplicar por AIPI dentro del score completo.

## 7.3 Adopción productiva

Baseline recomendado: **anchored simulated adoption**, salvo que exista medición directa comparable de adopción productiva.

Uso:

$$
q^{use}_{i,s,t}=\bar q_{i,t}\Lambda(\ell^q_{i,s,t}).
$$

$$
\ell^q_{i,s,t}=\mu_{i,s,t}+\nu_A A_{i,t}-\nu_I I^{adopt}_{i,t}-\nu_G Gap_{i,t}.
$$

Techo de adopción:

$$
\bar q_{i,t}=\max\{0,\min[1,1-\omega_I I^{ceiling}_{i,t}-\omega_G Gap_{i,t}]\}.
$$

Difusión productiva:

$$
q^{prod}_{i,s,t}=\min\{\bar q_{i,t},(1-\lambda_q)q^{prod}_{i,s,t-1}+\lambda_q q^{use}_{i,s,t}\}.
$$

Condición inicial y calibración del intercepto (obligatorias del paper; deben declararse en el replication file): (a) la condición inicial default es `q_prod_{t0} = q_use_target_adj_{t0}`, donde `q_use_target_adj` es el target proyectado al interior del soporte con `epsilon_mu`; `q_prod_{t0} = 0` se reporta SOLO como robustez conservadora etiquetada. (b) el intercepto `mu_{i,s,t0}` NO es un parámetro libre: se DERIVA por inversión logit para igualar `q_use_target_adj` dado `nu_A*A - nu_I*I - nu_G*Gap`, y queda fijo para `t>t0` (`mu_{i,s,t} = mu_{i,s,t0}`); el primitivo registrable es `q_use_target`, no `mu`. (c) bajo la convención de trayectoria congelada (7.2), `q_prod` permanece en su valor ancla; `lambda_q` opera solo en corridas `trajectory_sensitivity` y en la inversión de uso (7.7.6ter), cuya `q_prod_{t-1}` es el valor ancla declarado.

Lectura operativa ÚNICA del baseline congelado (resuelve la interacción con el Monte Carlo): como `mu` se re-invierte contra el `q_use_target` sorteado de cada draw, en baseline congelado `q_use_{t0} = q_use_target_adj` y `q_prod = q_use_target_adj` exactamente. Por tanto: (a) la incertidumbre de adopción del MC baseline opera SOLO vía `q_use_target`, el techo `q_bar = max{0, min[1, 1 - omega_I*I_ceiling - omega_G*Gap]}` (draws de `omega_I`, `omega_G`, `I`, `Gap`) y la proyección del target al soporte; (b) los draws de `nu_A`, `nu_I`, `nu_G` y `lambda_q` son INERTES en el baseline congelado (se cancelan por la inversión de mu): operan únicamente en `trajectory_sensitivity`, en el modo structural-intercept de robustez y en las inversiones 7.7.5-7.7.6ter; (c) la adopción baseline es invariante al escenario salvo shifter de escenario explícitamente calibrado (regla del paper); los escenarios operan vía `phi_s` y `lambda_AI_s`.

Nota de transparencia: para países sin encuesta directa de adopción de firmas, `q_use_target` es un supuesto calibrado con soporte declarado; en ese caso la incertidumbre de adopción del Monte Carlo baseline es esencialmente un prior declarado, no una distribución muestral, y el texto del paper debe describirla así.

Regla:

> Si `I` o `Gap` aparecen en el índice logístico y en el techo de adopción, su efecto debe particionarse o etiquetarse. No se aplica el castigo completo dos veces.

## 7.4 Captura fiscal

Se permiten dos modos, pero no simultáneamente como si fueran sumables.

### Modo primario — Channel-based fiscal mode

Alineado con la declaración del paper: todas las columnas `V` se computan en modo channel-based, porque es el único modo que representa los regímenes fiscales `r0-r4` nativamente; el histórico no contiene impuestos a rentas de IA ni reformas no ocurridas. Se construye:

$$
MFC^{gross}_{i,s,r,t}=\omega^L\tau^{L,eff}+\omega^{K,net}\tau^{K,eff}+\omega^C\tau^{C,eff}+\lambda^{AI}\tau^{AI,eff}.
$$

Convención frozen-weight: los pesos `omega`, `lambda_AI` y `MFCtilde` quedan CONGELADOS en el escenario evaluado para las fórmulas cerradas de inversión. Si las bases de canal se recomputan endógenamente al variar el shock, los umbrales se resuelven numéricamente sobre la función de ingresos por canal y la fórmula cerrada se reporta solo como diagnóstico frozen-weight.


### 7.4.1 Construcción de los pesos de canal (frozen weights)

Los pesos NO se asumen: se construyen desde los bloques del paper con insumos del plan 01 y quedan congelados en el escenario evaluado.

- `omega_L = (Delta_W_AI / Y0) / g_AI_level`, del bloque labor-share: `Delta_W_AI/Y0 = LS'(1+g) - LS`, con `LS'` del ajuste parcial en logit (parámetros `delta_s`, `psi_s`, `zeta_s`, `lambda_LS`, `RST`, `E_auto`, `E_aug`; insumos: `labor_share_anchor`, `ai_exposure_anchor`).
- `omega_K = (Delta_Pi_AI_dom / Y0) / g_AI_level`, de la cadena de capital: `Delta_NLS -> chi_Kbase -> chi_dom, psi_shift`. Bajo la convención subset de rentas IA se usa `omega_K_net = omega_K - lambda_AI_Kbase` (rescalado a la base doméstica post-shifting).
- `omega_C = (Delta_C_AI_taxable / Y0) / g_AI_level`, del canal de consumo inducido: incrementos disponibles con `tau_L_disp`, `tau_K_disp`, `tau_R_disp`; propensiones `mpc_W`, `mpc_Pi`, `mpc_R`; `theta_R_dom`; importaciones `m_M`; exenciones `exempt_C` (en base O en tasa, nunca ambas).
- `lambda_AI` se declara por escenario con convención explícita subset/adicional.

Regla de construcción temporal: los `Delta` del numerador y el `g_AI_level` del denominador se evalúan AMBOS al endpoint del escenario con estructura 2024 congelada (el mismo shock acumulado en numerador y denominador); el cociente solo está definido con shock (`g_AI_level > 0`) — en 2024 sin shock es 0/0 y NO debe computarse. Los pesos son objetos de escenario: se construyen una vez por escenario y quedan congelados (frozen weights) para fórmulas cerradas e inversiones.

Todos estos primitivos entran a `calibrated_parameter_registry` y al `parameter_set` del baseline.

### 7.4.2 Companion de erosión conductual (obligatorio para r>=1)

Los regímenes r>=1 son cotas superiores mecánicas: suben tasas y captura sin costo conductual. El companion obligatorio usa la ecuación del paper de base gravable erosionada: `B_j_taxable = B_j * (1 - epsilon_ero_j * tau_j_eff_r)`, donde `epsilon_ero_j` captura evasión, elusión, relocalización y respuestas de reporte NO incorporadas ya en la cadena de capital baseline. Operacionalmente, en la corrida companion cada término de canal de la fórmula de 7.4 se reemplaza por: `omega_j * (1 - epsilon_ero_j * tau_j_eff_r) * tau_j_eff_r` para j in {L, K_net, C}, y el canal de rentas por `lambda_AI * (1 - epsilon_ero_AI * tau_AI_eff) * tau_AI_eff` (las rentas IA son la base más móvil del menú). Reglas: (a) `epsilon_ero_j = 0` en el baseline r0 (statu quo); (b) sin valor puntual preferido: grilla declarada o PERT acotada, registrada en `calibrated_parameter_registry`; (c) restricción de positividad `epsilon_ero_j * tau_j < 1`; (d) ningún resultado titular con r>=1 se reporta sin esta corrida (regla 11 de la sección 21 y `test_erosion_companion`).

### Modo de disciplina y robustez — Historical reduced-form mode

$$
MFC^{hist,gross}_{i,t}=\frac{\Delta Revenue_{i,t}}{\Delta GDP_{i,t}}.
$$

Cumple dos funciones: (a) disciplina de plausibilidad para TODAS las celdas, porque el MFC construido por canales se clasifica contra `P50/P75/P90` históricos; (b) corrida de robustez etiquetada, principalmente para `r0`.

Regla:

> En el modo channel-based, `MFCgross` se construye desde canales y los percentiles históricos se usan solo para clasificación de plausibilidad. En la corrida histórica de robustez, `MFCgross` se dibuja de la historia y las tasas por canal son descriptivas. No se promedian ni se suman ambos. Los dos modos nunca se mezclan dentro de una misma celda.

## 7.5 Espacio fiscal efectivo

Objeto principal:

$$
fs^{eff}_{i,p,s,r,t}=\widetilde{MFC}^{gross}_{i,s,r,t}g^{AI,level}_{i,s,t}-ac^{net,fix}_{i,p,s,r,t}-tr^{ann}_{i,s,r,t}-leak^{fix}_{i,s,r,t}.
$$

Si se usa una versión con costos marginales equivalentes:

$$
\widetilde{MFC}^{gross}=MFC^{gross}-ac^{ME}-tr^{ME}-leak^{ME}.
$$

Regla:

> Un costo puede ser fijo o marginal-equivalente, pero no ambos al mismo tiempo.

## 7.6 Umbral principal

$$
V^{gross}_{i,p,s,r,t}=\frac{fs^{eff}_{i,p,s,r,t}}{c^{gross}_{i,p,t}}.
$$

Cruce básico:

$$
V^{gross}_{i,p,s,r,t}\geq 1.
$$

Con buffer:

$$
V^{gross}_{i,p,s,r,t}\geq 1+\xi,
\qquad
\xi\in\{0,0.05,0.10,0.25,0.50\}.
$$

Guardrail de deuda:

$$
fs^{eff}_{i,p,s,r,t}\geq (1+\xi)c^{gross}_{i,p,t}+sPB^+_{i,t},
$$

donde:

$$
sPB^+_{i,t}=\max\{0,sPB_{i,t}\}.
$$

## 7.7 Fórmulas cerradas de threshold inversion

$$
F^{fix}_{i,p,s,r,t}=ac^{net,fix}_{i,p,s,r,t}+tr^{ann}_{i,s,r,t}+leak^{fix}_{i,s,r,t}.
$$

El requerimiento BASELINE contable y el requerimiento DEBT-CONSISTENT son objetos separados:

$$
R^{req}_{i,p,s,r,t}(\xi)=(1+\xi)c^{gross}_{i,p,t}+F^{fix}_{i,p,s,r,t},
$$

$$
R^{req,DC}_{i,p,s,r,t}(\xi)=R^{req}_{i,p,s,r,t}(\xi)+sPB^+_{i,t}.
$$

Regla del paper: el guardrail de deuda es una capa fuerte separada, no el benchmark de autofinanciamiento marginal. Toda inversión se computa dos veces, baseline y debt-consistent, y se reporta en columnas separadas. La tabla `threshold_inversion_result` debe añadir el campo `requirement_basis` con valores `baseline` / `debt_consistent`.

Validez de las fórmulas cerradas: valen bajo la convención frozen-weight, con pesos congelados en el escenario evaluado, o en la corrida histórica reduced-form. Si las bases de canal se recomputan endógenamente, el umbral se resuelve numéricamente y la fórmula cerrada es solo diagnóstico. Para horizontes acumulados, la inversión de `T` usa:

$$
T^{req,H}=\frac{\left(1+R^{req}/\widetilde{MFC}^{gross}\right)^{1/H}-1}{\phi^{Y,nom}},
$$

El chequeo `frontier_exceeds_one` aplica igualmente a `T^{req,H}`: como `T = min{1, S/S_frontier}` está acotado en 1, si `T^{req,H} > 1` ningún nivel de adopción o exposición puede cruzar y las inversiones aguas abajo (`S_required`, `q_required`, `E_required`) se reportan solo con ese flag activo.

y la estática solo en corridas etiquetadas `one-period static`.

### 7.7.1 Crecimiento IA requerido

Si:

$$
\widetilde{MFC}^{gross}_{i,s,r,t}>0,
$$

entonces:

$$
g^{AI,required}_{i,p,s,r,t}=\frac{R^{req}_{i,p,s,r,t}(\xi)}{\widetilde{MFC}^{gross}_{i,s,r,t}}.
$$

Si:

$$
\widetilde{MFC}^{gross}_{i,s,r,t}\leq 0
\quad \text{and} \quad
R^{req}_{i,p,s,r,t}(\xi)>0,
$$

la celda recibe:

```text
impossibility_reason = noncomputable_mfc_zero_or_negative
```

### 7.7.2 Captura fiscal requerida

Si:

$$
g^{AI,level}_{i,s,t}>0,
$$

entonces:

$$
MFC^{gross,required}_{i,p,s,r,t}=
\frac{R^{req}_{i,p,s,r,t}(\xi)}{g^{AI,level}_{i,s,t}}
+ac^{ME}+tr^{ME}+leak^{ME}.
$$

Las deducciones marginales-equivalentes se devuelven al invertir porque la condición de cruce es sobre MFCtilde = MFC - ME: sin ellas, la fórmula entrega el objeto tilde requerido, no el gross. El objeto gross es el ÚNICO comparable con los percentiles históricos (gate mfc_object_matches_percentile_object de la Fase 5). Cuando no hay costos ME, ambos coinciden.

Si:

$$
g^{AI,level}_{i,s,t}\leq 0,
$$

la celda recibe:

```text
impossibility_reason = noncomputable_g_ai_zero_or_negative
```

### 7.7.3 Traducción doméstica requerida

Esta subsección corresponde a la versión estática `one-period`; el baseline acumulado usa `T^{req,H}`.

Si:

$$
\phi^{Y,nom}_{s}>0,
$$

entonces:

$$
T^{required}_{i,p,s,r,t}=\frac{g^{AI,required}_{i,p,s,r,t}}{\phi^{Y,nom}_{s}}.
$$

Si:

$$
T^{required}_{i,p,s,r,t}>1,
$$

la celda recibe:

```text
impossibility_reason = frontier_exceeds_one
```

Si:

$$
\phi^{Y,nom}_{s}\leq 0,
$$

la celda recibe:

```text
impossibility_reason = noncomputable_phi_zero
```

### 7.7.4 Score doméstico requerido

Dado:

$$
T_{i,s,t}=\min\left\{1,\frac{S^{NDC}_{i,s,t}}{S^{frontier}_{s,t}}\right\},
$$

el score doméstico requerido es:

$$
S^{required}_{i,p,s,r,t}=T^{req,H}_{i,p,s,r,t}S^{frontier}_{s,t}.
$$

En corridas `one_period_static` se usa el `T` requerido estático.

### 7.7.5 Adopción productiva requerida

Con el gate y el piso numérico explícitos:

$$
S^{NDC}_{i,s,t}=\mathbf{1}\{q^{prod}>0,E^{prod}>0\}(\tilde E^{prod}_{i,t})^{\beta}(\tilde q^{prod,num}_{i,s,t})^{\gamma},
\qquad \tilde q^{prod,num}=\epsilon+(1-\epsilon)q^{prod}.
$$

Primero el umbral en escala normalizada:

$$
\tilde q^{prod,required}=\left(\frac{S^{required}}{(\tilde E^{prod})^{\beta}}\right)^{1/\gamma}.
$$

Luego la transformación inversa del piso a escala ORIGINAL:

$$
q^{prod,required,raw}=\frac{\tilde q^{prod,required}-\epsilon}{1-\epsilon},
\qquad
q^{prod,required}=\max\{0,q^{prod,required,raw}\}.
$$

Los diagnósticos se aplican al objeto en escala original: existencia si:

$$
0<q^{prod,required}\leq \bar q.
$$

Si `q_prod_required > q_bar`, entonces:

```text
impossibility_reason = adoption_ceiling_impossible
```

Si `q_prod_required = 0` con requerimiento positivo y el cruce falla al fijar `epsilon=0`:

```text
epsilon_floor_driven = TRUE
```

Esta es la definición operacional única del flag.

### 7.7.6 Exposición requerida

Alternativamente, si se invierte por exposición:

$$
\tilde E^{prod,required}_{i,p,s,r,t}
=
\left(\frac{S^{required}_{i,p,s,r,t}}{(\tilde q^{prod}_{i,s,t})^{\gamma}}\right)^{1/\beta}.
$$

La transformación inversa del piso se aplica igual que en la inversión de adopción: `E_prod_required = max{0, (tilde_E_prod_required - epsilon_E) / (1 - epsilon_E)}`, que devuelve el requerimiento al espacio natural de exposición. El chequeo de techo `tilde_E_prod_required > 1` es equivalente en ambos espacios. Si el requerimiento cae al piso con requerimiento positivo, aplica el mismo flag `epsilon_floor_driven` de 7.7.5.

Si:

$$
\tilde E^{prod,required}_{i,p,s,r,t}>1,
$$

la celda recibe:

```text
impossibility_reason = exposure_ceiling_impossible
```

Las inversiones de exposición y de preparación (`exposure_required`, `aipi_required`) se reportan SOLO como stress tests, según el paper; `aipi_required` no tiene fórmula cerrada: se obtiene por inversión numérica del módulo de adopción.

### 7.7.6bis Captura de rentas IA requerida

Con `MFC_base = MFCtilde_gross - lambda_AI * tau_AI_eff`, canales sin el término de rentas:

$$
\tau^{AI,eff,required}=\max\left\{0,\frac{R^{req}/g^{AI,level}-\widetilde{MFC}^{base,gross}}{\lambda^{AI}}\right\},
$$

válido si `g_AI_level > 0` y `lambda_AI > 0`.

La tasa estatutaria requerida es:

$$
\tau^{AI,required}=\frac{\tau^{AI,eff,required}}{\chi^{AI}},
$$

si `chi_AI > 0`. Si `chi_AI = 0` con requerimiento positivo:

```text
impossibility_reason = ai_rent_capture_impossible
```

Si `tau_required` excede la cota declarada, efectiva o estatutaria, la celda queda infeasible por el canal de rentas.

### 7.7.6ter Uso productivo requerido

Con `lambda_q > 0`:

$$
q^{use,required}=\max\left\{0,\frac{q^{prod,required}-(1-\lambda_q)q^{prod}_{t-1}}{\lambda_q}\right\}.
$$

Si `lambda_q = 0`, la inversión de uso no está definida. Si `q_use_required > q_bar`:

```text
impossibility_reason = use_ceiling_impossible
```

### 7.7.7 Flags obligatorios de threshold inversion

| Flag | Cuándo se activa |
|---|---|
| `noncomputable_mfc_zero_or_negative` | `MFCtilde_gross <= 0` con requerimiento fiscal positivo |
| `noncomputable_g_ai_zero_or_negative` | `g_AI_level <= 0` |
| `noncomputable_phi_zero` | `phi_Y_nom <= 0` |
| `adoption_ceiling_impossible` | `q_prod_required > q_bar` |
| `frontier_exceeds_one` | `T_required > 1` |
| `exposure_ceiling_impossible` | `Eprod_required > 1` |
| `exposure_zero_impossible` | `Eprod <= 0` al invertir por exposición |
| `epsilon_floor_driven` | el resultado depende del piso numérico `epsilon` |
| `requirement_already_covered` | el baseline ya cruza el umbral con buffer |
| `ai_rent_capture_impossible` | `lambda_AI <= 0`, o `chi_AI = 0` con requerimiento positivo, o `tau_required` excede la cota declarada |
| `use_ceiling_impossible` | `q_use_required > q_bar` |
| `use_inversion_undefined` | `lambda_q = 0` |

---

# 8. Diseño de corridas

## 8.1 Llave mínima de toda corrida

Toda tabla de resultados debe tener:

| Campo | Uso |
|---|---|
| `run_id` | identifica la corrida |
| `model_version` | versión del código/modelo |
| `horizon_H` | horizonte acumulado usado en la corrida |
| `static_or_accumulated` | `accumulated_endpoint` / `one_period_static` |
| `dataset_version` | versión de base usada |
| `parameter_set_id` | set de supuestos |
| `country_id` | país |
| `policy_id` | política |
| `scenario_id` | escenario IA |
| `regime_id` | régimen fiscal |
| `anchor_year` | año de anclaje (2024) |
| `endpoint_year` | año de evaluación (anchor_year + H) |

## 8.2 Celdas base

La grilla principal es:

$$
PER,CHL,COL,MEX \times PEN,MUT,GMI,PBI,UBI \times low,mid,high,stress \times r0,r1,r2,r3,r4 \times \{anchor\_year=2024, H=10\}.
$$

Número base de celdas:

$$
4\times5\times4\times5=400.
$$

Convención de años, explícita para evitar comparar objetos de años distintos:
- `anchor_year = 2024`: año de anclaje de datos y calibración (t0).
- `endpoint_year = 2034`: año de evaluación (anchor_year + H).
- `cost_year = endpoint_year`: los costos de política se proyectan al endpoint (convención de 10.9).
- `data_harmonization_year = 2024`: año de armonización de la base (plan 01).
El numerador (`g_AI_level` acumulado) y el denominador de costos se evalúan AMBOS en `endpoint_year`;
comparar g acumulado a 2034 contra costos 2024 es un error de implementación y activa hard_fail.
La versión estática un-período se corre solo como diagnóstico etiquetado.

## 8.3 No result without audit

Regla dura:

> No table or figure can be exported unless `run_readiness_flag = TRUE` and all hard-fail checks in `double_counting_audit` pass.

Implementación:

```text
if run_readiness_flag != TRUE:
    stop_export()

if any(double_counting_audit.severity == "hard_fail" and passes_check == FALSE):
    stop_export()
```

Esta regla aplica a tablas, figuras, heatmaps, Monte Carlo summaries, threshold inversion y outputs de appendix.

---

# 9. Calibración formal de parámetros no observados

Todo parámetro no observado debe estar documentado antes de entrar a una corrida baseline, robustez o Monte Carlo.

## 9.1 Regla dura

> Ningún parámetro calibrado entra al baseline si no está en `assumption_registry`, `parameter_set` y `parameter_set_item`.

## 9.2 Tabla mínima: `calibrated_parameter_registry`

| Campo | Qué debe contener |
|---|---|
| `parameter_name` | `nu_A`, `nu_I`, `omega_I`, `lambda_ai`, `tau_ai_eff`, etc. |
| `module` | adopción / fiscal / costos / leakage / transición / GMI |
| `baseline_value` | valor central usado en primary specification |
| `low_value` | mínimo defendible |
| `high_value` | máximo defendible |
| `distribution` | pert / triangular / beta / uniform / empirical / discrete |
| `truncation_rule` | rango admisible y regla de truncación |
| `source_id` | paper, institución, fuente empírica o juicio calibrado |
| `is_observed` | TRUE/FALSE |
| `is_scenario` | TRUE/FALSE |
| `is_structural_unobserved` | TRUE/FALSE |
| `sensitivity_level` | baja / media / alta |
| `justification` | por qué el rango es defendible |
| `double_counting_note` | si se vincula con AIPI, Gap, informalidad o MFC |
| `included_in_primary` | TRUE/FALSE |
| `parameter_set_id` | set compatible |

## 9.3 Parámetros que no pueden quedar escondidos en el código

| Módulo | Parámetros mínimos |
|---|---|
| Adopción | `nu_A`, `nu_I`, `nu_G`, `omega_I`, `omega_G`, `lambda_q`, `mu` (derivado por inversión logit, no libre; el primitivo es `q_use_target`), `q_use_target`, `epsilon` (piso técnico), `epsilon_mu` (piso logit) |
| Traducción doméstica | `beta`, `gamma`, `S_frontier`, normalizaciones de `Eprod` y `qprod` |
| Shock IA | `phi_raw`, `kappa_to_y`, `pi_ai_y`, `phi_Y_nom` |
| Fiscal | `MFCgross`, `lambda_ai`, `tau_ai_eff`, `tau_L_eff`, `tau_K_eff`, `tau_C_eff`, `rho_L`, `rho_K`, `rho_C`, `epsilon_ero` |
| Canales: labor share | `LS`, `E_auto`, `E_aug`, `RST`, `delta_s`, `psi_s`, `zeta_s`, `lambda_LS` |
| Canales: capital | `chi_Kbase`, `chi_dom`, `psi_shift`, `lambda_AI_Kbase` |
| Canales: consumo | `mpc_W`, `mpc_Pi`, `mpc_R`, `m_M`, `exempt_C`, `theta_R_dom`, `tau_L_disp`, `tau_K_disp`, `tau_R_disp` |
| Leakage | `leak_fix`, `leak_me`, profit shifting, ownership leakage |
| Costos | `admin_cost_new`, `admin_savings_existing`, `transition_horizon`, `transition_discount_rate` |
| GMI | `chi_gmi`, `theta_target`, poverty-gap convention, focalización ideal/cargada |
| Deuda | `sPB`, regla de balance primario estabilizador |

---


# 10. Metodología de asignación de valores y umbrales

Esta sección fija la regla de entrada de valores al modelo. Su función es evitar que los resultados dependan de números convenientes, supuestos escondidos o umbrales elegidos después de ver resultados.

Regla de precedencia: las fórmulas de la sección 7 (ecuaciones operativas) gobiernan; los re-enunciados de esta sección son guías de asignación y, en caso de discrepancia, se corrigen contra la sección 7.

La regla general es:

> Ningún valor escalar entra al baseline solo porque es conveniente. Todo valor debe clasificarse como observado, construido, disciplinado por literatura, calibrado o stress; debe tener fuente o justificación; debe tener unidad; debe indicar si pertenece a la especificación primaria, robustez o diagnóstico de stress; y debe quedar registrado antes de correr resultados.

## 10.1 Principio de separación

La asignación de valores debe distinguir cinco objetos distintos:

| Objeto | Pregunta que responde | Dónde se registra | Puede entrar al baseline |
|---|---|---|---|
| Dato observado | ¿Qué dice una fuente pública? | `variable_source_map`, `data_quality_report` | Sí, si pasa auditoría |
| Variable construida | ¿Qué sale de una fórmula mecánica? | tabla procesada + script + fórmula | Sí, si tiene trazabilidad |
| Parámetro normativo de política | ¿Qué beneficio/elegibilidad define la política? | `policy_parameter` | Sí, si la regla está documentada |
| Parámetro calibrado | ¿Qué valor asumimos porque no es observado directamente? | `assumption_registry`, `parameter_set_item` | Sí, solo si tiene soporte y rango |
| Valor stress | ¿Qué caso extremo se usa para frontera o benchmark? | `assumption_registry` con `stress_flag=TRUE` | No, salvo que el bloque sea explícitamente stress |

Regla práctica:

> Datos, parámetros y resultados no deben vivir en la misma tabla lógica. Los datos observados tienen `dataset_version`; las corridas tienen `run_id`; los supuestos tienen `assumption_id` y `parameter_set_id`.

## 10.2 Jerarquía para asignar valores

Cuando exista más de una forma de asignar un valor, se usa esta jerarquía:

| Prioridad | Tipo de asignación | Ejemplo | Uso |
|---:|---|---|---|
| 1 | Observado armonizado | PIB, población, tax/GDP, AIPI publicado | Baseline |
| 2 | Observado nacional oficial | informalidad 2024 nacional, gasto social nacional | Baseline si mejora precisión y está documentado |
| 3 | Construido mecánicamente | `policy_cost`, `MFC_hist`, percentiles históricos | Baseline si la fórmula está cerrada |
| 4 | Literatura / paper-disciplined | rangos de `phi_raw`, bridges TFP/LP, exposición IA | Baseline o robustez según especificación |
| 5 | Calibrado con soporte | `q_prod`, `lambda_ai`, leakage, costos administrativos no observados | Baseline solo con rango y sensibilidad |
| 6 | Stress / frontera | shock disruptivo, reforma fiscal combinada extrema | Stress, no baseline |

Si una variable puede construirse desde datos observados, no debe reemplazarse por juicio calibrado. Si el juicio calibrado es inevitable, debe declararse como tal.

## 10.3 Campos obligatorios para cada valor escalar

Toda variable o parámetro que entre a una corrida debe tener, como mínimo:

| Campo | Descripción |
|---|---|
| `name` | nombre exacto del parámetro o variable |
| `module` | macro / costo / adopción / fiscal / deuda / GMI / Monte Carlo |
| `value_type` | observed / constructed / policy_parameter / calibrated / stress |
| `unit` | porcentaje del PIB, tasa, índice 0-1, moneda local, USD, etc. |
| `baseline_value` | valor central usado en primary specification |
| `low_value` | límite inferior defendible |
| `high_value` | límite superior defendible |
| `support_type` | source / formula / literature / calibrated_judgment / stress |
| `source_id` | fuente o paper que disciplina el valor |
| `formula_id` | fórmula si es construido |
| `distribution` | fixed / empirical / pert / triangular / beta / uniform / discrete |
| `truncation_rule` | regla de límites admisibles |
| `primary_spec_flag` | TRUE si entra al baseline |
| `robustness_flag` | TRUE si entra solo a robustez |
| `stress_flag` | TRUE si es stress |
| `double_counting_risk` | none / AIPI_gap / informality / fiscal / cost / leakage |
| `audit_status` | pass / soft_warning / robustness_only / hard_fail |

Regla de distribución:

> La PERT acotada es la distribución BASELINE del paper para parámetros `low-central-high`; triangular y truncated-uniform son solo robustez.

Regla dura:

> Ningún valor con `audit_status = hard_fail` puede aparecer en una tabla o figura exportada.

## 10.4 Asignación de shocks de IA

El shock que entra a las ecuaciones fiscales debe ser siempre `phi_Y_nom`. Nunca debe entrar `phi_raw` directamente.

Secuencia obligatoria:

$$
\phi^{raw}_{s} \rightarrow \phi^{Y,real}_{s} \rightarrow \phi^{Y,nom}_{s}.
$$

Donde:

$$
\phi^{Y,real}_{s}=\kappa_{s}\phi^{raw}_{s},
$$

$$
\phi^{Y,nom}_{s}=(1+\phi^{Y,real}_{s})(1+\pi^{AI,Y}_{s})-1.
$$

La forma aditiva `phi_real + pi` es solo aproximación de tasas pequeñas y no se usa como ecuación de asignación.

Reglas:

| Caso | Tratamiento |
|---|---|
| `phi_raw` viene como TFP | aplicar bridge `kappa_TFP_to_Y` |
| `phi_raw` viene como LP | aplicar bridge `kappa_LP_to_Y` |
| `phi_raw` ya viene como GDP/Y | `kappa=1` salvo ajuste nominal explícito |
| shock disruptivo | stress, no baseline |
| bridge alternativo | robustez, no primary si cambia unidad base |

Hard fail:

> Usar `phi_raw` directamente como si fuera `phi_Y_nom` detiene el baseline.

## 10.5 Asignación de adopción productiva

La adopción productiva `q_prod` no debe tratarse como dato observado puro. Es un parámetro/modelo anclado por datos de preparación, uso digital, informalidad, brecha digital y exposición productiva.

Baseline recomendado:

$$
q^{prod}_{i,s,t}=f(A_i,Gap_i,I_i,q^{use}_{i,t};\nu_A,\nu_G,\nu_I,\lambda_q,\mu).
$$

Reglas:

| Elemento | Regla baseline | Robustez |
|---|---|---|
| AIPI | publicado, no reconstruido | reconstrucción geométrica |
| Gap digital | excluded-indicators (baseline); residualized solo robustez (muestra internacional, regla de 11.2) | Gap alternativo |
| Informalidad | mecanismos separados: adopción (partición entre índice y techo si es la misma variable) + captura fiscal (`I_marg` por base, base o tasa) | adopción-only / fiscal-only como ablaciones |
| `q_use` | ancla de uso digital/empresarial si existe | proxy ICT |
| `q_prod` | valor simulado anclado | threshold inversion |

Condiciones de soporte:

$$
0\leq q^{prod}_{i,s,t}\leq \bar{q}_{i,s,t}\leq 1.
$$

Si la inversión de umbral exige:

$$
q^{prod,required}_{i,p,s,r,t}>\bar{q}_{i,s,t},
$$

la celda debe marcarse como:

```text
adoption_ceiling_impossible
```

## 10.6 Asignación de exposición productiva y frontier benchmark

La exposición productiva debe entrar como capacidad de transformar el shock de IA en producto doméstico, no como shock fiscal directo.

Puntaje doméstico mínimo:

$$
S^{NDC}_{i,s,t}=\mathbf{1}\{q^{prod}_{i,s,t}>0,E^{prod}_{i,t}>0\}\left(\widetilde{E}^{prod}_{i,t}\right)^{\beta}\left(\widetilde{q}^{prod,num}_{i,s,t}\right)^{\gamma}.
$$

Factor de traducción:

$$
T_{i,s,t}=\min\left\{1,\frac{S^{NDC}_{i,s,t}}{S^{frontier}_{s,t}}\right\}.
$$

Shock doméstico inducido:

$$
g^{AI,level}_{i,s,H}=\prod_{\tau=1}^{H}\left(1+\phi^{Y,nom}_{s,\tau}T_{i,s,\tau}\right)-1,
$$

de acuerdo con la convención acumulada de la sección 7.2.

Reglas:

- `S_frontier` debe pertenecer a la misma población de referencia usada para estimar `phi_s`.
- No se recalcula `S_frontier` dentro de la celda invertida.
- Usar el mejor país mundial como frontier si el shock proviene de promedio OCDE puede descontar dos veces la adopción; solo se permite como robustez conservadora.
- Si `T_required > 1`, la celda se marca como `frontier_exceeds_one`.

## 10.7 Asignación de captura fiscal histórica

La captura fiscal histórica reduced-form cumple dos funciones: disciplina de plausibilidad (percentiles) para el modo primario channel-based, y corrida de robustez etiquetada.

Métrica principal:

$$
MFC^{hist,gross}_{i,t}=\frac{\Delta Revenue_{i,t}}{\Delta GDP_{i,t}}.
$$

Reglas de asignación:

| Paso | Regla |
|---|---|
| Unidad | moneda local corriente |
| Ventana primaria | 2000-último año disponible |
| Robustez | 2010+, 2015+, sin 2020-2021 |
| Denominador | excluir o marcar `delta_gdp <= 0` |
| Outliers | winsorizar P1/P99 o reportar mediana robusta |
| Nivel de gobierno | no mezclar gobierno central y general dentro de una serie |
| Recursos naturales | reportar variante non-resource |

Percentiles obligatorios:

$$
P10_i,\quad P50_i,\quad P75_i,\quad P90_i,\quad p^-_i.
$$

`P10/P50/P90` alimentan la PERT condicional positiva. `p^-` es la proporción histórica de años con captura negativa. La PERT positiva es el benchmark CONDICIONAL; la mezcla de dos componentes, negativa con probabilidad `p^-` y positiva con `1-p^-`, es el benchmark INCONDICIONAL. Regla del paper: todo claim de expected feasibility usa la mezcla incondicional o se declara explícitamente condicional a años de captura positiva. Las tablas baseline reportan ambos.

Interpretación:

| Captura usada o requerida | Clase |
|---|---|
| `MFC <= P50` | fiscalmente ordinaria |
| `P50 < MFC <= P75` | fiscalmente moderada |
| `P75 < MFC <= P90` | fiscalmente exigente |
| `MFC > P90` | fuera de soporte histórico |

Hard fail:

> Mezclar simultáneamente `MFC_hist` reduced-form con `MFC_channel` dentro de la misma celda primaria detiene el baseline.

## 10.8 Asignación de conversión fiscal por canales

El modo channel-based es la especificación primaria (alineado con la declaración del paper): es el único modo que representa los regímenes r1-r4 nativamente. Precisamente por eso sus reglas anti-flexibilidad son obligatorias y la historia fiscal lo disciplina desde afuera.

Regla de canales:

$$
MFC^{channel,gross}_{i,s,r,t}=\omega_L\tau_L^{eff}+\omega_K^{net}\tau_K^{eff}+\omega_C\tau_C^{eff}+\lambda^{AI}_{s}\tau^{AI,eff}_{i,r}.
$$

Bajo la convención subset de rentas IA (sección 7.4.1), el peso de capital es SIEMPRE `omega_K_net = omega_K - lambda_AI_Kbase` cuando el término `lambda_AI * tau_AI_eff` está activo: usar `omega_K` sin netear junto a `lambda_AI` duplica las rentas (regla del paper). Si las rentas son adicionales al canal K, `omega_K_net = omega_K`.

La renta de IA `lambda_AI` es un objeto de ESCENARIO económico y no lleva índice de régimen (regla del paper): la renta existe según el escenario; el régimen determina cuánto se captura, vía `tau_AI_eff` y `chi_AI`.

Las deducciones marginales-equivalentes (`ac_ME`, `tr_ME`, `leak_ME`) NO entran en el objeto gross: entran una sola vez vía `MFCtilde = MFC - ac_ME - tr_ME - leak_ME` (sección 7.5).

Reglas anti flexibilidad:

- `tau_L`, `tau_K`, `tau_C` deben salir de tasas efectivas observadas o de reglas de régimen predefinidas.
- `tau_AI_eff` solo puede ser positivo en regímenes con captura explícita de rentas IA.
- Si `MFC_channel > P90_i`, la celda se marca como `fiscally_extreme` salvo justificación de reforma estructural excepcional.
- No puede contarse `lambda_ai` dentro de profits y otra vez dentro de AI rents.

## 10.9 Asignación de costos de política

El costo principal del paper debe ser costo bruto sobre PIB base:

$$
c^{gross,0}_{i,p,t}=\frac{C^{gross}_{i,p,t}}{Y^0_{i,t}}.
$$

La versión neta es robustez:

$$
c^{net,0}_{i,p,t}=\frac{\max\{0,C^{gross}_{i,p,t}-C^{exist}_{i,p,t}\}}{Y^0_{i,t}}.
$$

Reglas:

| Política | Valor central | Regla de asignación |
|---|---|---|
| `PEN` | beneficio anual × población elegible | edad y monto explícitos |
| `MUT` | fracción de línea de pobreza × población cubierta | `eta_MUT` explícito |
| `GMI` | brecha de pobreza cubierta | agregado o microdata, nunca ambiguo |
| `PBI` | beneficio parcial × población objetivo | `eta_PBI` explícito |
| `UBI` | beneficio benchmark × población total | stress benchmark |

Hard fail:

> Restar pensiones contributivas o derechos adquiridos como `Cexist` detiene el baseline.

Convención de costos endpoint (H=10, endpoint 2034): (a) las poblaciones elegibles al endpoint usan proyecciones UN WPP variante media (crítico para `PEN`: el ratio 65+/población crece hacia 2034 en los cuatro países); (b) beneficios y líneas de pobreza siguen la `indexation_rule` declarada en `policy_parameter` — bajo indexación a línea de pobreza o PIB per cápita, los niveles monetarios se cancelan dentro de los ratios y lo que gobierna el costo es el ratio demográfico proyectado; (c) variante de sensibilidad etiquetada: estructura demográfica 2024 constante.

Fórmulas cerradas del costo endpoint (obligatorias; `Y0_2034` NUNCA se necesita en niveles):
- Políticas con elegibilidad demográfica (PEN con `age_threshold`, PBI/UBI sobre adultos, MUT si es etaria): `c_gross_{i,p,2034} = c_gross_{i,p,2024} × [(N_elig/N)_{2034}^{WPP} / (N_elig/N)_{2024}]`, porque bajo `indexation_rule` (línea de pobreza o PIB pc) el ratio beneficio/Y0pc es constante.
- GMI y políticas de brecha con estructura distributiva congelada 2024: `c_gross_{2034} = c_gross_{2024}` (mover pobreza/distribución es sensibilidad etiquetada).
- Costos administrativos, transición anualizada y leakage: constantes como % del PIB (estructura congelada).
- Guardrail de deuda: `sPB_2034 = sPB_2024` (anchors 2024; dinámica de deuda al endpoint solo como sensibilidad etiquetada).
Condición de validez de la cancelación: las fórmulas cerradas anteriores requieren `indexation_rule` en {poverty_line_growth, gdp_pc_growth}. Si `indexation_rule = wage_growth` (caso PEN con pensión mínima ligada a salarios) o `none`/`inflation`, los niveles NO se cancelan (salario != PIB pc). Convención baseline declarada para esos casos: crecimiento real de salarios aproximado por crecimiento real del PIB pc (restaura la cancelación como supuesto declarado, con nota de sesgo en el ledger); la senda salarial explícita se corre como sensibilidad etiquetada. La regla usada se registra por país-política en `policy_parameter.indexation_rule`.
Combinar `g_AI_level` acumulado a 2034 con ratios de costo 2024 SIN el ajuste demográfico activa el hard_fail de la sección 8.2.

## 10.10 Asignación específica de GMI

GMI debe reportarse en cuatro versiones cuando los datos lo permitan:

| Versión | Interpretación | Uso |
|---|---|---|
| `GMI_ideal_aggregate` | lower-bound mecánico | baseline mínimo, con advertencia |
| `GMI_loaded_aggregate` | agregado con `theta_target` | robustez conservadora |
| `GMI_ideal_microdata` | microsimulación paper-ready | baseline fuerte si existe |
| `GMI_loaded_microdata` | microdata + carga de focalización | robustez conservadora fuerte |

Regla de interpretación:

> El ranking favorable de GMI frente a UBI no debe interpretarse como superioridad operacional si solo se usa focalización ideal agregada.

Regla de reporte del paper: toda tabla de comparación o ranking ENTRE instrumentos debe incluir la columna GMI cargada con `theta_target` JUNTO a la ideal; la ideal sola nunca sostiene el ranking GMI-antes-que-UBI.

`theta_target` debe tener soporte explícito:

$$
\theta^{target}\in[1.0,1.5].
$$

Si se usa otro rango, debe justificarse y reportarse como sensibilidad.

## 10.11 Asignación de costos administrativos, transición y leakage fijo

Espacio fiscal efectivo:

$$
fs^{eff}_{i,p,s,r,t}=\widetilde{MFC}^{gross}_{i,s,r,t}g^{AI,level}_{i,s,t}-ac^{net,fix}_{i,p,s,r,t}-tr^{ann}_{i,s,r,t}-leak^{fix}_{i,s,r,t}.
$$

Reglas:

| Componente | Asignación |
|---|---|
| `admin_cost_new` | por política, no ratio uniforme |
| `admin_savings_existing` | cero si ya está incluido en `Cexist` |
| `transition_oneoff` | anualizar con horizonte y tasa explícitos |
| `transition_recurring` | anual, no anualizar otra vez |
| `leak_fix` | costo fijo separado de leakage marginal |

Hard fail:

> Descontar el mismo ahorro administrativo en `Cexist` y otra vez en `admin_savings_existing` detiene el baseline.

## 10.12 Asignación de umbrales estructurales

El umbral estructural central es único:

$$
V^{gross}_{i,p,s,r,t}\geq 1.
$$

Con buffer prudencial:

$$
V^{gross}_{i,p,s,r,t}\geq 1+\xi.
$$

Valores de `xi`:

| Uso | Valor |
|---|---:|
| baseline prudencial | 0.10 |
| sensibilidad baja | 0.05 |
| sensibilidad alta | 0.25 |
| sin buffer | 0.00, solo diagnóstico |

Regla:

> `V >= 1` mide cobertura contable. `V >= 1+xi` mide margen prudencial. No deben confundirse.

## 10.13 Asignación de umbrales de plausibilidad

Los umbrales de plausibilidad no definen la identidad contable; disciplinan la interpretación.

| Umbral | Función | Acción |
|---|---|---|
| `MFC <= P50` | soporte fiscal ordinario | puede ser `fiscally_ordinary` |
| `MFC <= P75` | soporte moderado | puede ser robusto si pasa otros gates |
| `MFC <= P90` | soporte exigente | condicional o demanding |
| `MFC > P90` | fuera de soporte histórico | no llamar robusto |
| `prob_v_ge_1_10 >= 0.75` | robustez probabilística (grilla declarada del paper: `{0.50, 0.75, 0.90}`) | puede apoyar `robustly_feasible` |
| `prob_v_ge_1 < 0.50` | fragilidad probabilística | no usar lenguaje robusto |
| `debt_guardrail_pass=TRUE` | consistencia fiscal mínima | requerido para robustez |
| `q_required <= q_bar` | adopción posible | si falla, imposible por adopción |
| `T_required <= 1` | no supera frontier | si falla, `frontier_exceeds_one` |

Regla:

> Un resultado puede cruzar `V >= 1` y aun así ser fiscalmente extremo, frágil o no reportable como robusto.

Base de probabilidad de clasificación: TODAS las probabilidades de las reglas de clase (`prob_v_ge_1*`, `prob_debt_consistent*`) usan `prob_basis = all_draw` — la más conservadora (draws inválidos o no computables cuentan como no-cruce) y la pi titular del paper. Las bases `basic_valid` y `support_valid` son diagnóstico de la cadena de validez y NUNCA cambian una clase.

## 10.14 Asignación de umbrales de inversión

Requerimiento fiscal bruto con buffer y costos fijos:

$$
F^{fix}_{i,p,s,r,t}=ac^{net,fix}_{i,p,s,r,t}+tr^{ann}_{i,s,r,t}+leak^{fix}_{i,s,r,t}.
$$

$$
R^{req}_{i,p,s,r,t}(\xi)=(1+\xi)c^{gross}_{i,p,t}+F^{fix}_{i,p,s,r,t}.
$$

El requerimiento debt-consistent se reporta separado:

$$
R^{req,DC}_{i,p,s,r,t}(\xi)=R^{req}_{i,p,s,r,t}(\xi)+sPB^+_{i,t}.
$$

Las inversiones se calculan dos veces, una con `requirement_basis = baseline` y otra con `requirement_basis = debt_consistent`.

Shock IA requerido:

$$
g^{AI,required}_{i,p,s,r,t}=\frac{R^{req}_{i,p,s,r,t}(\xi)}{\widetilde{MFC}^{gross}_{i,s,r,t}},
$$

si:

$$
\widetilde{MFC}^{gross}_{i,s,r,t}>0.
$$

Captura fiscal requerida:

$$
MFC^{gross,required}_{i,p,s,r,t}=
\frac{R^{req}_{i,p,s,r,t}(\xi)}{g^{AI,level}_{i,s,t}}
+ac^{ME}+tr^{ME}+leak^{ME},
$$

si:

$$
g^{AI,level}_{i,s,t}>0.
$$

Factor de traducción requerido con horizonte acumulado:

$$
T^{req,H}_{i,p,s,r,t}=\frac{\left(1+R^{req}_{i,p,s,r,t}(\xi)/\widetilde{MFC}^{gross}_{i,s,r,t}\right)^{1/H}-1}{\phi^{Y,nom}_{s,t}},
$$

si:

$$
\phi^{Y,nom}_{s,t}>0.
$$

La versión estática `T_required = g_AI_required / phi_Y_nom` solo se usa en corridas etiquetadas `one-period static`.

Puntaje doméstico requerido:

$$
S^{required}_{i,p,s,r,t}=T^{req,H}_{i,p,s,r,t}S^{frontier}_{s,t}.
$$

Adopción requerida, si:

$$
S_{i,s,t}=\left(\widetilde{E}^{prod}_{i,t}\right)^\beta\left(\widetilde{q}^{prod}_{i,s,t}\right)^\gamma,
$$

entonces:

$$
\widetilde{q}^{prod,required}_{i,p,s,r,t}=\left(\frac{S^{required}_{i,p,s,r,t}}{(\widetilde{E}^{prod}_{i,t})^\beta}\right)^{1/\gamma}.
$$

Los flags obligatorios y sus condiciones son los de la tabla canónica 7.7.7 (única fuente; no se duplica aquí para evitar drift entre copias).

## 10.15 Asignación de clasificación final país-política

La clasificación final no se asigna por una celda favorable aislada. Se asigna por regla agregada.

| Clase | Regla mínima |
|---|---|
| `robustly_feasible` | cruza en `mid` (los cruces en `low` cuentan a fortiori), con `r0-r2`, pasa `xi=0.10`, `MFCgross <= P75`, pasa deuda y `prob_v_ge_1_10 >= 0.75`; si el cruce depende de `r1` o `r2`, además debe sobrevivir el companion de erosión conductual (`epsilon_ero`) |
| `conditionally_feasible` | cruza solo en `high` (frontier feasible según el paper) o `stress`, o requiere `r3-r4`, o `P75 < MFCgross <= P90`; clase residual de la precedencia determinística de 18.2 |
| `fragile_feasible` | cruza `V >= 1`, pero falla deuda, depende de `MFC > P90`, o `prob_v_ge_1 < 0.50` |
| `not_feasible` | no cruza salvo supuestos extremos/no computables |
| `stress_benchmark_only` | `UBI`, salvo que pase criterios fuertes sin `stress+r4` |

Regla editorial:

> Si cruza solo con `stress+r4`, se debe escribir “conditional on extreme AI and combined reform”, no “feasible”.

## 10.16 Tabla de decisión: baseline, robustez o stress

| Elemento | Baseline | Robustez | Stress |
|---|---|---|---|
| `Vgross` | Sí | — | — |
| `Vnet` | No | Sí | — |
| costo bruto | Sí | — | — |
| costo neto incremental | No | Sí | — |
| `MFC_hist_positive` | No; siempre activo como disciplina de plausibilidad | Sí, corrida etiquetada + ventanas alternativas | — |
| `MFC_channel` | Sí, frozen weights | variantes de canal | reforma excepcional |
| `phi_Y_nom_mid` | Sí (escenario central) | bridges alternativos | — |
| `phi_Y_nom_high` | No como baseline: corre en la grilla y se etiqueta `frontier feasible` (regla del paper) | — | — |
| `phi_stress` | No | — | Sí |
| `q_prod_anchored` | Sí | fórmulas alternativas | — |
| Gap: excluded-indicators (baseline); residualized solo robustez (muestra internacional, regla de 11.2) | Sí | Gap alternativo | — |
| Colombia 2026 | No | Sí | — |
| GMI agregado ideal | Sí con advertencia | — | — |
| GMI cargado `theta_target` | No | Sí; obligatorio junto al ideal en rankings entre instrumentos | — |
| UBI | No como política base | benchmark | stress benchmark |

## 10.17 Output obligatorio de esta metodología

Antes de correr la Fase 2 o exportar cualquier resultado, deben existir:

```text
value_assignment_table
threshold_assignment_table
calibrated_parameter_registry
baseline_parameter_set
assumption_registry_complete_flag
threshold_rule_registry
run_readiness_flag
```

`value_assignment_table` debe permitir responder para cada número del modelo:

1. de dónde sale;
2. qué unidad tiene;
3. si es observado, construido o calibrado;
4. cuál es su soporte;
5. si entra al baseline o solo a robustez;
6. qué riesgo de doble conteo tiene;
7. qué audit status recibió.

`threshold_assignment_table` debe permitir responder para cada umbral:

1. qué decisión controla;
2. si es estructural, prudencial, histórico, probabilístico o computacional;
3. qué valor usa en baseline;
4. qué valores se usan en sensibilidad;
5. qué acción activa si falla.


# 11. Hard gates y auditoría de inputs

## 11.1 Tres niveles de control

| Nivel | Ejemplo | Acción |
|---|---|---|
| `hard_fail` | usar `phi_raw` directo; mezclar MFC histórico y canales; duplicar AIPI; usar Colombia 2026 como baseline 2024 | detener baseline |
| `soft_fail` | dato importante carried-forward; conflicto leve de fuente; ventana histórica corta | permitir con warning |
| `robustness_only` | Gap solapado no residualizado; Colombia 2026; AIPI reconstruido mezclado con publicado | excluir de baseline, permitir solo como robustez |

## 11.2 Checks mínimos de input audit

- todos los países son `PER`, `CHL`, `COL`, `MEX`;
- el baseline usa 2024;
- Colombia 2026 no entra al baseline salvo como robustez marcada;
- `policy_cost` tiene costo bruto y neto claramente separados;
- `GMI` indica si es agregado o microdata;
- `AIPI` publicado no se mezcla con reconstruido;
- `Gap` no reutiliza indicadores del AIPI sin residualizar;
- si se usa el Gap residualizado, la residualización se estima sobre la muestra internacional completa disponible del panel ITU/AIPI (todos los países con datos), NUNCA sobre los 4 países del estudio (`n=4` no identifica la proyección); el baseline usa el Gap de indicadores excluidos, que no requiere estimación; la muestra usada se registra en el manifest;
- `MFC_hist` usa un solo nivel de gobierno por país;
- `Cexist` no incluye pensiones contributivas ni derechos adquiridos;
- cada variable final tiene fuente, unidad y transformación;
- todo parámetro no observado está en `calibrated_parameter_registry`;
- todo resultado tiene `run_id`, `model_version`, `dataset_version` y `parameter_set_id`.
- el baseline es acumulado `H=10` con convención endpoint; toda corrida estática está etiquetada `one_period_static`;

## 11.3 Output del audit

- `input_audit_report`;
- `double_counting_audit`;
- `run_readiness_flag`;
- `hard_fail_count`;
- `soft_fail_count`;
- `robustness_only_count`.

---


# 12. Roadmap secuencial de ejecución

Esta sección convierte el protocolo metodológico en un plan operativo. La lógica es secuencial: una fase produce insumos, diagnósticos o calibraciones que habilitan la siguiente. No se debe saltar directamente al Monte Carlo, a las figuras finales o a la clasificación país-política sin haber pasado los gates previos.

## 12.1 Vista general de fases

| Fase | Nombre corto | Objetivo | Depende de | Output principal | Gate para avanzar |
|---:|---|---|---|---|---|
| 0 | `input_readiness` | Auditar si la base puede correr el modelo | Plan `01` terminado | `run_readiness_flag`, `input_audit_report` | sin `hard_fail` |
| 1 | `baseline_calibration` | Fijar especificación primaria y valores centrales | Fase 0 | `baseline_input_table`, `parameter_set_baseline` | parámetros completos y trazables |
| 2 | `deterministic_baseline` | Obtener primeros resultados centrales | Fase 1 | `baseline_Vgross_table` | ecuaciones y tests básicos pasan |
| 3 | `scenario_regime_grid` | Barrer escenarios IA y regímenes fiscales | Fase 2 | `scenario_regime_grid`, heatmaps | celdas clasificadas sin cherry-picking |
| 4 | `threshold_inversion` | Calcular condiciones mínimas para cruzar | Fases 2-3 | `threshold_inversion_result` | flags de no computabilidad asignados |
| 5 | `historical_plausibility` | Comparar MFC usado/requerido con historia fiscal | Fases 3-4 | `historical_plausibility_table` | percentiles históricos válidos |
| 6 | `monte_carlo_uncertainty` | Propagar incertidumbre paramétrica | Fases 1-5 | `monte_carlo_result`, `mc_convergence_report` | convergencia y soporte válido |
| 7 | `robustness_falsification` | Probar fragilidad, placebos y diagnósticos | Fases 2-6 | `diagnostic_result`, `robustness_table` | no contradice baseline sin explicación |
| 8 | `final_classification` | Convertir celdas en conclusión país-política | Fases 3-7 | `final_country_policy_classification` | reglas agregadas aplicadas |
| 9 | `paper_outputs` | Exportar tablas, figuras y texto | Fases 0-8 | tablas cuerpo + appendix | `run_readiness_flag = TRUE` y tests pasan |

Regla central:

> Ningún resultado final debe reportarse si no puede trazarse hacia atrás hasta una fase, un `run_id`, un `parameter_set_id`, una versión de datos y un audit aprobado.

---

## 12.2 Fase 0 — Input readiness y auditoría de base

**Objetivo:** verificar que la base construida en el documento `01` está lista para ejecutar el modelo.

Esta fase no produce resultados económicos. Produce permisos de ejecución.

### Checks mínimos

| Check | Pregunta | Acción si falla |
|---|---|---|
| cobertura país-año | ¿PER, CHL, COL y MEX tienen anchors 2024 o flags claros? | bloquear baseline si faltan anchors críticos |
| trazabilidad | ¿cada variable tiene fuente, script y calidad? | bloquear si falta en variables principales |
| supuestos | ¿todo parámetro calibrado está en `assumption_registry` y `parameter_set_item`? | bloquear baseline |
| doble conteo | ¿AIPI, Gap, informalidad, IVA, rents, leakage y costos están separados? | bloquear si hay `hard_fail` |
| GMI | ¿se distingue agregado vs microdata? | permitir solo con etiqueta correcta |
| costos | ¿`c_gross`, `c_net`, admin, transición y leakage están separados? | bloquear si hay mezcla no trazable |
| MFC | ¿se distingue reduced-form histórico de channel-based? | bloquear si se mezclan |

Nota de corrida piloto: el check de cobertura país-año se evalúa sobre la lista de países DECLARADA de la corrida. Una corrida `run_label = pilot` con subconjunto declarado (p.ej. solo `PER`, corte vertical del plan 01, sección 23) puede alcanzar `run_readiness_flag = TRUE` para ese subconjunto; ese flag NO habilita el baseline oficial: el baseline del paper exige cobertura completa de los cuatro países y sus outputs nunca provienen de una corrida `pilot`.

### Outputs

```text
input_audit_report
run_readiness_flag
double_counting_audit
data_quality_summary
baseline_input_table
```

### Gate

```text
run_readiness_flag = TRUE
hard_fail_count = 0
```

Si este gate falla, no se corre la Fase 1.

---

## 12.3 Fase 1 — Baseline calibration

**Objetivo:** fijar los valores centrales que alimentan la especificación primaria.

Esta es la fase equivalente a una primera calibración. Aquí todavía no se concluye factibilidad; se congelan inputs.

### Decisiones que deben quedar congeladas

| Bloque | Decisión baseline |
|---|---|
| resultado | `Vgross` |
| costo | `c_gross` sobre `Y0` |
| shock IA | `phi_Y_nom` central por escenario |
| adopción | `anchored simulated adoption` |
| fiscal conversion | channel-based con frozen weights; histórico como plausibilidad y robustez |
| horizonte | `H=10` acumulado, convención endpoint |
| informalidad | mecanismos separados con convención declarada; partición dentro de adopción si aplica |
| Gap digital | excluded-indicators (baseline); residualized solo robustez (muestra internacional, regla de 11.2) |
| GMI | agregado; microdata si existe |
| deuda | guardrail separado |
| UBI | stress benchmark |

### Outputs

```text
parameter_set_baseline
calibrated_parameter_registry
baseline_input_table
primary_specification_manifest
```

### Gate

```text
all_baseline_parameters_registered = TRUE
all_primary_specification_choices_frozen = TRUE
```

Si un parámetro no observado no tiene soporte, distribución, rango y justificación, no entra al baseline.

---

## 12.4 Fase 2 — Deterministic baseline

**Objetivo:** obtener los primeros resultados centrales bajo la especificación primaria.

Esta fase responde por primera vez:

> Con valores centrales y sin incertidumbre aleatoria, ¿qué políticas cruzan `Vgross >= 1`?

### Cálculos

Para cada país-política-escenario-régimen baseline:

```text
phi_Y_nom
q_prod
T
g_AI_level
MFCgross
fs_eff
c_gross
Vgross
debt_guardrail_pass
cell_result_class
```

### Outputs

```text
baseline_Vgross_table
baseline_policy_ranking
baseline_country_policy_matrix
baseline_failure_gap_table
```

### Gate

```text
computational_validation_core_tests = PASS
no_negative_costs = TRUE
no_unregistered_parameters = TRUE
```

Si el baseline determinístico tiene errores mecánicos, no se pasa a grid completo.

---

## 12.5 Fase 3 — Scenario-regime grid

**Objetivo:** expandir el baseline a todas las combinaciones relevantes.

Dimensión completa:

```text
country_id × policy_id × scenario_id × regime_id × endpoint_year
```

Con:

```text
country_id ∈ {PER, CHL, COL, MEX}
policy_id ∈ {PEN, MUT, GMI, PBI, UBI}
scenario_id ∈ {low, mid, high, stress}
regime_id ∈ {0, 1, 2, 3, 4} (los códigos r0-r4 son `regime_code`, no la llave entera)
anchor_year = 2024 (anchor_year fijo en 2024); endpoint_year = 2034 (baseline H=10)
```

### Outputs

```text
scenario_regime_grid
crossing_table
Vgross_heatmap_input
regime_sensitivity_table
policy_ranking_by_country
```

### Gate

```text
all_cells_have_classification = TRUE
stress_r4_not_called_robust = TRUE
```

Una política que cruza solo en `stress + r4` queda marcada como condicional extrema, no como robustamente factible.

---

## 12.6 Fase 4 — Threshold inversion

**Objetivo:** calcular qué tendría que pasar para que una política cruce el umbral.

Esta fase depende de las Fases 2 y 3 porque se aplica sobre celdas que no cruzan, celdas que cruzan débilmente y celdas que cruzan con supuestos exigentes.

### Umbrales mínimos

| Umbral | Pregunta |
|---|---|
| `g_ai_required` | ¿cuánta ganancia de PIB por IA se necesita? |
| `mfc_required_gross` | ¿qué captura fiscal bruta se necesita? |
| `q_prod_required` | ¿qué adopción productiva se necesita? |
| `q_use_required` | ¿qué uso productivo se necesita? |
| `tau_ai_required` | ¿qué captura explícita de rentas IA se necesita? |
| `aipi_required` | ¿qué preparación institucional sería necesaria? |
| `exposure_required` | ¿qué exposición productiva sería necesaria? |

### Outputs

```text
threshold_inversion_result
threshold_distance_table
impossibility_flags
adoption_ceiling_report
required_mfc_vs_history_input
```

### Gate

```text
noncomputable_cells_flagged = TRUE
impossibility_reason_not_null_when_needed = TRUE
```

No se permite dejar celdas imposibles como valores faltantes silenciosos.

---

## 12.7 Fase 5 — Historical fiscal plausibility

**Objetivo:** disciplinar los resultados con la experiencia fiscal del país.

Aquí se compara el `MFCgross` usado o requerido contra la distribución histórica positiva.

### Clasificación de plausibilidad

| Condición | Clase |
|---|---|
| `MFCgross <= P50` | ordinaria |
| `P50 < MFCgross <= P75` | moderada |
| `P75 < MFCgross <= P90` | demandante |
| `MFCgross > P90` | fuera de soporte histórico |

### Outputs

```text
historical_plausibility_table
mfc_required_percentile_table
fiscal_support_classification
extreme_cells_report
```

### Gate

```text
historical_percentiles_available = TRUE
mfc_object_matches_percentile_object = TRUE
```

La comparación primaria debe ser objeto contra objeto: `MFCgross` contra percentiles históricos brutos.

---

## 12.8 Fase 6 — Monte Carlo uncertainty

**Objetivo:** transformar resultados puntuales en probabilidades bajo incertidumbre paramétrica.

### Orden interno recomendado

| Subfase | Corrida | Uso |
|---:|---|---|
| 6.1 | `MC_independent_baseline` | transparencia inicial |
| 6.2 | `MC_rank_correlated` | robustez principal con dependencia institucional |
| 6.3 | `MC_block_correlated_stress` | stress conjunto favorable/adverso |
| 6.4 | `mc_convergence_report` | comprobar estabilidad de probabilidades |

### Outputs

```text
monte_carlo_result
mc_convergence_report
prob_v_ge_1
prob_v_ge_1_10
v_p05_p50_p95
valid_support_share
```

### Gate

```text
mc_converged_flag = TRUE for main cells
valid_support_share_above_threshold = TRUE
```

Si la probabilidad de cruce cambia más de la tolerancia al aumentar draws, la celda no debe reportarse como resultado estable.

---

## 12.9 Fase 7 — Robustness and falsification

**Objetivo:** comprobar que los resultados no son artefactos de una especificación favorable.

### Diagnósticos obligatorios

| Diagnóstico | Qué controla |
|---|---|
| gross vs net | dependencia de costo neto |
| GMI ideal vs loaded | focalización perfecta irreal |
| historical vs channel-based | flexibilidad fiscal excesiva |
| mecanismos separados de informalidad vs variantes adopción-only/fiscal-only | doble castigo o castigo insuficiente |
| AIPI/GAP alternativo | solapamiento de preparación digital |
| placebo ICT | factibilidad mecánica en shocks tecnológicos pasados |
| negative controls | sectores expuestos no productivos |
| leave-one-source-out | dependencia de fuente única |
| channel ablation | qué canal sostiene el resultado |

### Outputs

```text
robustness_table
diagnostic_result
placebo_result
negative_control_result
ablation_result
```

### Gate

```text
baseline_not_reversed_without_explanation = TRUE
diagnostics_documented = TRUE
```

Si el baseline solo sobrevive en una variante favorable, la conclusión debe bajar de categoría.

---

## 12.10 Fase 8 — Final country-policy classification

**Objetivo:** convertir muchas celdas en una conclusión final por país-política.

Esta fase no puede mirar solo la mejor celda. Debe usar la regla agregada definida en la sección de clasificación final.

### Outputs

```text
final_country_policy_classification
main_result_table
policy_feasibility_ranking
country_summary_table
```

### Gate

```text
classification_rule_applied_to_all_country_policy_pairs = TRUE
no_best_case_only_conclusion = TRUE
```

Regla editorial:

> La conclusión final debe decir si una política es robustamente factible, condicional, frágil, no factible o solo benchmark de stress.

---

## 12.11 Fase 9 — Paper outputs

**Objetivo:** exportar las tablas, figuras y texto que irán al paper.

### Cuerpo del paper

```text
country_anchor_table
policy_cost_table
baseline_Vgross_table
threshold_inversion_table
historical_plausibility_table
monte_carlo_table
final_country_policy_classification
```

### Appendix

```text
Vnet_results
channel_based_results
debt_integrated_results
placebo_ICT_results
negative_control_results
leave_one_source_out_results
anti_double_counting_audit
complete_parameter_registry
mc_convergence_report
```

### Gate final

```text
run_readiness_flag = TRUE
hard_fail_count = 0
computational_validation_tests = PASS
results_discipline_protocol = PASS
```

Si el gate final falla, no se exporta ninguna figura ni tabla final.

---

## 12.12 Dependencias críticas entre fases

| Si falla esta fase | Qué no puede hacerse |
|---|---|
| Fase 0 | ninguna corrida baseline |
| Fase 1 | no se puede interpretar ningún resultado como especificación primaria |
| Fase 2 | no se puede expandir a grid completo |
| Fase 3 | no se puede hacer clasificación país-política |
| Fase 4 | no se puede hablar de condiciones mínimas |
| Fase 5 | no se puede llamar ordinario/moderado/demandante/extremo |
| Fase 6 | no se puede hablar de probabilidad de factibilidad |
| Fase 7 | no se puede hacer claim fuerte de robustez |
| Fase 8 | no se puede escribir conclusión agregada país-política |
| Fase 9 | no se puede exportar resultados finales |

---

## 12.13 Equivalencia práctica con un plan por etapas

En términos operativos, el proyecto puede trabajarse así:

```text
Primero: verificar y congelar base + parámetros.
Segundo: correr primeros resultados determinísticos.
Tercero: expandir escenarios y regímenes.
Cuarto: calcular umbrales requeridos.
Quinto: evaluar plausibilidad histórica.
Sexto: correr incertidumbre Monte Carlo.
Séptimo: hacer robustez y falsificación.
Octavo: clasificar país-política.
Noveno: producir tablas finales del paper.
```

Esta es la versión económica del esquema por fases usado en papers computacionales: cada bloque produce outputs que alimentan el siguiente, y cada avance exige pasar un gate mínimo.

---

# 13. Experimentos principales

## Experimento 0 — Input audit antes de correr el modelo

Objetivo: verificar que la base está lista y que no hay mezclas peligrosas.

Output:

- `input_audit_report`;
- `double_counting_audit`;
- `run_readiness_flag`.

Regla:

> Si falla una regla `hard_fail`, la corrida baseline se detiene y no se exportan tablas ni figuras.

## Experimento 1 — Baseline determinístico

Objetivo: generar una primera matriz interpretativa sin incertidumbre aleatoria.

Configuración primaria:

| Bloque | Baseline |
|---|---|
| Shock IA | valor central por escenario, convertido a `phi_Y_nom` |
| Adopción | anchored simulated adoption |
| Fiscal conversion | channel-based frozen-weight; percentiles históricos como flag |
| Costos | `c_gross` baseline sobre `Y0` |
| GMI | agregado y, si existe, microdata |
| Buffer | `xi=0`, luego `xi=0.10` |
| Deuda | guardrail separado |

Output:

- `fiscal_space_result_baseline`;
- matriz `Vgross`;
- clasificación fiscal histórica;
- tabla de gaps absolutos y relativos.

## Experimento 2 — Scenario-regime grid

Objetivo: mostrar cómo cambia la factibilidad según escenario IA y régimen fiscal.

Dimensiones:

| Dimensión | Valores |
|---|---|
| escenarios IA | `low`, `mid`, `high`, `stress` |
| regímenes fiscales | `r0`, `r1`, `r2`, `r3`, `r4` |
| políticas | `PEN`, `MUT`, `GMI`, `PBI`, `UBI` |
| países | `PER`, `CHL`, `COL`, `MEX` |

Resultados:

- heatmap de `Vgross`;
- heatmap de clasificación fiscal;
- ranking de políticas por país;
- ranking de sensibilidad a régimen fiscal.

Interpretación correcta:

> Si una política cruza solo en `stress + r4`, no es una política robustamente factible. Es una política condicionada a escenario extremo y reforma fuerte.

## Experimento 3 — Threshold inversion

Objetivo: calcular condiciones mínimas necesarias para cruzar el umbral.

Para cada celda, estimar:

| Umbral | Pregunta |
|---|---|
| `g_ai_required` | qué ganancia de PIB IA se necesita |
| `mfc_required_gross` | qué captura fiscal bruta se necesita |
| `q_prod_required` | qué adopción productiva se necesita |
| `q_use_required` | qué uso productivo se necesita |
| `tau_ai_required` | qué tasa/captura de rentas IA se necesita |
| `aipi_required` | qué preparación institucional sería necesaria |
| `exposure_required` | qué exposición productiva sería necesaria |

Usar las fórmulas cerradas de la sección 7.7.

Output:

- `threshold_inversion_result`;
- `impossibility_reason`;
- `support_headroom`;
- `threshold_distance`;
- `floor_driven_flag`.

## Experimento 4 — Monte Carlo principal

Objetivo: propagar incertidumbre paramétrica sin convertir el ejercicio en forecast.

Número recomendado:

- MVP: 5,000 draws por bloque de país-política-escenario-régimen.
- Paper-ready: 10,000 a 50,000 draws, con convergencia de probabilidades de cruce.

Diseño de draws:

| Tabla | Qué sortea |
|---|---|
| `global_scenario_draw` | `phi_raw`, `kappa_to_y`, `pi_ai_y`, `phi_y_nominal` |
| `country_scenario_draw` | primitivos de adopción (`A`, `I`, `Gap`, `nu`s, `q_use_target`, `lambda_q`, `omega_I`, `omega_G`); `q_use`, `q_prod`, `T` y `g_ai_level` se DERIVAN, no se sortean (en baseline congelado, los draws de `nu`s y `lambda_q` son inertes — ver lectura operativa de 7.3; alimentan sensibilidades e inversiones) |
| `policy_cost_draw` | costo de política, beneficio, elegibles |
| `fiscal_conversion_draw` | primitivos de canal (tasas efectivas, cadena `chi_Kbase`/`chi_dom`/`psi_shift`, mpc's, `exempt_C`, costos, leakage); `MFCgross` se DERIVA en modo canal; se sortea directamente solo en la corrida histórica de robustez (PERT condicional o mezcla) |
| `monte_carlo_result` | distribución y probabilidad de cruce |

Todos los primitivos sorteados se persisten además en `draw_parameter_value` (formato largo); junto con `random_seed` en `run_manifest`, esto hace cada draw reproducible y auditable.

Resultados mínimos:

$$
\{P5,P25,P50,P75,P95\}(V^{gross}).
$$

Probabilidades:

$$
\widehat{\pi}(\xi)=\frac{1}{M}\sum_{m=1}^{M}\mathbf{1}\{V^{gross,(m)}\geq 1+\xi\}
$$

para:

$$
\xi\in\{0,0.05,0.10,0.25,0.50\}.
$$

Reportar:

- `prob_v_ge_1_00` (alias retenido: `prob_v_ge_1`);
- `prob_v_ge_1_05`;
- `prob_v_ge_1_10`;
- `prob_v_ge_1_25`;
- `prob_v_ge_1_50`;
- `prob_debt_consistent_1_00`;
- `prob_debt_consistent_1_05`;
- `prob_debt_consistent_1_10`;
- `prob_debt_consistent_1_25`;
- `prob_debt_consistent_1_50`;
- `valid_support_share`;
- `threshold_computability_share`;
- `failure_severity_mean_1_00`;
- `failure_severity_mean_1_05`;
- `failure_severity_mean_1_10`;
- `failure_severity_mean_1_25`;
- `failure_severity_mean_1_50` (medida PRINCIPAL, definición del paper `E[1+xi-V | V<1+xi]`);
- `failure_severity_median_1_00`;
- `failure_severity_median_1_05`;
- `failure_severity_median_1_10`;
- `failure_severity_median_1_25`;
- `failure_severity_median_1_50` (companion de robustez frente a colas).

Las tres familias del paper se guardan como filas separadas vía `prob_basis`: pi(xi) all-draw, pi_basic(xi) condicional a validez aritmética y pi_support(xi) condicional a soporte válido. Los shares (`valid_support_share`, `threshold_computability_share`, `requirement_already_covered_share`) son objetos COMPLEMENTARIOS de la cadena de validez, no sustitutos de las probabilidades condicionales.

## Experimento 5 — Historical fiscal plausibility

Objetivo: clasificar si la captura fiscal requerida está dentro o fuera de la experiencia histórica del país.

Comparaciones:

| Resultado | Comparación |
|---|---|
| `MFCgross` realizado | percentiles de `MFC_hist_gross_positive` |
| `MFC_required_gross` | percentiles históricos |
| `prob_crossing` | robustez frente a distribución histórica |

Regla:

> La comparación primaria debe usar objeto bruto contra objeto bruto: `MFCgross` vs `MFC_hist_gross`. No usar `MFCeff` contra percentiles históricos brutos como métrica principal.

## Experimento 6 — Robustez determinística

Bloques obligatorios:

| Robustez | Variante |
|---|---|
| Costos | gross vs net |
| GMI | agregado vs microdata; ideal vs `theta_target` cargado |
| Informalidad | adopción-side, fiscal-side, mecanismos separados con convención declarada |
| AIPI/GAP | Gap excluido vs Gap residualizado |
| Fiscal conversion | historical reduced-form vs channel-based |
| AI shock | low/mid/high/stress; TFP/LP bridge alternativo |
| Rentas IA | subset de capital vs adicional |
| VAT | exenciones en base vs tasa efectiva |
| Profit shifting | base-side vs rate-side |
| Costos | fijos vs marginal-equivalentes |
| Deuda | sin guardrail vs debt-consistent |
| Pandemia | MFC con y sin 2020-2021 |
| Recursos naturales | revenue total vs non-resource revenue |
| Erosión conductual | `r>=1` mecánico (cota superior) vs con `epsilon_ero` por canal; companion OBLIGATORIO del paper para todo resultado titular con `r>=1`; restricción `epsilon_ero*tau < 1` |
| `S_frontier` | sweep dedicado: set de economías benchmark (promedio OCDE vs mejor país vs set alternativo) × año de referencia × convención de score (`NDC_baseline` vs `full_score_robustness`); es el denominador de T y el objeto externo menos disciplinado del modelo |
| Reciclaje de transferencias | costo gross baseline vs variante `c_recyc` de primera ronda, etiquetada |

## Experimento 7 — Placebo y falsificación

Objetivo: evitar que el framework “encuentre” factibilidad mecánica en cualquier shock tecnológico.

Diagnósticos:

| Diagnóstico | Objetivo |
|---|---|
| Temporal placebo mecánico | correr estructura en años anteriores sin GenAI |
| Placebo ICT 2010-2018 | corre el pipeline COMPLETO con inputs era-consistentes (distribuciones fiscales, costos de política e informalidad históricos), no solo el bloque de traducción; benchmark de resultado conocido: la digitalización 2010-2018 no financió protección social universal |
| Negative control sectorial | sectores expuestos no productivos no deberían generar alta factibilidad |
| Leave-one-source-out | revisar dependencia excesiva de una fuente |
| Channel ablation | apagar canales para ver qué sostiene el resultado |
| No rent capture | probar dependencia de rentas IA |
| No formalization | probar si el resultado depende de asumir formalización por IA |
| Espejo de informalización | si se activa formalización endógena en `r1/r4`, reportar también el escenario adverso de informalización por desplazamiento |
| High leakage | stress institucional |

Output:

- `diagnostic_result`;
- `passes_diagnostic`;
- `baseline_v`;
- `diagnostic_v`;
- `rank_change`.

## Experimento 8 — Sensibilidad global y ranking de drivers

Objetivo: saber qué mueve `V`.

Métodos:

1. Spearman rank correlation.
2. Tornado chart.
3. Sobol solo si los inputs se tratan como independientes o si se usa método compatible con dependencia.

Drivers esperados:

- `phi_Y_nom`;
- `q_prod`;
- `T`;
- `S_frontier`;
- `MFCgross`;
- `c_gross`;
- `admin_cost`;
- `leakage`;
- `informality`;
- `tau_ai_eff`;
- `theta_target` para GMI.

---

# 14. Monte Carlo con dependencia

El Monte Carlo no debe asumir que todos los parámetros son independientes en la versión principal de robustez. AIPI, Gap, informalidad, adopción y captura fiscal están institucionalmente conectados.

## 14.1 Modos de Monte Carlo

| Modo | Uso |
|---|---|
| `MC_independent_baseline` | primera corrida transparente; todos los bloques independientes salvo restricciones mecánicas |
| `MC_rank_correlated` | robustez principal; correlaciones Spearman por bloques institucionales |
| `MC_block_correlated_stress` | shocks conjuntos adversos/favorables; stress de dependencia |

Regla:

> El baseline puede usar draws independientes por transparencia, pero la robustez principal debe usar dependencia rank-correlated por bloques país-institución.


La corrida histórica de robustez sortea `MFCgross` de la PERT condicional `PERT(P10, P50, P90)` o de la mezcla incondicional según el claim; los claims de expected feasibility usan la mezcla.
## 14.2 Correlaciones esperadas

| Par de variables | Signo esperado |
|---|---|
| `AIPI` – `q_prod` | positivo |
| `Gap` – `q_prod` | negativo |
| `informality` – `q_prod` | negativo |
| `informality` – `MFCgross` | negativo |
| `AIPI` – `MFCgross` | positivo moderado |
| `leakage` – `MFCeff` | negativo |
| `admin_cost` – `Vgross` | negativo |
| `theta_target` – `Vgross` para GMI | negativo |
| `S_frontier` más exigente – `T` | negativo |
| `informality` – `chi_Kbase` | negativo (la informalidad eleva la parte de ingreso mixto del residuo no laboral) |
| `AIPI` – `E_prod` | positivo (economías más preparadas están más expuestas) |

## 14.3 Restricciones mecánicas obligatorias

- `q_prod <= q_bar`;
- `0 <= T <= 1`;
- `MFCtilde_gross <= MFCgross`;
- `fs_eff <= MFCgross * g_AI_level` cuando hay costos fijos positivos;
- `Vgross` debe bajar si `c_gross` sube y todo lo demás queda fijo;
- `Vgross` debe bajar si `admin_cost`, `transition_cost` o `leakage` suben.


- Draws con `g_AI_level = 0` son draws económicos de no-cruce y permanecen en el denominador `all-draw`.
- Draws con `phi_Y_nom <= 0` son fallas económicas retenidas; se excluyen solo de las inversiones de umbral.
- Un draw con `MFCtilde_gross < 0` y `g_AI_level < 0` produciría mecánicamente producto positivo: se clasifica como falla económica, nunca como cruce.
## 14.4 Convergencia Monte Carlo

Para versión paper-ready correr:

$$
M\in\{5{,}000,10{,}000,25{,}000,50{,}000\}.
$$

Comparar `prob_v_ge_1` y `prob_v_ge_1_10` en celdas principales.

Criterio recomendado:

$$
|\widehat{\pi}_{M_k}-\widehat{\pi}_{M_{k-1}}| \leq 0.01\text{ a }0.02.
$$

Tabla nueva: `mc_convergence_report`.

| Campo | Descripción |
|---|---|
| `run_id` | corrida |
| `country_id` | país |
| `policy_id` | política |
| `scenario_id` | escenario |
| `regime_id` | régimen |
| `mc_n_draws` | número de draws |
| `prob_v_ge_1` | probabilidad estimada |
| `prob_v_ge_1_10` | probabilidad con buffer `xi=0.10` |
| `prob_change_vs_previous` | cambio frente a corrida anterior |
| `converged_flag` | TRUE/FALSE |
| `convergence_tolerance` | tolerancia usada |

---

# 15. Disciplina del modo channel-based

El modo channel-based es la especificación primaria porque es el único que representa los regímenes fiscales nativamente. Precisamente por eso debe tener reglas estrictas contra la flexibilidad excesiva, y la historia fiscal lo disciplina desde afuera: todo `MFC` construido por canales se clasifica contra los percentiles históricos del país.

## 15.1 Tabla de régimen fiscal channel-based

| Régimen | `tau_L` | `tau_K` | `tau_C` | `tau_AI` | Base broadening | Leakage |
|---|---|---|---|---|---|---|
| `r0` | efectivo observado | efectivo observado | efectivo observado | 0 | 0 | alto |
| `r1` | +cumplimiento | +cumplimiento | +cumplimiento | 0 | bajo | medio |
| `r2` | base ampliada | base ampliada | base ampliada | 0 | medio | medio |
| `r3` | igual `r0/r1` | igual `r0/r1` | igual `r0/r1` | positivo | bajo | medio/alto |
| `r4` | cumplimiento + base | cumplimiento + base | cumplimiento + base | positivo | alto | bajo/medio |

Nota: si la convención asigna exenciones o profit shifting al lado base, en `r>=2` el régimen opera sobre `exempt_C` y `psi_shift` (que heredan el índice de régimen), no sobre las tasas; el mismo margen nunca se implementa base-side y rate-side a la vez.

## 15.2 Regla de plausibilidad histórica

> El modo channel-based no puede producir `MFCgross > P90` histórico sin quedar automáticamente marcado como `extreme_or_outside_historical_support`, salvo que se justifique como reforma estructural excepcional y se saque de la especificación primaria.

## 15.3 Regla contra suma de canales y reduced-form

```text
if fiscal_conversion_mode == "historical_reduced_form":
    use MFC_hist_draw_or_percentile
    do not add tau_L + tau_K + tau_C + tau_AI

if fiscal_conversion_mode == "channel_based":
    construct MFC from channels
    use historical percentiles only for plausibility classification
```

---

# 16. Tratamiento reforzado de GMI

El GMI debe distinguir con claridad entre aproximación agregada, microsimulación y cargas de focalización.

| Versión GMI | Cómo se reporta |
|---|---|
| `GMI_ideal_aggregate` | lower-bound mecánico; no es microsimulación |
| `GMI_loaded_aggregate` | agregado con `theta_target`; sensibilidad conservadora |
| `GMI_ideal_microdata` | paper-ready si hay microdatos armonizados |
| `GMI_loaded_microdata` | paper-ready conservador; preferido para journal submission |

Vocabulario canónico: los cuatro valores de esta tabla son los canónicos para el campo `gmi_version` en todas las tablas (regla de canonicidad, sección 19). Equivalencia con el plan 01: `GMI_MVP_AGGREGATE` → `GMI_ideal_aggregate`; `GMI_PAPER_READY_MICRODATA` → `GMI_ideal_microdata`; las variantes `loaded` añaden la carga `theta_target` sobre la misma fuente de datos.

Regla dura:

> El ranking favorable de GMI frente a UBI no debe interpretarse como superioridad operacional si solo se usa focalización ideal agregada.

Interpretación permitida:

- Con `GMI_ideal_aggregate`: “mecánicamente más barato bajo focalización perfecta”.
- Con `GMI_loaded_aggregate`: “más barato bajo una carga de focalización asumida”.
- Con `GMI_ideal_microdata`: “estimado con distribución de hogares, pero sin fricciones conductuales completas”.
- Con `GMI_loaded_microdata`: “estimado con microdatos y carga conservadora de focalización”.

---

# 17. Reglas anti doble conteo

Estas reglas son duras. Una corrida que las viola debe ser marcada como inválida o solo como robustez etiquetada.

| Riesgo | Regla de diseño | Flag sugerido | Severidad baseline |
|---|---|---|---|
| AIPI contado dos veces | Si `qprod` se simula desde `AIPI`, no multiplicar otra vez por `AIPI` en `Sfull` baseline | `aipi_double_count_flag` | `hard_fail` |
| Gap solapado con AIPI | `Gap` debe usar indicadores excluidos del AIPI o ser residualizado | `gap_aipi_overlap_flag` | `hard_fail` o `robustness_only` |
| Informalidad duplicada | hard_fail SOLO si: la misma variable entra al índice logístico Y al techo sin partición/residualización, o la penalización laboral se aplica base-side y rate-side a la vez. El uso simultáneo adopción+fiscal como mecanismos separados declarados es el baseline del paper. | `informality_partition_flag` | `hard_fail` |
| Profit shifting duplicado | Aplicar en base o en tasa, no en ambas | `profit_shift_double_flag` | `hard_fail` |
| AI rents duplicadas | Si rentas IA son subset de capital, restarlas de `omegaK`; si son adicionales, etiquetar | `ai_rent_convention_flag` | `hard_fail` |
| IVA/exenciones duplicadas | Exenciones en base o tasa efectiva; no ambas | `vat_exemption_double_flag` | `hard_fail` |
| Costos administrativos duplicados | Si `Cexist` ya incluye gasto administrativo reemplazado, no sumar ahorro administrativo adicional | `admin_saving_double_flag` | `hard_fail` |
| Costos one-off mal tratados | Anualizar transición one-off; no restarla como costo anual permanente | `transition_treatment_flag` | `hard_fail` |
| MFC histórico y canales mezclados | Usar modo histórico o channel-based, no ambos sumados | `mfc_mode_flag` | `hard_fail` |
| Shock crudo mal usado | Usar `phi_Y_nom`, no `phi_raw` | `shock_unit_flag` | `hard_fail` |
| Denominador contaminado | Costos y fiscal space baseline sobre `Y0`, no PIB post-IA | `denominator_y0_flag` | `hard_fail` |
| GMI sobredimensionado | Si no hay microdatos, reportar como agregado; no como microsimulación | `gmi_microdata_flag` | `hard_fail` |
| Dato carried-forward importante | Permitir con warning y sensibilidad | `carried_forward_flag` | `soft_fail` |
| Colombia 2026 en informalidad | Excluir del baseline 2024 | `non_harmonized_robustness` | `robustness_only` |

---

# 18. Clasificación de resultados

## 18.1 Clasificación por celda

Eje 1 — `cell_result_class` (precedencia: primera regla gana):

| Orden | Condición | Clasificación |
|---:|---|---|
| 1 | falla condición de existencia | `impossible_or_noncomputable` |
| 2 | `Vgross < 1` | `not_feasible` |
| 3 | cruza pero falla deuda | `accounting_feasible_debt_failed` |
| 4 | cruza solo en `stress+r4` (evaluado sobre el conjunto de celdas del país-política) | `extreme_conditional_crossing` |
| 5 | resto | `feasible_cell` |

Eje 2 — `historical_plausibility_class` (independiente del eje 1):

| Condición | Clasificación |
|---|---|
| `MFCgross <= P50` | `fiscally_ordinary` |
| `P50 < MFCgross <= P75` | `fiscally_moderate` |
| `P75 < MFCgross <= P90` | `fiscally_demanding` |
| `MFCgross > P90` | `extreme_or_outside_historical_support` |

Flag de frontera: si `MFCgross` (o `MFC_required_gross`) cae dentro del intervalo de confianza bootstrap del percentil que define su clase (campos `*_ci_low/high` de `historical_capture_percentiles`), la celda conserva su clase pero recibe `borderline_plausibility_flag = TRUE` y las tablas del paper la marcan; la clase nunca se decide por el CI, solo se matiza.

Cada eje llena su propio campo de `fiscal_space_result`; una celda tiene SIEMPRE ambos.

## 18.2 Regla final país-política

Esta regla agrega celdas y evita cherry-picking.

| Clase país-política | Regla |
|---|---|
| `robustly_feasible` | cruza en `mid` (los cruces en `low` cuentan a fortiori), con `r0-r2`, pasa `xi=0.10`, `MFCgross <= P75`, pasa deuda y `prob_v_ge_1_10 >= 0.75`; si el cruce depende de `r1` o `r2`, además debe sobrevivir el companion de erosión conductual (`epsilon_ero`) |
| `conditionally_feasible` | cruza solo en `high` (frontier feasible según el paper) o `stress`, o requiere `r3-r4`, o `P75 < MFCgross <= P90` |
| `fragile_feasible` | cruza `Vgross >= 1`, pero falla deuda, depende de `MFCgross > P90`, o `prob_v_ge_1 < 0.50` |
| `not_feasible` | no cruza salvo supuestos extremos o no computables |
| `stress_benchmark_only` | `UBI`, salvo que pase criterios fuertes sin `stress+r4` |

Precedencia determinística (se evalúa en orden y la primera regla que aplica gana; elimina huecos y solapamientos): (0) `UBI` -> `stress_benchmark_only`, salvo la excepción de la regla adicional 4; (1) no cruza salvo supuestos extremos o no computables -> `not_feasible`; (2) cruza pero falla deuda, o depende de `MFCgross > P90`, o `prob_v_ge_1 < 0.50` -> `fragile_feasible`; (3) cumple TODAS las condiciones de `robustly_feasible` -> `robustly_feasible`; (4) resto -> `conditionally_feasible`, que es la clase RESIDUAL explícita e incluye la banda `prob_v_ge_1 >= 0.50` con `prob_v_ge_1_10 < 0.75`.

Base de probabilidad de clasificación: TODAS las probabilidades de las reglas de clase (`prob_v_ge_1*`, `prob_debt_consistent*`) usan `prob_basis = all_draw` — la más conservadora (draws inválidos o no computables cuentan como no-cruce) y la pi titular del paper. Las bases `basic_valid` y `support_valid` son diagnóstico de la cadena de validez y NUNCA cambian una clase.

Reglas adicionales:

1. Una política no puede ser `robustly_feasible` si falla el guardrail de deuda.
2. Una política no puede ser `robustly_feasible` si solo cruza en `stress+r4`.
3. Una política no puede ser `fiscally_ordinary` si `MFC_required > P90`.
4. `UBI` se clasifica por defecto como `stress_benchmark_only` salvo evidencia fuerte bajo `mid/high` y `r0-r2`.
5. Si `prob_v_ge_1 < 0.50`, no usar lenguaje de robustez.
6. Un cruce que depende de `r1-r2` no puede ser `robustly_feasible` sin sobrevivir el companion de erosión conductual.

---

# 19. Tablas de resultados a crear

Regla de canonicidad: estos esquemas son los CANÓNICOS para las tablas de corrida y prevalecen sobre las interfaces indicativas del plan 01 (secciones 20-22).

Disciplina de nombres MFC: `mfc_gross` y `mfc_tilde_gross` son columnas genéricas cuyo objeto lo define `run_manifest.fiscal_conversion_mode` (en `channel_based`, el objeto construido por canales; en `historical_reduced_form`, el objeto sorteado de la historia). NO se renombran por modo: el modo es propiedad de la corrida, no de la columna, y dos vocabularios por modo generan drift. Los objetos históricos ya llevan nombres explícitos (`mfc_tax_hist_gross`, `mfc_total_revenue_hist_gross`, plan 01 §15.2). `mfc_eff` es SOLO reporte derivado (`fs_eff/g`): nunca input, nunca sorteado, nunca comparado contra percentiles. Si la implementación quiere alias explícitos (p.ej. `mfc_channel_gross`), se crean como VISTAS de solo lectura en DuckDB, nunca como columnas nuevas de esquema.

## 19.1 `run_manifest`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `run_label` | TEXT |
| `model_version` | TEXT |
| `horizon_H` | INTEGER |
| `anchor_year` | INTEGER |
| `endpoint_year` | INTEGER |
| `static_or_accumulated` | TEXT |
| `trajectory_convention` | TEXT (baseline: `frozen_anchor_2024`) |
| `dataset_version` | TEXT |
| `parameter_set_id` | TEXT |
| `run_type` | TEXT |
| `adoption_mode` | TEXT |
| `fiscal_conversion_mode` | TEXT |
| `cost_convention` | TEXT |
| `gmi_version` | TEXT |
| `mc_mode` | TEXT |
| `created_at` | TIMESTAMP |
| `random_seed` | INTEGER |
| `run_readiness_flag` | BOOLEAN |
| `notes` | TEXT |

Nota: `endpoint_year = anchor_year + horizon_H`; consistente con las tablas 19.3/19.4.

## 19.2 `double_counting_audit`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `check_name` | TEXT |
| `passes_check` | BOOLEAN |
| `severity` | TEXT |
| `notes` | TEXT |

## 19.3 `fiscal_space_result`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `endpoint_year` | INTEGER |
| `phi_y_nominal` | DOUBLE |
| `translation_factor` | DOUBLE |
| `g_ai_level` | DOUBLE |
| `mfc_gross` | DOUBLE |
| `mfc_tilde_gross` | DOUBLE |
| `fs_gross` | DOUBLE |
| `fs_eff` | DOUBLE |
| `cost_gross_gdp` | DOUBLE |
| `cost_net_gdp` | DOUBLE |
| `v_gross` | DOUBLE |
| `v_net` | DOUBLE, nullable |
| `xi` | DOUBLE |
| `crosses_v1` | BOOLEAN |
| `crosses_buffer` | BOOLEAN |
| `debt_guardrail_pass` | BOOLEAN |
| `historical_plausibility_class` | TEXT |
| `cell_result_class` | TEXT |
| `country_policy_result_class` | TEXT, nullable |

## 19.4 `threshold_inversion_result`

| Campo | Tipo |
|---|---|
| `run_id` | TEXT |
| `model_version` | TEXT |
| `parameter_set_id` | TEXT |
| `dataset_version` | TEXT |
| `country_id` | TEXT |
| `policy_id` | TEXT |
| `requirement_basis` | TEXT: `baseline` / `debt_consistent` |
| `xi` | DOUBLE |
| `scenario_id` | TEXT |
| `regime_id` | INTEGER |
| `endpoint_year` | INTEGER |
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

Toda inversión es función del buffer: `R_req(xi)`; baseline `xi=0.10`, grilla completa opcional.

## 19.5 `monte_carlo_result`

Campos mínimos:

- `v_p05`, `v_p25`, `v_p50`, `v_p75`, `v_p95`;
- `prob_basis` | TEXT: `all_draw` / `basic_valid` / `support_valid` — una fila por basis y celda, con las cinco columnas de xi en cada fila;
- `prob_v_ge_1` (alias de `prob_v_ge_1_00`);
- `prob_v_ge_1_00`, `prob_v_ge_1_05`, `prob_v_ge_1_10`, `prob_v_ge_1_25`, `prob_v_ge_1_50` (formato ancho: la grilla xi está congelada por diseño y los percentiles no dependen de xi);
- `prob_debt_consistent_1_00`, `prob_debt_consistent_1_05`, `prob_debt_consistent_1_10`, `prob_debt_consistent_1_25`, `prob_debt_consistent_1_50`;
- `failure_severity_mean_1_00`, `failure_severity_mean_1_05`, `failure_severity_mean_1_10`, `failure_severity_mean_1_25`, `failure_severity_mean_1_50` (medida principal; la mediana es companion);
- `failure_severity_median_1_00`, `failure_severity_median_1_05`, `failure_severity_median_1_10`, `failure_severity_median_1_25`, `failure_severity_median_1_50`;
- `valid_support_share`;
- `threshold_computability_share`;
- `requirement_already_covered_share`;
- `mc_mode`;
- `mc_n_draws`;
- `converged_flag`.

## 19.6 `diagnostic_result`

Debe guardar:

- tipo de diagnóstico;
- resultado baseline;
- resultado diagnóstico;
- cambio de ranking;
- si pasa o falla;
- notas de interpretación.

## 19.7 Tablas de gobernanza pre-run (requeridas por 10.17 y Fase 0)

Estos objetos deben existir ANTES de la Fase 2 (regla 10.17). Esquemas mínimos:

`value_assignment_table`: su esquema ES la tabla de campos obligatorios de la sección 10.3 (`name`, `module`, `value_type`, `unit`, `baseline_value`, `low_value`, `high_value`, `support_type`, `source_id`, `formula_id`, `distribution`, `truncation_rule`, `primary_spec_flag`, `robustness_flag`, `stress_flag`, `double_counting_risk`, `audit_status`) más las llaves `parameter_set_id` y `dataset_version`. Una fila por valor escalar que entra al modelo.

`threshold_assignment_table` (VALORES de umbrales): `threshold_name` | `controls_decision` | `threshold_type` (structural / prudencial / histórico / probabilístico / computacional) | `baseline_value` | `sensitivity_values` | `action_on_fail` | `source_section` (p.ej. 10.12, 10.13).

`threshold_rule_registry` (REGLAS de clase, distinto del anterior): `rule_id` | `rule_text` | `inputs_used` | `precedence_order` | `source_section` (18.1, 18.2, reglas adicionales 1-6). Congela las reglas de clasificación y su precedencia antes de ver resultados.

`input_audit_report`: `dataset_version` | `parameter_set_id` | `check_name` | `module` | `table_name` | `passes_check` | `severity` (hard_fail / soft_fail / robustness_only) | `notes` — paralelo pre-run del esquema 19.2.

`run_readiness_flag` y `assumption_registry_complete_flag` NO son tablas: son derivados booleanos registrados como fila resumen de `input_audit_report` y como campo `run_readiness_flag` de `run_manifest` (19.1). `calibrated_parameter_registry` ya tiene esquema en 9.2 y se referencia, no se duplica. `baseline_parameter_set` es el `parameter_set` del plan 01 con `parameter_set_name = baseline`.

---

# 20. Computational validation tests

Estas pruebas validan que el código respeta la lógica económica del modelo.

| Test | Condición esperada |
|---|---|
| `test_cost_monotonicity` | si `c_gross` sube y todo lo demás queda fijo, `Vgross` baja |
| `test_zero_mfc` | si `MFCtilde_gross <= 0` con costos positivos, `Vgross < 1` o no computable — el caso peligroso es `MFCgross > 0` con `MFCtilde_gross <= 0` por deducciones ME |
| `test_zero_phi` | si `phi_Y_nom = 0`, entonces `g_AI_level = 0` |
| `test_zero_qprod` | si `q_prod = 0`, entonces `T = 0` |
| `test_fixed_cost_monotonicity` | si `ac_fix`, `tr_ann` o `leak_fix` suben, `fs_eff` baja |
| `test_historical_class` | si `MFC_required > P90`, la celda no puede ser `fiscally_ordinary` |
| `test_debt_guardrail` | si `Vgross >= 1` pero falla deuda, no puede ser `robustly_feasible` |
| `test_bilinear_corner` | si `MFCtilde_gross < 0` y `g_AI_level < 0`, la celda se clasifica como falla económica, nunca como cruce |
| `test_stress_only` | si cruza solo en `stress+r4`, no puede ser `robustly_feasible` |
| `test_phi_raw_blocked` | si una corrida usa `phi_raw` directo, debe activar `hard_fail` |
| `test_mfc_mode_exclusion` | no se puede sumar MFC histórico con channel-based |
| `test_gmi_labeling` | GMI agregado no puede etiquetarse como microdata |
| `test_gap_aipi_overlap` | Gap solapado no residualizado no entra al baseline |
| `test_static_labeling` | ninguna corrida estática puede tener `static_or_accumulated = accumulated_endpoint` |
| `test_erosion_companion` | un resultado titular con `r>=1` sin corrida companion de erosión conductual bloquea la exportación |

Output recomendado:

- `computational_validation_report`.

Campos:

| Campo | Descripción |
|---|---|
| `test_id` | identificador |
| `test_name` | nombre |
| `passes_test` | TRUE/FALSE |
| `severity` | hard/soft |
| `affected_module` | módulo |
| `notes` | explicación |

---

# 21. Results discipline protocol

Este protocolo controla cómo se escriben los resultados para no exagerar conclusiones.

Reglas editoriales obligatorias:

1. No reportar solo las celdas favorables.
2. Siempre mostrar por país: mejor caso, baseline y peor caso.
3. Separar `UBI` como benchmark de estrés.
4. Toda conclusión debe incluir `Vgross`, plausibilidad histórica y guardrail de deuda.
5. Si cruza solo en `stress+r4`, escribir: “conditional on extreme AI and combined reform”, no “feasible”.
6. Si `prob_v_ge_1 < 0.50`, no usar lenguaje de robustez.
7. Si `MFCgross > P90`, escribir: “outside historical support”.
8. Si el resultado depende de `Vnet`, reportarlo como robustez, no como conclusión principal.
9. Si GMI usa `GMI_ideal_aggregate`, describirlo como lower-bound mecánico.
10. Si una celda falla el audit, no debe aparecer en tablas principales.
11. Ningún resultado titular con `r>=1` se reporta sin su companion de erosión conductual.
12. Si el baseline usa `is_lac_fallback = TRUE`, toda referencia a H2 en el texto del paper lleva el caveat de construcción: la variación entre países de `T` proviene de preparación y adopción por construcción, no de exposición medida.

Orden narrativo obligatorio:

1. costos de política;
2. espacio fiscal inducido por IA;
3. `Vgross`;
4. plausibilidad histórica;
5. guardrail de deuda;
6. Monte Carlo;
7. threshold inversion;
8. diagnósticos;
9. límites y no-claims.

---

# 22. Main tables vs appendix

## 22.1 Cuerpo del paper

| Tabla | Contenido |
|---|---|
| Table 1 | Anchors observados por país |
| Table 2 | Costos brutos por política |
| Table 3 | Especificación primaria: escenarios IA y regímenes fiscales |
| Table 4 | Baseline `Vgross` por país-política-escenario-régimen |
| Table 5 | Threshold inversion: `g_ai_required`, `MFC_required`, `q_required` |
| Table 6 | Plausibilidad histórica vs P50/P75/P90 |
| Table 7 | Monte Carlo: percentiles y probabilidades de cruce |
| Table 8 | Clasificación final país-política |

## 22.2 Appendix

| Tabla | Contenido |
|---|---|
| Appendix A | Net-cost specification |
| Appendix B | Historical reduced-form fiscal mode (robustez etiquetada) |
| Appendix C | Debt-integrated specification |
| Appendix D | Placebo ICT |
| Appendix E | Negative controls |
| Appendix F | Leave-one-source-out |
| Appendix G | Channel ablation |
| Appendix H | Anti-double-counting audit |
| Appendix I | Parámetros completos y calibration registry |
| Appendix J | Monte Carlo convergence report |
| Appendix K | Computational validation tests |

---

# 23. Minimum publishable package

| Elemento | Working paper | Journal submission |
|---|---|---|
| Baseline determinístico | obligatorio | obligatorio |
| Scenario-regime grid | obligatorio | obligatorio |
| Historical plausibility | obligatorio | obligatorio |
| Threshold inversion | obligatorio | obligatorio |
| Monte Carlo | recomendable | obligatorio |
| MC convergence report | opcional | obligatorio |
| GMI microdata | recomendable | muy recomendable |
| Placebo ICT | opcional | obligatorio si el claim es fuerte |
| Negative controls | opcional | obligatorio |
| Leave-one-source-out | opcional | recomendable |
| Channel ablation | recomendable | obligatorio |
| Anti-double-counting audit | obligatorio | obligatorio |
| Calibration registry | obligatorio | obligatorio |
| Results discipline protocol | obligatorio | obligatorio |

Regla práctica:

> Para enviar a journal, no basta con cruzar `Vgross`. Debe existir plausibilidad histórica, Monte Carlo, audit de doble conteo, threshold inversion y clasificación final país-política.

---

# 24. Model risk register

| Riesgo | Qué afecta | Mitigación |
|---|---|---|
| shock IA incierto | `phi_Y_nom` | escenarios + Monte Carlo + threshold inversion |
| adopción no observada | `q_prod`, `T` | anchored adoption + adopción requerida |
| informalidad doble contada | `T`, `MFCgross` | mecanismos separados declarados; partición índice/techo dentro de adopción; base-o-tasa en fiscal |
| GMI idealizado | costo social | `theta_target` + microdata |
| fiscal conversion flexible | `MFCgross` | channel-based primary + disciplina histórica P50/P75/P90 |
| deuda omitida | factibilidad final | debt guardrail separado |
| datos no armonizados | comparabilidad | input audit + robustness-only flags |
| AIPI/Gap solapados | traducción doméstica | excluded-indicators o residualization |
| AI rents duplicadas | fiscal conversion | subset de capital o canal adicional, no ambos |
| profit shifting duplicado | base capital | aplicar en base o tasa, no ambas |
| costos administrativos duplicados | `fs_eff` | separar admin nuevo, ahorro existente y transición |
| resultados cherry-picked | conclusión | clasificación país-política + results discipline |
| trayectoria congelada 2024 | `T`, `g_AI_level`, `V` | sesgo conservador en el margen T (subestima difusión); compounding generoso; declarado en 7.2 y acotado con `trajectory_sensitivity` |

---

# 25. Algoritmo operativo

```text
Para cada run_id:

1. Cargar dataset_version y parameter_set_id.
2. Verificar calibrated_parameter_registry.
3. Ejecutar input audit.
4. Ejecutar double_counting_audit.
5. Si run_readiness_flag != TRUE, detener.
6. Si existe hard_fail no superado, detener baseline y bloquear exportación.
7. Para cada país i:
8.   Para cada política p:
9.     Construir c_gross y c_net.
10.    Cargar costos administrativos, transición y leakage.
11.    Determinar versión GMI si p == GMI.
12.    Para cada escenario s:
13.      Convertir phi_raw a phi_Y_nom.
14.      Calcular q_use, q_prod y T.
15.      Calcular g_AI_level acumulado a horizonte H (convención endpoint, sección 7.2):
         (1 + phi_Y_nom * T)^H - 1 con phi y T constantes, o el producto anual si varían.
         La fórmula estática solo en corridas etiquetadas one_period_static.
16.      Para cada régimen r:
17.        Modo fiscal: channel-based frozen-weight (baseline); histórico solo en la corrida de robustez etiquetada.
18.        Calcular MFCgross y MFCtilde_gross.
19.        Calcular fs_eff.
20.        Calcular Vgross.
21.        Calcular buffers xi.
22.        Calcular guardrail de deuda.
23.        Clasificar celda y plausibilidad histórica.
24.        Guardar fiscal_space_result.
25.        Calcular threshold inversion con fórmulas cerradas.
26.        Guardar threshold_inversion_result.
27. Ejecutar Monte Carlo si run_type = monte_carlo.
28. Ejecutar mc_convergence_report si versión paper-ready.
29. Ejecutar robustez y diagnósticos.
30. Agregar clasificación final país-política.
31. Ejecutar computational validation tests.
32. Exportar tablas y figuras solo si audit y tests duros pasan.
```

---

# 26. Orden recomendado de implementación por entregables

El roadmap secuencial de la sección 12 define el orden lógico completo. Para organizar el trabajo práctico, los entregables pueden agruparse en tres paquetes.

## Paquete A — MVP determinístico defendible

Incluye:

1. Fase 0 — `input_readiness`.
2. Fase 1 — `baseline_calibration`.
3. Fase 2 — `deterministic_baseline`.
4. Fase 3 — `scenario_regime_grid`.
5. Fase 4 — `threshold_inversion`.
6. Fase 5 — `historical_plausibility`.
7. versión preliminar de Fase 8 — clasificación país-política sin Monte Carlo.

Este paquete permite una primera versión seria del paper, pero todavía no permite claims probabilísticos fuertes.

## Paquete B — Robustez paper-ready

Incluye:

1. Fase 6 — Monte Carlo independiente y rank-correlated.
2. convergencia Monte Carlo para celdas principales.
3. GMI agregado vs microdata, si existe.
4. gross vs net.
5. modo histórico vs channel-based.
6. deuda separada y debt-consistent.
7. informalidad con mecanismos separados vs variantes adopción-only/fiscal-only.
8. AIPI/GAP sin solapamiento.
9. pandemia y non-resource revenue.
10. sweep de `S_frontier` (set, año, convención).

Este paquete permite sostener resultados como probabilidades y no solo como puntos calibrados.

## Paquete C — Diagnóstico final y envío a journal

Incluye:

1. Fase 7 completa — robustez y falsificación.
2. placebo ICT.
3. negative controls.
4. leave-one-source-out.
5. channel ablation.
6. global sensitivity / ranking de drivers.
7. Fase 8 final — clasificación país-política completa.
8. Fase 9 — tablas cuerpo + appendix.
9. computational validation tests.
10. results discipline protocol.

Este paquete es el mínimo razonable para una versión journal submission si el paper quiere hacer claims fuertes sobre factibilidad robusta.

---

# 27. Checklist final antes de reportar resultados

- [ ] `Primary specification` está declarada antes de mostrar resultados.
- [ ] `Vgross` es el resultado principal.
- [ ] `Vnet` aparece solo como robustez.
- [ ] `phi_raw` nunca entra directo a fiscal space.
- [ ] `phi_Y_nom` está documentado y trazado.
- [ ] `qprod` y `Eprod` están separados.
- [ ] `AIPI` no está duplicado entre adopción y score completo.
- [ ] `Gap` no se solapa con AIPI sin residualizar.
- [ ] Informalidad: convención declarada; partición dentro de adopción (índice vs techo) si aplica; fiscal usa `I_marg` en base o tasa.
- [ ] Modo fiscal histórico y channel-based no se mezclan.
- [ ] `MFCgross` se compara con percentiles históricos brutos.
- [ ] `MFCeff` no se usa como comparación primaria contra historia bruta.
- [ ] Costos fijos y marginal-equivalentes no se duplican.
- [ ] `Cexist` excluye pensiones contributivas y derechos adquiridos.
- [ ] GMI agregado no se presenta como microdata.
- [ ] `UBI` aparece como stress benchmark.
- [ ] Existe clasificación final país-política.
- [ ] Existe `calibrated_parameter_registry`.
- [ ] Existe `mc_convergence_report` si se reporta Monte Carlo paper-ready.
- [ ] Existe `computational_validation_report`.
- [ ] Toda tabla tiene `run_id`, `model_version`, `dataset_version`, `parameter_set_id`.
- [ ] Toda conclusión distingue factibilidad contable, plausibilidad histórica y sostenibilidad fiscal.
- [ ] Ninguna tabla o figura se exporta sin `run_readiness_flag = TRUE`.

---

# 28. Frase metodológica sugerida para el paper

> We implement the framework through a calibrated empirical-simulation design rather than a causal forecast. For each country-policy-scenario-regime cell, observed macro-fiscal and social-protection anchors are combined with explicitly registered scenario parameters to compute AI-induced effective fiscal space, gross-cost feasibility ratios, threshold inversions, historical fiscal-capture plausibility classes, and Monte Carlo crossing probabilities. The baseline object is the gross-cost feasibility index under a pre-specified channel-based fiscal-conversion mode with frozen weights, disciplined by historical fiscal-capture percentiles; net-cost, debt-integrated, historical reduced-form, full-score, and alternative-bridge specifications are reported only as labelled robustness exercises. No result is exported unless input-audit and double-counting checks pass.

---

# 29. Conclusión práctica

Este diseño convierte el paper en una aplicación empírica defendible porque separa:

1. datos observados;
2. parámetros normativos;
3. supuestos de escenario;
4. parámetros calibrados no observados;
5. resultados de corrida;
6. factibilidad contable;
7. plausibilidad histórica;
8. sostenibilidad fiscal conservadora;
9. robustez bajo incertidumbre;
10. reglas de reporte.

La clave es no vender el resultado como predicción. El valor del paper está en mostrar **cuánto tendría que pasar** para que una política social sea fiscalmente cubierta por espacio fiscal inducido por IA, y si ese “cuánto” cae dentro de rangos históricos e institucionalmente plausibles para Perú, Chile, Colombia y México.
