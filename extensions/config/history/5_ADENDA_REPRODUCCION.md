# Aplicación del plan existente a JPM V2

Se conserva como autoridad metodológica REPRODUCIBILITY_PLAN.md y como antecedente operativo REPRODUCING.md del paquete 1.1.1. Esta adenda delimita las modificaciones de integración necesarias para reproducir los resultados científicos de 7g–7h que aparecen en los documentos 7k.

1. Inventario con hashes y procedencia; separación entre entradas congeladas, resultados esperados y resultados reconstruidos.
2. Entorno Python nuevo, lock con hashes y comprobación de dependencias.
3. Ejecución de transformaciones, sorteos registrados, fronteras, inversas, financiación, reconciliación y sensibilidades en copia autónoma; sin acceso a carpetas originales durante el cálculo.
4. Comparación de claves, esquemas, valores, clasificaciones y cifras del manuscrito; tolerancias Tier A atol=1e-10/rtol=1e-8 y Tier B según plan. Con el mismo entorno y semilla se exige además identidad de conteos.
5. Registro de discrepancias, conservación de logs y cierre sólo del alcance efectivamente completado.

No se ejecutan scripts históricos de cierre ni se sobrescriben etapas selladas. La reproducción interna no es identificación causal ni evaluación externa. El depósito y la entrega editorial permanecen en el paso 8.
