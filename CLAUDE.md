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
- **`.github/workflows/precios-cron.yml`** ejecuta ese script cada 6h,
  comitea el JSON resultante si cambió (necesita "Read and write
  permissions" en Settings -> Actions -> General del repo) y **despliega
  él mismo en Azure Static Web Apps** tras el commit. Esto último es
  necesario por algo verificado en vivo (2026-09-02) y que NO es
  intuitivo: el workflow de Azure
  (`azure-static-web-apps-*.yml`, `on: push` a `master`) no se dispara
  con el push que hace este cron, porque ese push lo firma
  `github-actions[bot]` con el `GITHUB_TOKEN` por defecto, y GitHub
  bloquea explícitamente que los pushes hechos con ese token disparen
  otros workflows (protección anti-bucles). Sin el paso de despliegue
  añadido aquí, el repo se actualizaba pero la web publicada se quedaba
  con datos viejos indefinidamente, sin ningún error visible que lo
  delatase.
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

## Precisión del matching en búsquedas libres (verificado en vivo, 2026-09-03)

Se simuló en modo LAN un ticket de compra real de Alimerka (25 líneas,
CP 33012) para comprobar si el precio que devuelve la app coincide con lo
que de verdad se pagó en caja. Se comparó cada línea contra **todas** las
opciones que trae `/api/buscar` (no solo la preseleccionada), porque la
preselección "más barato" no es fiable como termómetro de precisión: en
esta prueba habría elegido potitos de bebé en vez de un plátano y un mango
de fregona en vez de la fruta (ver más abajo).

**Cuando el nombre buscado es inequívoco (marca + producto:
"aceite carbonell", "nocilla pistacho", "queso oscos barra", "cecina de
vacuno"...), Alimerka acierta el precio al céntimo**: 9 de las 25 líneas
del ticket aparecían en las opciones devueltas con el precio exacto de
caja (5,75 €, 1,10 €, 3,99 €, 13,45 €/kg, 31,95 €/kg...). El dato de
precio en sí es fiable; lo que falla es que hay que elegir la opción
correcta a mano — la preselección automática coge la más barata de la
búsqueda, que casi nunca es la que se compró.

**Falla por completo (0 resultados o resultado sin relación) en 7 de 25
líneas, casi todas por el mismo patrón — producto a granel/fresco de
mostrador, o palabra ambigua en español sin desambiguar**:

- "mango" devuelve mangos de fregona/metal (1,30-1,40 m), cero fruta.
- "banana ecologica" solo encuentra potitos de bebé ("Pouch fresa y
  plátano"), ninguna banana real — probablemente porque en Alimerka la
  fruta se cataloga como "plátano", no "banana".
- "zanahorias" (a granel en el ticket) solo trae zanahoria rallada,
  zanahoria baby envasada y un plato preparado — no hay SKU de zanahoria
  suelta en el catálogo online.
- "bolsa de plastico reciclado" (la bolsa de 0,12 €/ud que da el propio
  súper en caja) devuelve patatas fritas Lay's y bolsas de basura — esa
  bolsa de caja no está en el catálogo buscable.
- "cebolleta manojo" y "huevo eco campomayor" (con marca): 0 resultados.
- "agua aquadeus" solo encuentra la variante con gas de 50cl, no la de
  33cl sin gas del ticket.

Conclusión práctica: `filtrar_relevantes()` y el matching por nombre
funcionan bien para producto envasado con marca reconocible, pero no
tienen forma de acertar con fruta/verdura a granel, productos frescos de
mostrador ni con bolsas/artículos de caja que no están en el catálogo
online del súper — ahí hace falta que el usuario reformule la búsqueda o
acepte que esa línea no se puede verificar por esta vía. No se ha tocado
código a raíz de esto, queda anotado como limitación conocida por si se
quiere mejorar `filtrar_relevantes()` o avisar en la interfaz cuando una
búsqueda de una sola palabra genérica probablemente no es fruta/verdura.

### Reintento con palabra clave única, solo Alimerka (verificado en vivo, 2026-09-03)

Para las 15 líneas problemáticas (7 que fallaban + 8 que traían otra
variante) se repitió la búsqueda restringida a Alimerka y usando solo la
palabra clave del producto (p. ej. "hogaza" en vez de "hogaza tradición
pan artesano"), inspeccionando después el listado completo de opciones
devuelto por `/api/buscar` (vía `fetch()` en la consola del navegador,
no solo la preselección "más barato") para buscar a mano la opción
correcta:

- **Se resuelven 2 con precio exacto**: "hogaza" → HOGAZA TRADICIÓN 400G
  (The Rustik Bakery) = 3,19 €; "vinagre" → VINAGRE DE LIMPIEZA 1L
  (Disiclín) = 0,90 €. En ambos casos la búsqueda original era demasiado
  específica (marca/variante) y una palabra más genérica sí encontraba
  la referencia correcta entre las opciones.
- **13 siguen sin resolverse aunque se simplifique la búsqueda**:
  aquadeus, calgon (antical), cebolleta, magnesio eco, huevos eco,
  banana, chuleta de pavo, ciruela, lomo, mango, bolsa (de la compra),
  zanahoria — más "fuensanta" que queda como near-miss (0,47 € vs
  0,39 € real). Para estos, el problema no es la redacción de la
  búsqueda: el catálogo online de Alimerka no tiene el SKU exacto (fruta
  y verdura a granel, fresco de mostrador, o artículos de caja que no
  se venden por la web), así que ninguna palabra clave lo va a
  encontrar. Confirma la conclusión de la sección anterior: es un hueco
  real de catálogo, no un problema de `filtrar_relevantes()` ni de
  matching de texto.

## Por qué el total simulado se dispara frente al ticket real (verificado en vivo, 2026-09-03)

Con la búsqueda inicial (25 líneas, en los 3 súpers, preselección "más
barato" de cada uno) la app daba un total de 137,47 € frente a los
69,21 € que costó de verdad el ticket de Alimerka — una diferencia de
+68,26 €. Sumando la diferencia (coste app − coste ticket) línea a línea
se reconstruye exactamente esa desviación, y el reparto por causa es:

- **Bug de parseo "EL KILO" (`medidas.py`), +37,68 € — más de la mitad
  del hueco.** `_MEDIDA_RE` exige un número pegado a la unidad ("120 G.",
  "1,5 L") y no reconoce el patrón que usa Alimerka en fresco de
  mostrador: "CECINA DE VACUNO BABILLA EL KILO", "QUESO EN BARRA EL
  KILO" (sin número delante, significa "se vende por kilo"). Al no
  matchear, `parsear_medida()` devuelve `None` y `precio_unidad` queda
  `null`; `costeDe()` en `app.js` aplica entonces su regla de
  "si no se conoce el peso, se cuenta un paquete" y cobra el precio de
  venta COMPLETO como si fuera una sola unidad, en vez de escalarlo a
  los gramos realmente pedidos. Con dos líneas de fresco de mostrador
  esto ya explica más de la mitad de toda la desviación. No se ha
  tocado código todavía — queda documentado como el bug de mayor
  impacto encontrado hasta ahora, candidato claro a arreglar en
  `_MEDIDA_RE` (añadir soporte para "EL KILO"/"EL LITRO" sueltos, sin
  número delante).
- **Otra variante elegida automáticamente (la preselección "más
  barato" no es la que se compró), +40,60 € en conjunto**, con los
  casos más caros siendo: "chuleta de pavo" → pack marinado que obliga
  a comprar 2 unidades (+12,03 €), "banana ecológica" → potitos de bebé
  (+8,16 €), "bolsa" (la de caja, 0,12 €) → patatas fritas Lay's
  (+7,72 €), "ciruela" → caja entera en vez de la cantidad suelta
  (+4,41 €), y en menor medida antical, lomo, zanahoria, vinagre y
  magnesio eco.
- **Compensación parcial a la baja, −10,15 €**: algunas líneas SÍ
  encontraron una opción más barata que el precio real (aceite
  Carbonell, jabón de manos, huevos, mango, leche, hogaza), lo que
  reduce algo el total pero no compensa ni de lejos los dos efectos
  anteriores.

Conclusión: la desviación no es un error sistemático de pesos/cantidades
en `costeDe()` en general (para producto envasado normal el cálculo de
paquetes es correcto) — es la combinación de (1) un bug real y acotado
de parseo de medidas para el patrón "EL KILO" de fresco de mostrador, y
(2) que la preselección automática "más barato" de una búsqueda libre
casi nunca es el producto exacto que se compró, así que arrastra el
precio de variantes más caras (packs más grandes, marcas premium,
formatos que obligan a comprar más unidades de las necesarias).

### Corrección aplicada al bug "EL KILO" (2026-09-03)

Se ha corregido el bug descrito arriba, en dos archivos:

- **`src/supermarkets/medidas.py`**: se añadió `_AL_KILO_RE` (patrón
  `r"\b(?:el|al|por)\s+(kilo|litro)\b"`), usado como fallback dentro de
  `parsear_medida()` cuando `_MEDIDA_RE` no encuentra ningún número
  pegado a la unidad. Si el texto contiene "EL KILO"/"AL KILO"/"POR
  KILO"/"...LITRO" sin número delante, se interpreta como que el precio
  mostrado YA es el del kilo/litro completo (`cantidad=1.0` en esa
  unidad), en vez de devolver `None`.
- **`webapp/static/app.js`**: `esAlPeso()` ahora también reconoce
  `unidad === "L"` además de `"kg"` (antes solo cubría kilos), para que
  el mismo arreglo funcione si algún día aparece un caso "AL LITRO" a
  granel.

**Verificado antes de darlo por bueno** (regla del proyecto) con un
script suelto contra `parsear_medida()`/`precio_por_medida()`, usando
nombres reales de la caché de Alimerka: "CECINA DE VACUNO BABILLA EL
KILO" (31,95 €) y "QUESO EN BARRA EL KILO" (13,45 €) ahora devuelven
`precio_unidad` = su propio precio (31,95 €/kg y 13,45 €/kg), lo mismo
para "LOMO EMBUCHADO EL KILO", "LOMO DE VILLAMANIN-LEON EL KILO", "LOMO
DE EXTREMADURA DUROC EL KILO", "LOMO DE BELLOTA IBERICO EL KILO" y
"JAMÓN SERRANO RVA DUROC 25% MENOS SAL EL KILO" (todos ellos vistos en
la caché real, no inventados). Los casos con número explícito ("JAMÓN
SERRANO RESERVA 120 G.", "GARBANZO PEDROSILLANO 1 KILO", "LECHE ENTERA 1
LITRO", "LOMO ADOBADO EXTRA 400 G.") siguen dando exactamente el mismo
resultado que antes — el cambio no toca ese camino. Un texto sin ninguna
medida ("ANTICAL 15 PASTILLAS") sigue devolviendo `None` como antes.

Con el fix, recalculando a mano `costeDe()` con los datos reales:
"cecina de vacuno" (105 g pedidos) pasa de cobrar 31,95 € a
`31,95 €/kg × 0,105 kg = 3,35 €` — precio EXACTO del tique. "queso oscos
barra" (325 g) pasa de 13,45 € a `13,45 €/kg × 0,325 kg = 4,37 €` —
también exacto. Los +37,68 € que aportaba este bug a la desviación total
quedan corregidos a 0 €.

**Pendiente para que el fix esté en producción**: el servidor Flask
corre con `debug=off` (sin autorecarga), así que hace falta reiniciarlo
(parar con Ctrl+C y volver a `python app.py`) para que cargue el
`medidas.py` nuevo, y recargar la pestaña del navegador para que sirva
el `app.js` nuevo. Se vació también la caché de precios
(`webapp/.cache_precios/*.json`) para forzar que la próxima búsqueda
recalcule `precio_unidad` con la lógica corregida en vez de servir el
valor `null` ya guardado.

### Selecciones manuales corregidas en la simulación del ticket (2026-09-03)

Al simplificar las búsquedas problemáticas a una sola palabra clave (ver
sección anterior), la app auto-selecciona por defecto la opción "más
barata" de esa nueva búsqueda, que en varios casos coincide por
casualidad de nombre con un producto totalmente distinto — un problema
nuevo, más allá del ya conocido de que "más barato" no es "el que se
compró". Ejemplos reales encontrados: "banana" pasó a emparejar con unos
polvos de maquillaje llamados "Banana"; "huevos" con huevos de chocolate
de Pascua; "magnesio" con pastillas de Magnesio+B6; "bolsa" con bolsas
de basura para cartón; "vinagre" y "hogaza" con variantes distintas a
las que se habían identificado a mano revisando el listado completo.

Se corrigió fijando a mano (con `elegirOpcion()`, no solo identificando
la opción correcta al leer el JSON) la selección real de cada línea:

- **Coincidencia exacta de precio, ahora sí aplicada de verdad**:
  "aceite carbonell" → ACEITE DE OLIVA VIRGEN EXTRA 1 LITRO, 5,75 €
  (antes tenía seleccionado por error el de 250 ml a 2,35 €); "hogaza" →
  HOGAZA TRADICIÓN 400G de The Rustik Bakery, 3,19 € (el código del
  tique "HOG.TRAD.RUS.BAKERY" es literalmente esto); "vinagre" →
  VINAGRE DE LIMPIEZA 1L Disiclín, 0,90 €.
- **Mejor coincidencia real disponible (no exacta, pero sí el producto
  correcto)**: "magnesio" → EKO Cereales Solubles con Magnesio 150 G.
  (mismo nombre y gramaje que el tique, 3,85 € vs 3,00 €); "calgon" →
  Antical Calgon 15 Pastillas, 7,99 € vs 5,99 € (única referencia real
  de "antical calgon" en el catálogo); "ciruela" → Ciruela Claudia caja
  de 1,25 kg de Sabrosona (la variedad correcta, aunque haya que llevarse
  la caja entera); "lomo" → Cinta de Lomo de Cerdo Fileteada Campofrío;
  "pavo" (para "chuleta de pavo" del tique) → Chuletas de Pavo Marinadas
  al Ajillo de Aldelís, la única referencia real de chuletas de pavo.
- **Se ha quitado la selección** (mejor "sin elegir" que un precio
  disparatado) en 5 líneas donde la búsqueda de una palabra encontró un
  producto sin ninguna relación real y no hay sustituto razonable en el
  catálogo de Alimerka: "banana", "bolsa", "huevos", "mango". "cebolleta"
  ya no tenía selección guardada (0 resultados en Alimerka). Estas 5
  líneas (13,03 € del tique real: 1,65+0,48+6,38+2,19+2,33) confirman ser
  huecos genuinos de catálogo — fruta/verdura suelta, fresco de
  mostrador y artículos de caja que Alimerka no vende por su web —, no
  errores de búsqueda.

Total recalculado a mano con `costeDe()` sobre las 20 líneas que sí
tienen selección razonable (antes de reiniciar el servidor, así que
"cecina de vacuno" y "queso oscos barra" TODAVÍA reflejan el bug de
"EL KILO" sin corregir): 114,92 €, frente a 56,18 € de esas mismas 20
líneas en el tique real. Con el fix de "EL KILO" ya aplicado (pendiente
de reinicio del servidor) esas dos líneas pasan a costar exactamente lo
mismo que en el tique (3,35 € y 4,37 €), así que el total de esas 20
líneas bajaría a 77,24 € — quedando +21,06 € de desviación explicada por
variantes reales pero distintas a las compradas (pack marinado de pavo
+12,03 €, caja de ciruelas en vez de sueltas +4,41 €, 3 packs de
zanahoria baby en vez de a granel +1,78 €, lomo envasado +1,95 €, antical
+2,00 €, magnesio +0,85 €... compensado en parte por jabón de manos y
leche más baratos).
