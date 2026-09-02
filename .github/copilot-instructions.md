# Instrucciones para GitHub Copilot

## Qué es esto

Comparador de precios entre supermercados (Mercadona, Hipercor, Alimerka).
Dado un código postal y una lista de la compra, busca cada producto en los
supermercados elegidos, muestra todas las opciones encontradas (todas las
marcas/variedades) y calcula: la lista más barata repartida entre
supermercados vs. el mejor supermercado único, más el ahorro entre ambos
escenarios. También lleva un presupuesto mensual (solo en el frontend, vía
`localStorage`, sin backend).

Hay dos formas de usarlo: un CLI (`src/main.py`) y una webapp local
(Flask + PWA en `webapp/`). **Todo en español**: código, comentarios,
nombres de variables/funciones, commits y documentación. Sigue esa
convención en cualquier código nuevo que generes.

Para el contexto completo de arquitectura (por qué cada conector funciona
como funciona, decisiones ya probadas y descartadas), lee siempre
`CLAUDE.md` en la raíz del repo antes de proponer cambios.

## Cómo construir, probar y validar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # una sola vez, solo hace falta para Mercadona

# CLI
python -m src.main --cp 33012 --lista data/lista_compra_ejemplo.json

# Webapp
cd webapp && python app.py       # abre http://localhost:5000
```

No hay suite de tests, linter ni build configurados. Antes de dar por
válido un cambio:
- Compílalo (`python -m py_compile <archivo>` o `node --check app.js`).
- Verifica la lógica con datos simulados si no hay red disponible —
  `src/compare.py` y el matching por similitud de `webapp/static/app.js`
  (función `encontrarAlternativaMasBarata`) se probaron así, sin acceso
  real a las webs de los supermercados.
- No asumas cómo responde la web de un supermercado sin comprobarlo en
  vivo. Ya hubo un caso real: se asumió que Mercadona tenía una API JSON
  pública sencilla (recordado de proyectos de la comunidad) y resultó ser
  falso — usa Akamai Bot Manager con rutas ofuscadas. Verificar en vivo
  antes de escribir el conector evitó ese error.

## Arquitectura (resumen — ver CLAUDE.md para el detalle completo)

- `src/supermarkets/` — un conector por supermercado (`Supermercado` en
  `base.py`), todos implementan `buscar_productos(nombre)` devolviendo
  TODAS las opciones encontradas, no solo la más barata.
- `alimerka.py` — HTML renderizado en servidor, `requests` normal.
- `mercadona.py` y `hipercor.py` — Playwright con navegador **visible**
  (`headless=False`): en headless, Hipercor devuelve 403 y Mercadona no
  carga resultados. No lo cambies a headless sin volver a verificarlo.
- `src/compare.py` — compara por coste real (no por precio de etiqueta),
  usado por el CLI. La webapp llama a los conectores vía `/api/buscar`
  porque necesita TODAS las opciones, no solo un precio por producto.
- `webapp/static/app.js` — todo el estado (lista, presupuesto, historial,
  selección por producto) vive en `localStorage`, sin backend propio para
  eso. El algoritmo de "más barato en otro súper" pesa cada palabra del
  nombre de producto por rareza dentro de esa búsqueda (similar a
  TF-IDF), para no confundir productos distintos que comparten palabras
  genéricas ("leche", "cocidos").

## Requisito no negociable del proyecto

Todo debe poder desplegarse y ejecutarse **100% gratis** (cuenta Azure
gratuita + GitHub Actions gratuito para el scraping programado de
Mercadona). No propongas servicios de pago como parte del flujo normal.
