# Reconstrucción separada ENAHO/CASEN — JPM V2

Este módulo reconstruye las comparaciones de costos de GMI citadas en el párrafo 67 del manuscrito: Perú −7,734 % y Chile +0,387 % frente al costo agregado con la misma línea PIP PPP 8,30. Recalcula además las variantes de sensibilidad y los controles de pobreza de los programas originales.

Las entradas son el ZIP original ENAHO Sumaria 2024, el archivo SPSS original CASEN 2024 y tres anclas agregadas generadas por la reproducción principal. No se incluyen microdatos en este módulo. Las referencias CSV se consultan después de calcular; el programa bloquea su lectura durante el cálculo.

## 1. Preparar el entorno y las carpetas

Extraiga el módulo en una carpeta nueva. Utilice el entorno del paquete principal: Python 3.12.10 y las dependencias fijadas. La ruta verificada usa la imagen Docker local identificada en INPUT_CONTRACT.json. Su identificador no es una URL pública de descarga.

Si usa Python nativo, cree un entorno e instale las dependencias:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --require-hashes --no-deps -r requirements-lock.txt -r requirements-windows-supplement.txt
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación.' }
& '.\.venv\Scripts\python.exe' -m pip check
```

## 2. Disponer de las entradas exactas

La carpeta del núcleo debe contener upstream/data/model_inputs/poverty_distribution_anchor.parquet, macro_anchor.parquet y policy_cost.parquet, generados por la reproducción principal. El contrato comprueba su esquema y todos los valores científicos, excluyendo únicamente los valores de build_id y created_at, que se generan en cada ejecución. Los hashes binarios se registran antes y después. La ejecución completa r7 reconstruye primero estas anclas desde los snapshots del núcleo.

La carpeta de encuestas debe tener estas rutas:

```text
robustness-gmimicro-per-v1/enaho_sumaria/966-Modulo34.zip
robustness-gmimicro-chl-v1/casen_2024/casen_2024.sav
```

Si ya conserva esos originales, el módulo los usa en modo de lectura. Si necesita obtenerlos, consulte ADQUISICION.md. Las proyecciones Parquet históricas son opcionales: cuando están disponibles, se comparan después del cálculo con las variables recién extraídas; no se utilizan como entradas del cálculo.

## 3. Ejecutar la reconstrucción

Con Python, indique las carpetas del núcleo, encuestas y una salida nueva:

```powershell
& '.\.venv\Scripts\python.exe' -B reproduce_surveys.py --core-root 'D:\replicacion\jpm-v2' --raw-root 'D:\replicacion\encuestas' --output 'D:\replicacion\salida-encuestas'
if ($LASTEXITCODE -ne 0) { throw 'Revise el mensaje de error y SURVEY_FAILURE.json.' }
```

Con la imagen Docker local fijada, desde la carpeta del módulo:

```powershell
$jpmSurveyModule = (Get-Location).Path
$jpmCore = 'D:\replicacion\jpm-v2'
$jpmSurveyRaw = 'D:\replicacion\encuestas'
$jpmSurveyOutput = 'D:\replicacion\salidas'
New-Item -ItemType Directory -Path $jpmSurveyOutput -Force | Out-Null
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=536870912 --mount "type=bind,source=$jpmSurveyModule,target=/app,readonly" --mount "type=bind,source=$jpmCore,target=/core,readonly" --mount "type=bind,source=$jpmSurveyRaw,target=/raw,readonly" --mount "type=bind,source=$jpmSurveyOutput,target=/out" --workdir /app -e PYTHONDONTWRITEBYTECODE=1 sha256:62e57073de8aa6cdd1d20061f7fe4b8494cee6bd8b642ec5039de66cbd5ac782 python -B -u reproduce_surveys.py --core-root /core --raw-root /raw --output /out/corrida-01
if ($LASTEXITCODE -ne 0) { throw 'Falló la reconstrucción de encuestas.' }
```

Use una carpeta de salida vacía para cada ejecución. El cálculo no necesita acceso a la red. Los CSV producidos son agregados; no se exportan registros individuales.

## 4. Verificar PASS

Abra SURVEY_REPRODUCTION.json en la salida y compruebe status: PASS y microdata_reexecuted: true. Debe registrar 33.691 hogares en Perú; 218.367 registros iniciales, 218.260 personas válidas y 78.654 hogares en Chile; ocho filas de costos para Perú y seis para Chile. Las diferencias principales son −7.733607010693411 % y +0.3866287931443724 %.

El informe incluye la comparación de todas las columnas, los controles de pobreza, la reconstrucción independiente de 14 costos, el entorno y las funciones históricas utilizadas. INPUT_CONTRACT.json fija rtol=1e-12 y atol=1e-10. Las referencias, hashes, definición de variables y tolerancias no deben modificarse para obtener PASS.

El alcance es la comparación separada de costos de hogares. El modelo agregado, las ecuaciones fiscales y las conclusiones de cobertura conservan su especificación. La integración final del módulo, CI y el depósito público se registran en el seguimiento del proyecto.
