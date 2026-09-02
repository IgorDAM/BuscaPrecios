# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es esto

Comparador de precios entre supermercados (Mercadona, Hipercor, Alimerka).
Dado un código postal y una lista de la compra, busca cada producto en los
supermercados elegidos, muestra todas las opciones encontradas (todas las
marcas/variedades) y calcula: la lista más barata repartida entre
supermercados vs. el mejor supermercado único, más el ahorro entre ambos
escenarios. También lleva un presupuesto mensual (solo en el frontend, vía
`localStorage`, sin backend).

Hay dos formas de usarlo: un CLI (`src/main.py`) y una webapp local
(Flask + PWA en `webapp/`). Todo en español (código, comentarios, docs).

## Comandos

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # una sola vez, solo hace falta para Mercadona

# CLI
python -m src.main --cp 33012 --lista data/lista_compra_ejemplo.json

# Webapp (recomendado)
cd webapp && python app.py       # abre http://localhost:5000
```

No hay suite de tests, linter ni build configurados en el repo. `compare.py`
se verificó manualmente con datos de prueba; el matching por similitud de
`app.js` se probó con `node app.js` (función `encontrarAlternativaMasBarata`).

## Arquitectura

**`src/supermarkets/`** — un "conector" por supermercado, todos heredan de
`Supermercado` (`base.py`) e implementan `buscar_productos(nombre)` (TODAS
las opciones que devuelve el buscador de esa web) y opcionalmente confían en
el atajo heredado `buscar_producto(nombre)` (la más barata de las opciones).
Esto es lo que permite que `compare.py` y la webapp traten a los tres
supermercados de forma idéntica sin importar cómo obtienen el precio por
dentro:

- `alimerka.py` — HTML renderizado en servidor, `requests` normal (sin
  JS). Verificado en vivo. Cada resultado trae marca y nombre por
  separado (primer/segundo `a.link` de cada tile).
- `mercadona.py` y `hipercor.py` — usan **Playwright** con navegador
  **visible** (`headless=False`), configurado en `navegador.py`. Esto no
  es opcional y no es paranoia: verificado el 2026-08-10 que en headless
  Hipercor devuelve 403 a todo (incluida la portada sin cookies) y la
  búsqueda de Mercadona nunca llega a cargar resultados. Las
  contramedidas típicas (User-Agent real, `AutomationControlled`, ocultar
  `navigator.webdriver`) **no bastan**; la ventana se abre fuera de
  pantalla (`--window-position=-2400,-2400`) para no molestar. Ambos
  exponen `buscar_productos_multiples()` para reutilizar un solo
  navegador en toda la lista.
- Mercadona fija la zona de entrega **escribiendo el CP en el formulario
  de la propia web** (`postal-code-checker`), no inyectando la cookie
  `__mo_da` a mano: la web descarta la cookie inyectada y devuelve
  búsquedas vacías. Por eso Mercadona ya no tiene mapa de almacenes
  hardcodeado; Hipercor sí lo mantiene (`CENTROS_CONOCIDOS`).
- Mercadona necesita pasar por `about:blank` entre búsquedas: si no, la
  SPA conserva en pantalla los resultados de la búsqueda anterior y se
  leen productos equivocados.
- `_buscar_uno()` devuelve `None` (no cargó) o `[]` (cargó pero no lo
  vende), y `buscar_productos_multiples()` aborta con `SupermercadoCaido`
  tras 2 `None` seguidos. La distinción importa: si un supermercado está
  bloqueado cada búsqueda agota 25 s, pero contar los `[]` como fallo
  mataría el supermercado por buscar dos productos raros seguidos.
- Hipercor y Mercadona fijan la zona de entrega vía cookie ligada al CP
  (`ff_food_center` en Hipercor, `warehouse` en Mercadona), y solo tienen
  mapeado 33012 (Oviedo) en `CENTROS_CONOCIDOS`/`ALMACENES_CONOCIDOS` — hay
  que añadir el valor correspondiente ahí si se necesita otro CP. Alimerka
  resuelve el CP automáticamente, sin ese problema.

**`medidas.py`** — normaliza formatos a kg/L y calcula el precio por
kilo/litro, porque comparar por precio de paquete engaña con lo que se
vende al peso (jamón a 2,29 € = 19,08 €/kg frente a 2,30 € = 25,56 €/kg,
verificado). Cada web lo cuenta distinto: Hipercor lo da ya calculado
(`measurementUnitPrice`), Mercadona en el texto de la tarjeta ("Paquete
120 Gramos", "6 briks x 1 Litro") y Alimerka **solo dentro del nombre**
("JAMÓN SERRANO RESERVA 120 G."). La interfaz muestra el €/kg de cada
opción y marca "Mejor €/kg", que a menudo no es el paquete más barato.

**`filtrar_relevantes()` (en `base.py`)** — los buscadores de los súper
devuelven, tras los resultados buenos, secciones enteras de
"relacionados" (buscar "huevos" en Mercadona da 91 resultados con natas y
batidos). Como la app ordena todo por precio y preselecciona lo más
barato, sin filtrar elegiría una bebida de avena como "los huevos más
baratos". El filtro exige que el nombre contenga todas las palabras
buscadas **y** que la primera empiece el nombre, con fallback progresivo
para no dejar nunca la lista vacía. Se aplica en `webapp/app.py` y en
`Supermercado.buscar_producto()` (el atajo que usa el CLI).

**`src/compare.py`** — dado `List[LineaCompra]` (nombre + cantidad +
unidad) y `supermercados: dict[str, Supermercado]`, produce un
`ResultadoComparacion` con dos escenarios: `lista_optima_repartida()` y
`mejor_supermercado_unico()`. Compara por **coste real** (`coste()`, misma
regla granel/paquete que `costeDe()` en el frontend), no por precio de
etiqueta. Un fallo en un conector deja ese precio como `None` sin romper la
comparación. Solo lo usa el CLI; la webapp llama a los conectores vía
`/api/buscar` porque necesita TODAS las opciones.

**`src/main.py`** — CLI. Acepta listas en formato antiguo (array de
strings) y nuevo (objetos con `cantidad`/`unidad`), y `--solo` para elegir
supermercados.

**`webapp/app.py`** — servidor Flask local. Sirve `webapp/static/` y expone
`POST /api/buscar` (todas las opciones por producto) y `DELETE /api/cache`.
Devuelve `avisos` por supermercado que falla o no devuelve nada — sin eso
es imposible distinguir "no lo venden" de "está bloqueado", que fue una
fuente real de confusión.

Escucha en `host="0.0.0.0"` (configurable con la variable de entorno
`HOST`, igual que `PORT` y `DEBUG`) para servir en modo LAN: se instala
una sola vez en el ordenador que se deja encendido, y el resto de
dispositivos de casa (otro PC, móvil) entran por IP sin instalar nada.
Al arrancar imprime esa IP calculándola con un socket UDP a un DNS
público (no llega a enviar tráfico real, solo sirve para que el SO
resuelva la interfaz de salida). El presupuesto/historial/lista de la
compra siguen sin compartirse entre dispositivos porque viven en
`localStorage` de cada navegador; lo que sí comparten todos los
dispositivos que hablan con el mismo servidor es la caché de precios
(`webapp/cache.py`).

**El frontend llama a `/api/buscar` una vez por supermercado, en
paralelo.** Es lo que da el paralelismo (Flask atiende en hilos) y el
progreso por súper: el total pasa a ser el del más lento en vez de la suma
(14 s medidos frente a ~23 s).

**`webapp/cache.py`** — precios guardados 6 h en `webapp/.cache_precios/`
(JSON por supermercado+CP). No es solo velocidad (0,4 s frente a 14 s):
reduce las visitas a las webs, que es lo que dispara los bloqueos de
Akamai. `_pendientes()` en `app.py` solo pide a la web lo que no esté
cacheado.

**`webapp/static/app.js`** — todo el estado (lista de la compra, presupuesto,
historial de compras, selección de producto por producto) vive en el
navegador vía `localStorage`, sin backend propio para eso. Cada línea de
la lista es `{nombre, cantidad, unidad}` con `unidad` = `"ud"` o `"g"`
(botón para alternar). En gramos, `costeDe()` distingue dos casos porque
cobrar igual en ambos da precios que no existen en caja: **a granel** (el
precio anunciado ya es el del kilo, detectado con `esAlPeso()`: precio ==
precio_unidad) se paga exactamente lo pedido; **en paquete** hay que
llevarse paquetes enteros, así que se redondea hacia arriba (300 g de
jamón = 3 paquetes de 120 g = 6,87 €, no 5,72 €). Si no se conoce el peso,
se cuenta un paquete. Los formatos antiguos de la lista (array de strings,
o sin `unidad`) se migran solos al leerlos. Implementa el
algoritmo de "más barato en otro súper": pesa cada palabra del nombre de
producto por rareza entre las opciones de esa búsqueda (similar a TF-IDF) y
exige compartir al menos una palabra "distintiva" (marca/variedad) para
considerar dos opciones de supermercados distintos como el mismo producto —
así evita falsos positivos por palabras genéricas compartidas (p.ej. "leche",
"cocidos"). No es infalible: siempre se muestra el nombre completo de cada
opción para que el usuario confirme.

## Despliegue en la nube (sin backend, sin PC encendido)

Verificado en vivo (2026-09-02, ver README para el detalle completo del
experimento): un runner de GitHub Actions con `xvfb-run` SÍ puede pasar
Mercadona e Hipercor (no están bloqueados por Akamai desde ahí; el fallo
que se veía al principio era intermitencia por la IP del runner, no un
bloqueo sistemático). Esto habilitó un pipeline sin backend:

- **`scripts/generar_precios.py`** busca `data/lista_compra_habitual.json`
  en los tres supermercados y escribe
  `webapp/static/precios_generados.json`. Reintenta el conector
  ENTERO (no solo una búsqueda suelta) hasta 3 veces si Hipercor/
  Mercadona devuelven 0 resultados o lanzan excepción, precisamente por
  esa intermitencia.
- **`.github/workflows/precios-cron.yml`** ejecuta ese script a diario y
  comitea el JSON resultante si cambió (necesita "Read and write
  permissions" en Settings -> Actions -> General del repo).
- **`webapp/static/app.js`**: `buscarEnSuper()` intenta primero
  `/api/buscar` (modo LAN/local con backend Flask); si falla (no hay
  backend, como en un sitio estático), cae a leer
  `precios_generados.json` y filtra por supermercado y productos
  pedidos. Limitación real de este modo: solo cubre lo que esté en
  `lista_compra_habitual.json`, no búsquedas libres.
- **`webapp/static/staticwebapp.config.json`**: config mínima para Azure
  Static Web Apps (plan gratuito), que sirve `webapp/static/` tal cual.

Ver README.md, sección "Cómo activar la versión en la nube", para el
paso manual que falta (crear el recurso Static Web App en el Portal de
Azure — no se puede hacer por código, necesita la cuenta del usuario).
Búsquedas fuera de la lista habitual sin esperar al cron: sigue siendo
el modo LAN (ver sección de modo LAN más arriba), o una futura Azure
Function solo para Alimerka (no tiene el problema de Akamai). Repo ya
subido a GitHub: `github.com/IgorDAM/BuscaPrecios`. Requisito explícito
del proyecto: todo debe poder correr 100% gratis.
