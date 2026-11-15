# Obtención de los originales

Las versiones usadas se descargaron el 10 de julio de 2026. INPUT_CONTRACT.json y metadata/ conservan las URL, fechas históricas y hashes. Los portales oficiales se consultaron el 14 de noviembre de 2026; esta reconstrucción utilizó los archivos locales congelados. No se volvió a descargar el contenido de los proveedores.

| Encuesta | Original requerido | Fuente |
|---|---|---|
| ENAHO 2024 | 966-Modulo34.zip; dentro, sumaria-2024.dta estándar, excluyendo 12g | [Portal INEI](https://proyectos.inei.gob.pe/microdatos/) · [ZIP histórico](https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip) |
| CASEN 2024 | casen_2024.sav, 749.656.107 bytes en la copia congelada | [Portal CASEN 2024](https://observatorio.ministeriodesarrollosocial.gob.cl/encuesta-casen-2024) · [SPSS histórico](https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/casen_2024.sav) |

El libro de códigos CASEN está enlazado en el portal y su URL y hash históricos se conservan en metadata/CHL.json. No es necesario para ejecutar las fórmulas, pero permite revisar las variables seleccionadas.

Tras consultar las condiciones del proveedor, puede guardar los archivos manualmente en las rutas del README o utilizar el programa de descarga:

```powershell
python acquire_surveys.py --country both --destination 'D:\replicacion\encuestas'
```

El programa verifica un archivo existente y no lo sobrescribe. Cada descarga nueva se guarda primero como .part y sólo se incorpora cuando su SHA-256 coincide con la versión congelada. Si el proveedor entrega una versión revisada, el programa se detiene y conserva el archivo provisional para inspección. Una versión distinta debe tratarse como actualización de datos, no como réplica exacta. Los portales y enlaces pueden cambiar; una descarga con el mismo nombre no garantiza la misma versión.

El programa de descarga se comprobó para la validación de archivos existentes y el rechazo de versiones distintas o descargas parciales; la descarga remota completa no se volvió a ejecutar en esta etapa.
