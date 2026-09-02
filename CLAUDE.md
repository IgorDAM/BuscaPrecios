# Contexto técnico de BuscaPrecios

Este repositorio implementa un comparador de precios entre Mercadona, Hipercor y Alimerka.

## Decisiones clave

- Cada conector de supermercado implementa la clase base `Supermercado`.
- `buscar_productos(nombre)` devuelve todas las coincidencias encontradas, no solo una.
- `mercadona.py` y `hipercor.py` están preparados para ejecución con Playwright en `headless=False`.
- `src/compare.py` calcula el coste real por unidad (`precio / cantidad`) cuando hay cantidad disponible.
- La webapp mantiene estado local (`lista`, `presupuesto`, `historial`, `selecciones`) en `localStorage`.
- `encontrarAlternativaMasBarata` en `webapp/static/app.js` usa un peso por rareza de términos para evitar falsos positivos por palabras genéricas.

## Notas de desarrollo

- Se prioriza funcionamiento local y simulación cuando no hay conectividad externa.
- Todo el código y documentación se mantiene en español.
