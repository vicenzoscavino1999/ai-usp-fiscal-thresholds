# Variables y cálculo de los comparadores

La línea PIP PPP 8,30, expresada en moneda local por persona y año, procede de poverty_distribution_anchor.parquet: PEN 6.835,9866112358295 para Perú y CLP 1.825.919,8813448949 para Chile. Se verifica la identidad del costo agregado: población × línea × brecha de pobreza × chi × theta. Las conversiones y los valores macroeconómicos proceden del núcleo ya reproducido.

En Perú se usan INGHOG2D anual, MIEPERHO y FACTOR07. El costo ideal es la suma por hogar de FACTOR07 × max(línea × MIEPERHO − INGHOG2D, 0). El programa original expresa la misma operación por persona y usa FACTOR07 × MIEPERHO como peso. Se conservan las sensibilidades de gasto GASHOG2D y línea nacional mensual LINEA anualizada por 12. La validación nacional contrasta el gasto por persona con LINEA y la clasificación POBREZA; no confunde esa validación con la comparación de ingreso a la línea PIP.

En Chile se validan primero las personas con pobreza en {1,2,3}, yae no ausente, lp positiva y expr positivo. Se comprueba constancia de las variables de hogar dentro de folio, se toma una observación por hogar y se verifica que expr × numper reproduce la suma de los pesos de personas válidas. El costo ideal es la suma de expr × max(línea × numper − 12 × ytotcorh, 0). ytotcorh es ingreso mensual total corregido; la anualización por 12 se aplica una sola vez. Se conservan las sensibilidades de ingreso monetario ymonecorh y metodología nacional con yae, lp y nae.

Las variantes ampliadas aplican theta a la misma brecha. La diferencia porcentual es 100 × (costo de encuesta / costo agregado − 1). Se mantienen las definiciones y las funciones de cálculo de los programas originales. El ejecutor carga únicamente las funciones de anclas, validación y costos mediante AST, con hashes por función; no ejecuta los antiguos modelos fiscales incluidos en esos archivos históricos.

La comprobación independiente suma las brechas monetarias por hogar con math.fsum, usando la identidad alternativa anterior. Las referencias CSV y las proyecciones Parquet archivadas se leen sólo después de completar los cálculos. Ninguna proyección de registros individuales se escribe en las salidas.

La identidad de las anclas regeneradas compara todas las columnas científicas y el esquema. Únicamente build_id y created_at se tratan como metadatos de ejecución; sus valores no entran al hash semántico. Las fuentes originales y el código continúan sujetos a hashes binarios exactos.
