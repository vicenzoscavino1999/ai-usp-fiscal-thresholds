# Verificación de resultados de JPM V2

`python -X utf8 reproduce.py` reconstruye los insumos y ejecuta las 28 etapas. La última etapa verifica los resultados y las 164 celdas documentales desde el mismo comando. Para comprobar una ejecución ya terminada:

```powershell
python -X utf8 compare_results.py
```

El resultado se guarda en `run_logs/COMPARISON.json`. El éxito requiere código de salida 0, `status: PASS`, `files_passed: 77`, `files_failed: 0`, figura coincidente y `documentary_checks.cells_verified: 164`. Un fallo devuelve código 1 e identifica el archivo, la regla y, cuando corresponde, la columna y las claves de las filas afectadas. `--report RUTA` permite guardar el informe por separado.

## Contrato de verificación

- `reference_manifest.json` enumera las 77 salidas obligatorias y sus referencias, los hashes de estas y el inventario de fuentes congeladas. La comparación no depende de los archivos que casualmente queden en una carpeta.
- `schemas.yaml` declara filas, columnas, tipos, claves, valores categóricos y nulabilidad. En 72 tablas las filas se emparejan por claves explícitas. Tres tablas conservan el ordinal registrado porque su exportación no contiene un identificador único; la razón está declarada en cada esquema. No se inventan claves ni se eliminan observaciones.
- Los nulos sólo se admiten en las columnas declaradas y deben aparecer en las mismas posiciones lógicas que en la referencia. No se admiten infinitos. Los valores no nulos conservan el tipo declarado.
- Los enteros, booleanos, textos, claves y conteos/años señalados se comparan exactamente. Los campos de metadatos variables conservan validación de estructura y tipo, pero no exigen igualdad de timestamps o identificadores de construcción.
- Las matrices NPZ tienen nombres, dimensiones y tipos explícitos. Los JSON tienen estructura y tipos definidos, prohíben claves duplicadas y valores no finitos y conservan comparación exacta de valores.
- `SOURCE_MANIFEST.json` protege las fuentes, los scripts, los documentos, las referencias y el contrato. Su ausencia o un hash incorrecto produce FAIL. Las fuentes congeladas se verifican por SHA-256 exacto.

La ausencia de `run_logs/execution.json` genera una advertencia: verificar resultados existentes no acredita por sí solo que se haya registrado una corrida completa. Esta advertencia no se aplica al manifiesto obligatorio de fuentes ni permite omitir una salida.

## Tolerancias y alcance

`tolerances.yaml` mantiene `atol=1e-10` y `rtol=1e-8` para los valores flotantes de esta reproducción. Selecciona perfiles explícitos `A`, `B_fixed_seed` y `C_reconstructed`. El perfil B comprueba repetición con las semillas registradas; no sustituye la calibración entre semillas. El perfil C sólo corresponde a tablas derivadas: los snapshots crudos requieren hashes exactos.

La calibración entre semillas y la revisión de aplicabilidad de diagnósticos Tier D tienen estado pendiente y no se activan con tolerancias supuestas. El contrato cubre las 77 salidas actuales de JPM V2; no añade automáticamente los objetos históricos H1–H5 o los diagnósticos de otra especificación.

## Documentos

Se leen directamente las celdas de ambos Word. Las 144 celdas de resultados se cotejan contra valores congelados de la reproducción Docker verificada, mientras se comprueban por separado las 77 salidas científicas que sustentan los resultados. Las 20 celdas adicionales S1–S2 se calculan desde el registro de valores regenerado, incluido entre esas comparaciones. Las 144 verificaciones científicas originales siguen dentro de la cadena. No se utiliza un JSON previo con estado PASS para aceptar el cotejo documental.

## Pruebas del verificador

```powershell
python -m pytest -q -p no:cacheprovider tests/test_verifier.py
```

La suite utiliza copias temporales para probar cifras alteradas, claves duplicadas, filas o columnas faltantes, tipos incompatibles, nulos/infinitos, matrices y JSON dañados, hashes incorrectos y comprobaciones documentales. El rechazo mantiene su efecto incluso con Python ejecutado con `-O`. Las tolerancias más amplias usadas en una prueba sintética no modifican los perfiles científicos del paquete.
