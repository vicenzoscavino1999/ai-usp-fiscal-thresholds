# Reproducción completa de JPM V2

El ejecutor completo reconstruye el núcleo fiscal, las extensiones y las comparaciones ENAHO/CASEN. El resultado completo es run_logs/COMPARISON_COMPLETE.json; COMPARISON_FULL.json corresponde al núcleo y las extensiones.

## 1. Preparar una extracción nueva

Extraiga el ZIP en una carpeta vacía. No copie resultados ni entradas calculadas. Deben aparecer reproduce_complete.py, Dockerfile y SOURCE_MANIFEST.json. Los Word vigentes se identifican en extensions/config/DOCUMENT_MAP.json; mantienen sus rutas técnicas por compatibilidad.

Las encuestas originales se guardan fuera de esta carpeta. Consulte surveys/ADQUISICION.md y siga su estructura de directorios. La versión exacta se comprueba por SHA-256. No se incluyen registros individuales en el paquete. Las proyecciones históricas Parquet son opcionales y sólo se usan para comparación posterior al cálculo.

## 2. Construir el entorno

La ruta principal es Docker en linux/amd64. La base Python 3.12.10 se fija por digest y las dependencias se instalan con versiones y hashes del archivo requirements-lock.txt:

```powershell
docker build --platform linux/amd64 --tag jpm-v2:2.0.0 .
if ($LASTEXITCODE -ne 0) { throw 'Falló la construcción del entorno.' }
```

La imagen y los ejecutores fijan NPY_DISABLE_CPU_FEATURES=X86_V4 antes de importar NumPy. Esta configuración conserva la misma ruta de cálculo entre procesadores para los hashes exactos de resultados derivados. No requiere modificar los comandos ni las tolerancias.

La construcción necesita acceso a los repositorios de dependencias. La imagen contiene el entorno; los cálculos usan exclusivamente archivos congelados y se ejecutan sin red. La ruta nativa conserva las dependencias fijadas, pero la verificación completa de esta versión corresponde a Docker.

## 3. Ejecutar la reproducción completa

Desde la extracción nueva, indique la carpeta de los originales de encuestas:

```powershell
$jpmRunFolder = (Get-Location).Path
$jpmSurveyRaw = 'D:\replicacion\encuestas'
docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=2147483648 --mount "type=bind,source=$jpmRunFolder,target=/app" --mount "type=bind,source=$jpmSurveyRaw,target=/raw,readonly" --workdir /app -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app:/app/surveys jpm-v2:2.0.0 python -B -X utf8 -u reproduce_complete.py --raw-root /raw
if ($LASTEXITCODE -ne 0) { throw 'La reproducción falló; consulte run_logs.' }
```

El ejecutor comprueba primero que no existan resultados precargados. Luego ejecuta las 39 etapas del núcleo y sus extensiones, reconstruye las encuestas con las anclas recién generadas y verifica el conjunto. Los hashes de fuentes se comprueban antes y después. Las referencias permanecen separadas de los cálculos.

Los valores científicos y el esquema de las tres anclas de encuestas se comprueban por identidad semántica; sólo los valores de build_id y created_at se excluyen porque cambian con cada ejecución. Sus hashes binarios también se registran antes y después del bloque de encuestas. Las fórmulas, calibraciones y datos observados conservan sus controles.

## 4. Verificar PASS

```powershell
Get-Content -LiteralPath '.\run_logs\COMPARISON_COMPLETE.json' -Raw | ConvertFrom-Json | Select-Object status, core_files_passed, extension_files_passed, survey_tables_passed, documentary_cells, scientific_outcomes
```

El resultado completo debe mostrar status: PASS, 77 salidas centrales, 88 de extensiones, cuatro tablas de encuestas y 164 celdas documentales; la figura debe coincidir. La comparación de encuestas conserva −7,734 % en Perú y +0,387 % en Chile. Un PASS de verify_all.py por sí solo no acredita esta reconstrucción completa.

scientific_outcomes conserva D_LOW_EXPOSURE=FAIL_RETAINED, H1=MIXED, H2/H3=NOT_TESTABLE, H4=HOLDS condicional y H5 retirada. PASS significa que se reprodujeron los resultados dentro del alcance declarado, incluidos los resultados adversos.

Las fuentes y la configuración son inmutables durante la corrida. Para repetir todo, utilice otra extracción. verify_complete.py permite verificar una ejecución completa existente sin recalcular las simulaciones; comprueba los archivos reales y la trazabilidad del arranque limpio.

## Ejecutar CI local

ci/run_ci.py usa la misma secuencia que GitHub Actions: construye Docker, crea una copia limpia del inventario, ejecuta la reproducción y corre todas las pruebas. La carpeta de trabajo debe ser nueva y estar fuera del paquete:

```powershell
python ci/run_ci.py --workdir 'D:\replicacion\ci-2.0.0' --raw-root 'D:\replicacion\encuestas'
```

Si omite --raw-root, el programa obtiene los originales desde los proveedores y exige que sus hashes coincidan antes de comenzar. Los datos de encuestas no se incluyen entre los artefactos de CI. Consulte CI.md para activar el flujo remoto y distinguir su ejecución de la verificación local.
