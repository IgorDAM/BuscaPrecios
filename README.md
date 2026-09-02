# Comparador de Supermercados

Con tu lista de la compra, busca en Mercadona, Hipercor y Alimerka (tú
eliges cuáles, con un checkbox por supermercado) y te enseña TODO lo que
encuentra para cada producto: si buscas "leche" verás todas las leches
del súper; si buscas "leche entera" solo las de leche entera, con marca
y precio; si buscas "leche central lechera asturiana" solo esa marca.
Eliges la opción que quieras por producto (o dejas que se preseleccione
la más barata), y si lo que elegiste existe más barato en otro
supermercado con un nombre parecido (misma marca/variedad), te avisa.

También lleva un presupuesto mensual: registras cada compra y ves cuánto
llevas gastado, cuánto te queda, y cuánto has ahorrado repartiendo la
compra entre supermercados en vez de comprarlo todo en el más caro.

## Estado actual

| Supermercado | Cómo obtiene los precios | Estado |
|---|---|---|
| Alimerka | HTML renderizado en servidor (`requests` normal, sin JS) | Implementado y **verificado en vivo**, entrando como invitado con tu CP. |
| Hipercor | Navegador real **visible** vía Playwright (ver por qué, abajo) | Implementado y **verificado en vivo**. |
| Mercadona | Navegador real **visible** vía Playwright | Implementado y **verificado en vivo**, fijando la zona de entrega con el formulario de su propia web. |

He comprobado en un navegador real que la lógica de extracción de
precios funciona con datos reales de cada supermercado (leche entera a
0,96 € tanto en Hipercor como en Alimerka; manzanas a 3,45 €/0,54 €/0,46 €
en Mercadona, etc). La lógica de comparación (`src/compare.py`) también
está verificada con datos de prueba, y no depende de que los tres
conectores funcionen: si un supermercado falla o no encuentra un
producto, simplemente lo excluye de esa comparación en vez de romper
todo.

**Por qué dos de ellos necesitan un navegador de verdad**: tanto
tienda.mercadona.es como hipercor.es están detrás de Akamai Bot Manager.
Comprobado en vivo el 2026-08-10:

- Con `requests` normal, Hipercor devuelve **403 Access Denied** a todo,
  incluida la portada sin cookies (antes funcionaba; dejó de hacerlo).
- Con Playwright en **modo headless**, Hipercor sigue dando 403 y la
  búsqueda de Mercadona nunca llega a cargar los resultados.
- Con Playwright y **navegador visible**, los dos responden con
  normalidad.

Probé también las contramedidas habituales en headless (User-Agent de un
Chrome real, `--disable-blink-features=AutomationControlled`, ocultar
`navigator.webdriver`) y **no bastan**. Por eso se abre un navegador de
verdad, colocado fuera de la pantalla (`--window-position=-2400,-2400`)
para que no moleste. Esto es lo que condiciona el despliegue (ver abajo).

**Zona de entrega**: Mercadona la fija escribiendo el código postal en el
formulario de su propia web, así que es la web quien decide el almacén y
no hay nada codificado a mano. Hipercor sí mantiene un mapa
(`CENTROS_CONOCIDOS`) con el centro de tu CP: `33012 -> 0703-DELIVERY`;
si cambias de CP hay que añadir el valor ahí (instrucciones dentro del
archivo). Alimerka resuelve el CP solo en cada ejecución.

**Caché**: cada búsqueda se guarda 6 horas en `webapp/.cache_precios/`.
Repetir una búsqueda es entonces instantáneo (0,4 s frente a 14 s
medidos) y, sobre todo, se hacen muchas menos visitas a las webs, que es
justo lo que dispara los bloqueos de Akamai. Para forzar precios frescos:
`curl -X DELETE http://localhost:5000/api/cache`.

## Cómo probarlo

### Opción A: por terminal (CLI)

```bash
python -m venv .venv
source .venv/bin/activate  # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium   # una sola vez, solo para Mercadona

python -m src.main --lista data/lista_compra_ejemplo.json

# solo algunos supermercados (Alimerka es el único que no abre navegador)
python -m src.main --lista data/lista_compra_ejemplo.json --solo alimerka
```

Edita `data/lista_compra_ejemplo.json` con tu lista real (o crea tu propio
archivo y pásalo con `--lista`). Cada producto puede ser un texto suelto
o llevar cantidad y unidad:

```json
{ "productos": [
    "leche entera",
    { "nombre": "jamon serrano", "cantidad": 300, "unidad": "g" },
    { "nombre": "yogur natural", "cantidad": 2, "unidad": "ud" }
] }
```

### Opción B: interfaz web (PWA), recomendada

```bash
python -m venv .venv
source .venv/bin/activate  # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium   # una sola vez, solo para Mercadona

cd webapp
python app.py
```

Abre `http://localhost:5000` en el navegador. Al arrancar, la propia
consola imprime la IP de tu ordenador en la red local (algo como
`http://192.168.1.XX:5000`) — esa es la dirección que hay que usar desde
**cualquier otro dispositivo de casa** (el portátil de tu mujer, un móvil,
una tablet), siempre que estén en el mismo WiFi/red que este ordenador.
No hace falta instalar nada en esos otros dispositivos: solo abrir esa
dirección en su navegador. Detalles y solución de problemas en
"Usar la app desde otro dispositivo de casa", más abajo.

Ahí puedes:

- Poner un **presupuesto mensual** y ver cuánto llevas gastado este mes,
  cuánto te queda, y cuánto has ahorrado en total (barra de progreso +
  historial de compras registradas). Se guarda en el navegador
  (`localStorage`), sin backend.
- Gestionar tu lista de la compra, indicando **cuánto quieres de cada
  cosa**: en unidades o **en gramos** (botón `ud`/`g`), para lo que se
  vende al peso. La cantidad se puede escribir directamente.
- Ver el **precio por kilo/litro** de cada opción, que es lo único que
  permite comparar cuando los formatos no coinciden: 2,29 € de jamón
  (120 g) son 19,08 €/kg y 2,30 € (90 g) son 25,56 €/kg, aunque parezcan
  el mismo precio.
- Marcar qué supermercados quieres comparar (Hipercor, Alimerka,
  Mercadona — cualquier combinación, hasta uno solo).
- Pulsar "Buscar precios": los tres supermercados se consultan **a la
  vez** y cada uno aparece en cuanto contesta, con su propio indicador de
  progreso (así se ve si uno falla en vez de esperar a ciegas). Cada
  producto es una tarjeta desplegable con TODAS las opciones encontradas.
- Las opciones se ordenan por **lo que realmente te costaría** lo que has
  pedido, no por el precio de la etiqueta: si pides 300 g y el paquete es
  de 120 g, cuentan tres paquetes. También puedes ordenar por €/kg.
- Un **TOTAL** al final con la suma de todo lo elegido.
- Si la opción que elegiste tiene una alternativa parecida (misma marca
  o variedad, según el nombre) más barata en otro supermercado, aparece
  un aviso con el botón "Usar este" para cambiarla en un toque. Este
  emparejamiento es por similitud de texto entre nombres — bueno pero no
  infalible; siempre se enseña el nombre completo de cada opción para
  que lo confirmes tú.
- Botón "Elegir lo más barato en todo" para preseleccionar de golpe la
  opción más barata en cada producto.
- Pulsar "Registrar esta compra en el mes" para sumar el total de tu
  selección al presupuesto y vaciar la lista, lista para la próxima
  compra.
- Pulsar "Instalar" para añadirla a la pantalla de inicio del móvil
  como una app normal (es una PWA).

Esta versión corre en tu ordenador — para que funcione desde el móvil
sin tenerlo encendido, el siguiente paso es desplegar `webapp/app.py`
(adaptado) en Azure, ver más abajo.

## Usar la app desde otro dispositivo de casa (modo LAN)

Solo hace falta el código y la instalación (Python, venv, Playwright) en
**un ordenador** — el que se vaya a dejar encendido cuando se quiera usar
la app. Los demás dispositivos de casa (otro PC, un móvil, una tablet)
**no necesitan instalar nada**: solo abrir un navegador.

1. En el ordenador que hace de servidor: `cd webapp && python app.py`
   como siempre. La consola imprime dos líneas al arrancar:
   - `Accesible en este PC: http://localhost:5000`
   - `Accesible desde otros PCs/móviles de casa: http://<IP>:5000`
2. En el otro dispositivo (misma red WiFi/cable que el ordenador
   servidor), abre esa segunda dirección en el navegador. Ya está.
3. Dos cosas a tener en cuenta:
   - **Firewall de Windows**: la primera vez que arranca el servidor,
     Windows puede preguntar si permite a Python comunicarse en redes
     privadas — hay que decir que sí, si no, no será visible desde
     fuera de ese mismo PC.
   - **El ordenador servidor tiene que estar encendido** y con
     `python app.py` corriendo para que los demás puedan entrar. Si se
     apaga o se cierra la consola, deja de estar disponible.
   - **Estado por navegador**: el presupuesto, el historial de compras
     y la lista de la compra viven en el `localStorage` de cada
     navegador, así que no se comparten entre el PC servidor y el de
     tu mujer — cada uno ve su propia lista/presupuesto aunque hablen
     con el mismo servidor. Lo que sí se comparte es la caché de
     precios (menos visitas a las webs, menos bloqueos de Akamai).
   - Si necesitas fijar la IP o el puerto a mano en vez del automático,
     hay variables de entorno: `HOST`, `PORT` y `DEBUG=1` (para volver
     al modo desarrollo con recarga automática).

## Requisito importante: todo debe ser 100% gratis

Sigue siendo posible, pero el plan inicial no sirve tal cual. Lo que lo
condiciona **no es el precio, es que Hipercor y Mercadona rechazan los
navegadores headless** (ver arriba). Hace falta poder abrir un navegador
"con pantalla", y eso descarta algunos servicios pero no todos:

| Opción gratuita | ¿Sirve? |
|---|---|
| **Azure Functions** (Consumption) | **No** para Hipercor/Mercadona: no puedes instalar Chromium + un servidor gráfico, y headless es justo lo que bloquean. Sí valdría para Alimerka, que va con `requests`. |
| **GitHub Actions** (cron) | **Sí.** Da una máquina Ubuntu completa donde se puede usar `xvfb-run` (pantalla virtual) para tener un navegador no-headless. Gratis e ilimitado en repos públicos. |
| **Azure Container Apps** | **Probablemente sí**: permite tu propia imagen Docker (con Xvfb + Chromium) y tiene una cuota mensual gratuita generosa. Es la opción "todo en Azure". |
| **Azure Static Web Apps** | **Sí**, para servir `webapp/static/`. |

**Actualización (2026-09-02) — verificado en vivo con GitHub Actions**:
se lanzó `.github/workflows/test-xvfb.yml` (`xvfb-run` + Playwright
`headless=False` de verdad, no una simulación) contra un runner real de
GitHub. Resultado, con datos reales:

- **Mercadona: funciona.** 24 opciones encontradas para "manzanas" con
  precios reales (`Manzana Golden` a 0,46 €/kg, coincide con los datos ya
  verificados más arriba). Xvfb es suficiente para pasar la detección de
  headless de Akamai en Mercadona, incluso desde una IP de datacenter.
- **Hipercor: NO funciona.** 0 opciones encontradas para "leche entera",
  con el paso tardando ~30 s (encaja con el timeout de 25 s esperando
  `window.__MOONSHINE_STATE__` en `hipercor.py`) — es el caso `None`
  ("no cargó"), no "no lo vende". Akamai sigue bloqueando a Hipercor
  concretamente desde el runner de GitHub, aunque el mismo código
  funciona perfecto desde un PC de casa. Xvfb resuelve la detección de
  headless, pero no lo que sea que Hipercor mira además (reputación de
  IP de datacenter, fingerprint TLS, u otra señal de Akamai) — pendiente
  de investigar si merece la pena perseguirlo.
- Alimerka no se ha vuelto a probar en este experimento (va con
  `requests`, sin navegador, así que no debería compartir este problema),
  pero tampoco está verificado en runner de GitHub todavía.

Esto invierte la dificultad esperada: Mercadona, que se suponía el caso
más difícil, queda resuelto gratis en la nube; Hipercor pasa a ser el
cuello de botella. Plan mientras no se resuelva Hipercor: llevarlo por
separado (modo LAN local, ver README más arriba) mientras Mercadona y
Alimerka sí pueden ir por el cron gratuito de abajo.

## Próximos pasos (pendiente de hacer)

1. ~~Comprobar Xvfb en GitHub Actions~~ **Hecho (2026-09-02)**, ver arriba.
   Sigue pendiente decidir qué hacer con Hipercor: intentar más (otro
   User-Agent/fingerprint, más reintentos, investigar si es bloqueo por
   IP) o dejarlo fuera del cron y servirlo solo en modo LAN.
2. **Scraping programado en GitHub Actions**: si el paso 1 sale bien, un
   cron (por ejemplo diario) que busque tu lista habitual en los tres
   supermercados y publique los precios como JSON (en el propio repo o
   en un blob). Así la app deja de depender de abrir navegadores.
3. **Alojar la interfaz** en Azure Static Web Apps (plan gratuito),
   leyendo ese JSON. La app pasaría a ser puramente estática, lo que
   elimina de golpe el problema del navegador y el del coste.
4. **Búsquedas nuevas bajo demanda**: para lo que no esté en el JSON
   diario, una Azure Function con Alimerka (que sí funciona sin
   navegador), o Azure Container Apps si se quiere el trío completo.
5. **GitHub**: crear el repo y subir esta carpeta. Sigue sin hacerse.

## Estructura

```
BuscaPrecios/
  src/
    supermarkets/
      base.py         # interfaz común (buscar_productos / buscar_producto)
                       # y filtrar_relevantes(): descarta el relleno que
                       # devuelven los buscadores (buscar "huevos" en
                       # Mercadona da 91 resultados con natas y batidos)
      navegador.py    # configuración del navegador visible y corte
                       # temprano cuando un supermercado no responde
      medidas.py      # pesos/volúmenes -> kg/L y precio por kilo
      mercadona.py    # Playwright visible; un navegador para toda la lista
      hipercor.py     # Playwright visible; lee window.__MOONSHINE_STATE__
      alimerka.py     # requests, el único sin navegador
    compare.py        # comparación por coste real (la usa el CLI)
    main.py           # CLI
  webapp/
    app.py            # Flask: POST /api/buscar (todas las opciones por
                       # producto) y DELETE /api/cache
    cache.py          # precios guardados 6 h en disco
    static/
      index.html, style.css           # interfaz
      app.js                          # lista con cantidades/gramos,
                                       # presupuesto e historial, coste real
                                       # por opción y algoritmo de similitud
                                       # para las alertas de "más barato"
      manifest.json, sw.js            # PWA instalable (red primero)
      icon-192.png, icon-512.png
  data/
    lista_compra_ejemplo.json
```

## Cómo funciona la alerta de "más barato en otro súper"

Cuando buscas "leche entera", todas las opciones comparten las palabras
"leche" y "entera" — esas palabras no sirven para saber si dos productos
de supermercados distintos son "el mismo". Lo que de verdad lo indica es
que compartan las palabras RARAS de esa búsqueda (la marca, la
variedad). `app.js` pesa cada palabra según en cuántas opciones de esa
búsqueda concreta aparece (igual que TF-IDF): las palabras que aparecen
en casi todas las opciones cuentan poco, las que aparecen en pocas
cuentan mucho. Además, exige que compartan al menos una palabra
"distintiva" para considerarlas parecidas — así "Garbanzos cocidos
Hacendado" y "Garbanzos cocidos Carrefour" no se confunden solo por
compartir "garbanzos" y "cocidos". Probado con casos reales en
`node app.js` (ver función `encontrarAlternativaMasBarata`), pero no es
perfecto: por eso siempre se enseña el nombre completo de cada opción.

## Nota para retomar este proyecto en otra sesión

Este README refleja el estado real y verificado del proyecto (no son
suposiciones). Verificado end-to-end el 2026-08-10 con los tres
supermercados en vivo: búsqueda completa en 14 s (los tres en paralelo),
0,4 s repitiéndola con caché, y los cálculos de gramos/paquetes
comprobados contra precios reales.

Lo único que se afirma **sin** haber podido comprobarlo es el uso de
`xvfb-run` para el despliegue (ver "Requisito importante"); está marcado
como tal. El resto de lo pendiente está en "Próximos pasos".
