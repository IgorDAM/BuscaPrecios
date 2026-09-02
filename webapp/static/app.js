// Lógica de la interfaz. Sin frameworks, JS normal.

const LS_KEY = "comparasuper_lista";
const LS_PRESUPUESTO = "comparasuper_presupuesto";
// Los precios de Hipercor, Alimerka y Mercadona son los mismos en toda
// Oviedo, así que el CP no se pide al usuario: se usa siempre el centro
// de entrega ya verificado para la ciudad.
const CP_OVIEDO = "33012";
const LS_HISTORIAL = "comparasuper_historial";
const LS_SELECCIONES = "comparasuper_selecciones";

// --- Funciones puras (sin DOM), para poder probarlas aparte con Node ---

function mesDe(fechaISO) {
  return fechaISO.slice(0, 7); // "2026-08-09" -> "2026-08"
}

function redondear2(n) {
  return Math.round(n * 100) / 100;
}

// Resumen del mes: cuánto se ha gastado (sumando cada compra registrada)
// y cuánto se ha ahorrado en total repartiendo la compra entre supermercados,
// a partir del historial completo y el mes que se quiera consultar.
function resumenMes(historial, mesActual) {
  const compras = historial.filter((h) => mesDe(h.fecha) === mesActual);
  const gastado = redondear2(compras.reduce((acc, h) => acc + h.total, 0));
  const ahorro = redondear2(compras.reduce((acc, h) => acc + h.ahorro, 0));
  return { gastado, ahorro, numCompras: compras.length, compras };
}

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function formatMesLegible(mesISO) {
  const [anio, mes] = mesISO.split("-").map(Number);
  return `${MESES[mes - 1]} de ${anio}`;
}

// --- Similitud de texto, para detectar "posiblemente el mismo producto" ---
// entre dos supermercados aunque lo describan con palabras distintas.
//
// No basta con contar palabras en común: si busco "leche entera", TODAS
// las opciones comparten "leche" y "entera", así que esas palabras no
// distinguen nada. Lo que realmente identifica que dos productos son
// "el mismo" es que compartan las palabras RARAS dentro de esa búsqueda
// (la marca, la variedad...). Por eso pesamos cada palabra según en
// cuántas de las opciones de ESTA búsqueda aparece: cuanto más rara,
// más peso. Es la misma idea que usan los buscadores (TF-IDF).
//
// No es infalible (dos marcas distintas pueden compartir alguna palabra
// suelta), por eso siempre enseñamos el nombre completo para que la
// persona lo confirme con sus propios ojos antes de cambiar de opción.

const PALABRAS_VACIAS = new Set([
  "de", "la", "el", "los", "las", "un", "una", "y", "en", "con", "para", "del",
  // palabras de envase/formato: no distinguen marca ni variedad, solo
  // el tamaño del paquete, así que no deben contar como "coincidencia".
  "brik", "botella", "bote", "lata", "pack", "garrafa", "tarro", "envase",
  "unidad", "ud", "sin", "caja",
]);

function normalizarTexto(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // quitar acentos
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\b(\d+)\s*l\b/g, "$1l")   // "1 l" y "1l" deben ser el mismo token
    .replace(/\b(\d+)\s*kg\b/g, "$1kg")
    .split(/\s+/)
    .filter((t) => t.length > 1 && !PALABRAS_VACIAS.has(t));
}

// Frecuencia de cada palabra dentro de un conjunto de nombres de
// producto (en cuántos nombres distintos aparece).
function calcularFrecuencias(nombres) {
  const freq = {};
  nombres.forEach((n) => {
    const unicos = new Set(normalizarTexto(n));
    unicos.forEach((tok) => {
      freq[tok] = (freq[tok] || 0) + 1;
    });
  });
  return freq;
}

// Similitud ponderada entre dos nombres, usando las frecuencias del
// conjunto de opciones al que pertenecen (así "leche"/"entera" cuentan
// poco, y "asturiana"/"hacendado" cuentan mucho). Además exige que
// compartan al menos una palabra "distintiva" (que no aparezca en más
// de la mitad de las opciones) - si solo comparten palabras genéricas,
// la similitud es 0 directamente.
function similitudPonderada(a, b, frecuencias, totalOpciones) {
  const ta = new Set(normalizarTexto(a));
  const tb = new Set(normalizarTexto(b));
  if (ta.size === 0 || tb.size === 0) return 0;

  const peso = (tok) => Math.log((totalOpciones + 1) / (frecuencias[tok] || 1));
  const union = new Set([...ta, ...tb]);

  let pesoInterseccion = 0;
  let pesoUnion = 0;
  let compartenPalabraDistintiva = false;

  union.forEach((tok) => {
    const p = peso(tok);
    pesoUnion += p;
    if (ta.has(tok) && tb.has(tok)) {
      pesoInterseccion += p;
      if ((frecuencias[tok] || 1) <= totalOpciones * 0.5) {
        compartenPalabraDistintiva = true;
      }
    }
  });

  if (!compartenPalabraDistintiva || pesoUnion === 0) return 0;
  return pesoInterseccion / pesoUnion;
}

const UMBRAL_SIMILITUD = 0.2; // a partir de aquí consideramos "posible mismo producto"

// Dada una opción elegida y el resto de opciones del mismo producto,
// busca si hay una opción de OTRO supermercado que (a) se parezca lo
// bastante como para ser "el mismo producto" y (b) sea más barata.
// Devuelve la mejor alternativa encontrada, o null si no hay ninguna.
function textoCompleto(opt) {
  return opt.marca ? `${opt.marca} ${opt.nombre_real}` : opt.nombre_real;
}

function encontrarAlternativaMasBarata(elegida, todasLasOpciones) {
  const nombres = todasLasOpciones.map((o) => textoCompleto(o));
  const frecuencias = calcularFrecuencias(nombres);
  const total = todasLasOpciones.length;

  let mejor = null;
  for (const opt of todasLasOpciones) {
    if (opt.supermercado === elegida.supermercado) continue;
    if (opt.precio >= elegida.precio) continue;
    const s = similitudPonderada(textoCompleto(elegida), textoCompleto(opt), frecuencias, total);
    if (s < UMBRAL_SIMILITUD) continue;
    if (!mejor || opt.precio < mejor.precio) {
      mejor = opt;
    }
  }
  return mejor;
}

// Node.js no tiene `window`/`document`; si se ejecuta este archivo con
// `node app.js` (require), exportamos las funciones puras para poder
// probarlas sin necesidad de un navegador.
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    mesDe, redondear2, resumenMes, formatMesLegible,
    normalizarTexto, calcularFrecuencias, similitudPonderada,
    textoCompleto, encontrarAlternativaMasBarata,
  };
}

// El resto de este archivo necesita un navegador (DOM). Si se cargó desde
// Node solo para los tests, paramos aquí.
if (typeof document === "undefined") {
  // no-op: entorno sin DOM (tests)
} else {

const listaEl = document.getElementById("lista-productos");
const nuevoInput = document.getElementById("nuevo-producto");
const anadirBtn = document.getElementById("anadir-btn");
const compararBtn = document.getElementById("comparar-btn");
const estadoEl = document.getElementById("estado");
const progresoEl = document.getElementById("progreso");
const ordenEl = document.getElementById("orden");
const incluirHipercorEl = document.getElementById("incluir-hipercor");
const incluirAlimerkaEl = document.getElementById("incluir-alimerka");
const incluirMercadonaEl = document.getElementById("incluir-mercadona");

const resumenSeccion = document.getElementById("resumen-seccion");
const resumenEl = document.getElementById("resumen");
const registrarBtn = document.getElementById("registrar-btn");
const masBaratoBtn = document.getElementById("mas-barato-btn");

const resultadosSeccion = document.getElementById("resultados-seccion");
const resultadosListaEl = document.getElementById("resultados-lista");
const resultadosTotalEl = document.getElementById("resultados-total");

const presupuestoInput = document.getElementById("presupuesto");
const guardarPresupuestoBtn = document.getElementById("guardar-presupuesto-btn");
const presupuestoResumenEl = document.getElementById("presupuesto-resumen");
const historialMesEl = document.getElementById("historial-mes");

// Último resultado de /api/buscar: [{ producto, opciones: [...] }, ...]
let ultimosResultados = [];

// Caché en memoria de webapp/static/precios_generados.json (el JSON que
// publica el cron de GitHub Actions para la versión sin backend, p.ej.
// desplegada en Azure Static Web Apps). false = ya se intentó y no hay.
// null = todavía no se ha intentado.
let cachePreciosEstaticos = null;

// true en cuanto se ha usado precios_generados.json al menos una vez
// (o sea, estamos en la versión sin backend). Sirve para distinguir, en
// la tarjeta de un producto sin resultados, "no está en la lista que
// revisa la nube" de "los tres supermercados dicen que no lo venden".
let modoEstaticoActivo = false;

// Nombres de producto pedidos que NO aparecen en absoluto en
// precios_generados.json (ni siquiera con 0 opciones): significa que no
// están en data/lista_compra_habitual.json, no que no se vendan.
let productosFueraDeListaCloud = new Set();

// Descarga (una sola vez por sesión) los precios que publicó el cron.
// Solo existen si la app está desplegada como sitio estático sin
// webapp/app.py detrás; en modo LAN/local nunca se llega a usar porque
// /api/buscar responde directamente.
async function cargarPreciosEstaticos() {
  if (cachePreciosEstaticos !== null) return cachePreciosEstaticos;
  try {
    const res = await fetch("precios_generados.json");
    if (!res.ok) throw new Error("no hay precios_generados.json");
    cachePreciosEstaticos = await res.json();
  } catch (e) {
    cachePreciosEstaticos = false;
  }
  return cachePreciosEstaticos;
}

// Adapta el JSON estático (que trae los tres supermercados juntos) al
// mismo formato que devuelve /api/buscar para UN supermercado, filtrando
// por los productos pedidos. Si pides un producto que no está en la
// lista habitual del cron, simplemente no aparecerá (0 opciones), igual
// que si ese súper no lo vendiera.
function filtrarPreciosEstaticos(datos, nombreSuper, productosPedidos) {
  const avisoSuper = (datos.avisos || []).find((a) => a.supermercado === nombreSuper);
  const resultados = productosPedidos.map((nombreProducto) => {
    const item = (datos.resultados || []).find((r) => r.producto === nombreProducto);
    if (!item) {
      productosFueraDeListaCloud.add(nombreProducto);
    }
    const opciones = item
      ? item.opciones.filter((o) => o.supermercado === nombreSuper)
      : [];
    return { producto: nombreProducto, opciones };
  });
  return {
    resultados,
    avisos: avisoSuper ? [avisoSuper] : [],
    desde_cache: true,
    generado_en: datos.generado_en,
  };
}

function formatearFecha(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    return iso;
  }
}

// Cómo se ordenan las opciones dentro de cada producto: por lo que
// costaría lo pedido (false) o por precio por kilo/litro (true).
let ordenPorMedida = false;

// Cada línea de la lista es { nombre, cantidad, unidad }, donde unidad es
// "ud" (paquetes/unidades) o "g" (gramos, para lo que se vende al peso:
// jamón, queso, fruta...). Las listas guardadas antes de existir estos
// campos se migran solas al leerlas.
function cargarLista() {
  try {
    const datos = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
    return datos.map((item) => {
      if (typeof item === "string") return { nombre: item, cantidad: 1, unidad: "ud" };
      return { unidad: "ud", cantidad: 1, ...item };
    });
  } catch (e) {
    return [];
  }
}

function guardarLista(lista) {
  localStorage.setItem(LS_KEY, JSON.stringify(lista));
}

// Cuánto se sube o baja con cada toque: de uno en uno en unidades, de 50
// en 50 en gramos (pedir 251 g de jamón no tiene sentido práctico).
function pasoDe(unidad) {
  return unidad === "g" ? 50 : 1;
}

function lineaDe(nombreProducto) {
  return (
    cargarLista().find((p) => p.nombre === nombreProducto) || {
      nombre: nombreProducto,
      cantidad: 1,
      unidad: "ud",
    }
  );
}

function formatCantidad(linea) {
  return linea.unidad === "g" ? `${linea.cantidad} g` : `x${linea.cantidad}`;
}

// Fija la cantidad a lo que se haya escrito. Si no es un número válido se
// deja como estaba (y el re-render devuelve el valor anterior al campo).
function fijarCantidad(idx, texto) {
  const lista = cargarLista();
  if (!lista[idx]) return;
  const valor = parseInt(String(texto).replace(/[^0-9]/g, ""), 10);
  if (!isNaN(valor) && valor > 0) {
    lista[idx].cantidad = valor;
    guardarLista(lista);
    renderTodo();
  }
  renderLista();
}

function cambiarCantidad(idx, delta) {
  const lista = cargarLista();
  if (!lista[idx]) return;
  const paso = pasoDe(lista[idx].unidad) * delta;
  lista[idx].cantidad = Math.max(pasoDe(lista[idx].unidad), lista[idx].cantidad + paso);
  guardarLista(lista);
  renderTodo();
  renderLista();
}

// Cambiar entre "por unidades" y "por gramos". Al cambiar, la cantidad
// anterior no sirve (2 unidades no son 2 gramos), así que se pone un
// valor de partida razonable para la nueva unidad.
function cambiarUnidad(idx) {
  const lista = cargarLista();
  if (!lista[idx]) return;
  const esGramos = lista[idx].unidad === "g";
  lista[idx].unidad = esGramos ? "ud" : "g";
  lista[idx].cantidad = esGramos ? 1 : 200;
  guardarLista(lista);
  renderTodo();
  renderLista();
}

// ¿Esta opción se vende a granel (el precio que se ve YA es el del kilo)
// o es un paquete cerrado? Si el precio coincide con el precio por kilo,
// es que lo que se anuncia es el kilo: carne picada a 13,00 € con 13,00
// €/kg. En un paquete no coinciden: 2,29 € el paquete, 19,08 €/kg.
function esAlPeso(opt) {
  return (
    opt.precio_unidad && opt.unidad === "kg" && Math.abs(opt.precio - opt.precio_unidad) < 0.005
  );
}

// Peso del paquete en gramos, deducido del precio y el precio por kilo.
function pesoPaqueteEnGramos(opt) {
  if (!opt.precio_unidad || opt.unidad !== "kg" || opt.precio_unidad <= 0) return null;
  return (opt.precio / opt.precio_unidad) * 1000;
}

// Cuántos paquetes hacen falta para cubrir los gramos pedidos: no se
// puede comprar medio tarro, así que se redondea hacia arriba.
function paquetesNecesarios(opt, gramos) {
  const peso = pesoPaqueteEnGramos(opt);
  if (!peso) return 1;
  return Math.max(1, Math.ceil(gramos / peso));
}

// Lo que cuesta de verdad una opción según lo que se pidió de ella.
//
// Hay que distinguir dos casos, porque cobrar igual en ambos da precios
// falsos: a granel (jamón cortado al momento, carne picada al peso) sí se
// paga exactamente lo que pides, pero de un tarro de 390 g no puedes
// comprar 250 g: te llevas el tarro entero. Antes se prorrateaba siempre,
// y 250 g de un tarro de 0,59 € salían por 0,38 €, un precio que no
// existe en la caja del supermercado.
function costeDe(opt, nombreProducto) {
  const linea = lineaDe(nombreProducto);

  if (linea.unidad === "g") {
    if (!(opt.precio_unidad && opt.unidad === "kg")) {
      return opt.precio; // no sabemos el peso: solo cabe contar el paquete
    }
    if (esAlPeso(opt)) {
      return redondear2((opt.precio_unidad * linea.cantidad) / 1000);
    }
    return redondear2(paquetesNecesarios(opt, linea.cantidad) * opt.precio);
  }

  return redondear2(opt.precio * linea.cantidad);
}

// ¿Se pidió en gramos pero esa opción no permite calcular el precio al peso?
function sinPrecioAlPeso(opt, nombreProducto) {
  return lineaDe(nombreProducto).unidad === "g" && !(opt.precio_unidad && opt.unidad === "kg");
}

function renderLista() {
  const lista = cargarLista();
  listaEl.innerHTML = "";
  lista.forEach((item, idx) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = item.nombre;
    span.className = "producto-lista-nombre";

    const cantidadEl = document.createElement("div");
    cantidadEl.className = "cantidad-control";
    // La cantidad es un campo escribible: poner 750 g a base de tocar "+"
    // serían quince toques.
    cantidadEl.innerHTML = `
      <button type="button" class="btn-cantidad" data-accion="restar">−</button>
      <input type="text" class="cantidad-valor" inputmode="numeric" value="${item.cantidad}"
             aria-label="Cantidad de ${item.nombre}" />
      <button type="button" class="btn-cantidad" data-accion="sumar">+</button>
      <button type="button" class="btn-unidad" data-accion="unidad"
              title="Cambiar entre unidades y gramos">${item.unidad === "g" ? "g" : "ud"}</button>
    `;
    cantidadEl.querySelector('[data-accion="restar"]').onclick = () => cambiarCantidad(idx, -1);
    cantidadEl.querySelector('[data-accion="sumar"]').onclick = () => cambiarCantidad(idx, 1);
    cantidadEl.querySelector('[data-accion="unidad"]').onclick = () => cambiarUnidad(idx);

    const inputCantidad = cantidadEl.querySelector("input");
    const aplicar = () => fijarCantidad(idx, inputCantidad.value);
    inputCantidad.addEventListener("change", aplicar);
    inputCantidad.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        inputCantidad.blur();
      }
    });

    const btn = document.createElement("button");
    btn.textContent = "✕";
    btn.className = "btn-quitar";
    btn.onclick = () => {
      const actual = cargarLista();
      actual.splice(idx, 1);
      guardarLista(actual);
      renderLista();
    };
    li.appendChild(span);
    li.appendChild(cantidadEl);
    li.appendChild(btn);
    listaEl.appendChild(li);
  });
}

function anadirProducto() {
  const valor = nuevoInput.value.trim();
  if (!valor) return;
  const lista = cargarLista();
  lista.push({ nombre: valor, cantidad: 1 });
  guardarLista(lista);
  nuevoInput.value = "";
  renderLista();
}

anadirBtn.addEventListener("click", anadirProducto);
nuevoInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    anadirProducto();
  }
});

function euros(valor) {
  return valor.toFixed(2).replace(".", ",") + " €";
}

// --- Selección de producto elegido por cada línea de la lista ---
// Guardamos la opción completa elegida (no solo un índice), para que no
// se desajuste si la próxima búsqueda devuelve las opciones en otro orden.

function cargarSelecciones() {
  try {
    return JSON.parse(localStorage.getItem(LS_SELECCIONES) || "{}");
  } catch (e) {
    return {};
  }
}

function guardarSelecciones(selecciones) {
  localStorage.setItem(LS_SELECCIONES, JSON.stringify(selecciones));
}

function claveOpcion(opt) {
  return `${opt.supermercado}|${opt.nombre_real}`;
}

// --- Presupuesto mensual e historial de compras registradas ---

function cargarPresupuesto() {
  const valor = parseFloat(localStorage.getItem(LS_PRESUPUESTO));
  return isNaN(valor) ? null : valor;
}

function guardarPresupuesto(valor) {
  localStorage.setItem(LS_PRESUPUESTO, String(valor));
}

function cargarHistorial() {
  try {
    return JSON.parse(localStorage.getItem(LS_HISTORIAL) || "[]");
  } catch (e) {
    return [];
  }
}

function guardarHistorial(historial) {
  localStorage.setItem(LS_HISTORIAL, JSON.stringify(historial));
}

function renderPresupuesto() {
  const presupuesto = cargarPresupuesto();
  presupuestoInput.value = presupuesto !== null ? presupuesto : "";

  const hoyISO = new Date().toISOString().slice(0, 10);
  const mesActual = mesDe(hoyISO);
  const historial = cargarHistorial();
  const { gastado, ahorro, numCompras, compras } = resumenMes(historial, mesActual);

  if (presupuesto === null) {
    presupuestoResumenEl.innerHTML = `
      <div class="presupuesto-linea">
        <span>Aún no has puesto un presupuesto mensual.</span>
      </div>
    `;
  } else {
    const restante = redondear2(presupuesto - gastado);
    const porcentaje = Math.min(100, Math.round((gastado / presupuesto) * 100));
    const excedido = gastado > presupuesto;

    presupuestoResumenEl.innerHTML = `
      <div class="presupuesto-linea">
        <span>${formatMesLegible(mesActual)}</span>
        <span class="valor">${euros(gastado)} / ${euros(presupuesto)}</span>
      </div>
      <div class="barra-progreso">
        <div class="barra-progreso-relleno ${excedido ? "exceso" : ""}" style="width:${porcentaje}%;"></div>
      </div>
      <div class="presupuesto-linea">
        <span>${excedido ? "Te has pasado del presupuesto en" : "Te queda este mes"}</span>
        <span class="valor">${euros(Math.abs(restante))}</span>
      </div>
      <div class="presupuesto-linea">
        <span>Ahorrado repartiendo la compra (este mes)</span>
        <span class="valor">${euros(ahorro)}</span>
      </div>
    `;
  }

  if (numCompras === 0) {
    historialMesEl.innerHTML = "";
  } else {
    // Cada compra se puede borrar: si registras una sin querer, el gasto
    // se quedaba en el mes para siempre. Se identifica por su posición en
    // el historial completo, no por la del listado del mes. Importante:
    // hay que buscarla en el MISMO array del que salió `compras`; con una
    // lectura nueva de localStorage los objetos son distintos y indexOf
    // devolvería -1.
    const items = compras
      .slice()
      .reverse()
      .map((c) => {
        const idx = historial.indexOf(c);
        return `
        <div class="historial-item">
          <span>${c.fecha} · ${c.numProductos} productos</span>
          <span>
            ${euros(c.total)} (ahorro ${euros(c.ahorro)})
            <button type="button" class="btn-borrar-compra" data-idx="${idx}"
                    title="Borrar esta compra">✕</button>
          </span>
        </div>`;
      })
      .join("");
    historialMesEl.innerHTML = `
      <details>
        <summary>${numCompras} compra(s) registradas este mes</summary>
        ${items}
      </details>
    `;
    historialMesEl.querySelectorAll(".btn-borrar-compra").forEach((btn) => {
      btn.onclick = () => borrarCompra(parseInt(btn.dataset.idx, 10));
    });
  }
}

function borrarCompra(idx) {
  const historial = cargarHistorial();
  if (idx < 0 || idx >= historial.length) return;
  const c = historial[idx];
  if (!confirm(`¿Borrar la compra del ${c.fecha} (${euros(c.total)})?`)) return;
  historial.splice(idx, 1);
  guardarHistorial(historial);
  renderPresupuesto();
}

guardarPresupuestoBtn.addEventListener("click", () => {
  const valor = parseFloat(presupuestoInput.value.replace(",", "."));
  if (isNaN(valor) || valor <= 0) {
    alert("Escribe un presupuesto válido (por ejemplo 300).");
    return;
  }
  guardarPresupuesto(valor);
  renderPresupuesto();
});

// --- Buscar precios (todas las opciones por producto) ---

// Estado de cada supermercado durante la búsqueda, para poder enseñar
// por dónde va en vez de un "Buscando..." mudo de 40 segundos.
let progresoSupers = {};

function renderProgreso() {
  const entradas = Object.entries(progresoSupers);
  if (entradas.length === 0) {
    progresoEl.innerHTML = "";
    return;
  }
  progresoEl.innerHTML = entradas
    .map(([nombre, info]) => {
      const icono = { buscando: "⏳", ok: "✅", vacio: "∅", error: "⚠️" }[info.estado];
      return `<div class="progreso-super ${info.estado}">
        <span>${icono} ${nombre}</span>
        <span class="progreso-detalle">${info.detalle}</span>
      </div>`;
    })
    .join("");
}

// Mezcla las opciones de un supermercado en los resultados que ya se
// están enseñando, para que la lista crezca según van respondiendo.
function fusionarResultados(resultadosSuper) {
  resultadosSuper.forEach((nuevo) => {
    const existente = ultimosResultados.find((r) => r.producto === nuevo.producto);
    if (existente) {
      existente.opciones = existente.opciones.concat(nuevo.opciones);
    } else {
      ultimosResultados.push({ producto: nuevo.producto, opciones: nuevo.opciones.slice() });
    }
  });
}

// Pide UN supermercado. Se lanzan los tres a la vez (el servidor los
// atiende en hilos distintos), así el total tarda lo que el más lento en
// vez de la suma de los tres, y cada uno aparece en cuanto contesta.
async function buscarEnSuper(nombre, flags, productos) {
  progresoSupers[nombre] = { estado: "buscando", detalle: "buscando..." };
  renderProgreso();

  const comienzo = Date.now();
  try {
    let data;
    let modoEstatico = false;
    try {
      const res = await fetch("/api/buscar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cp: CP_OVIEDO, productos, ...flags }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || "error del servidor");
      }
      data = await res.json();
    } catch (errorBackend) {
      // No hay servidor Flask detrás (p.ej. desplegado como sitio
      // estático en Azure Static Web Apps, sin webapp/app.py): se usan
      // los precios que publicó el último cron de GitHub Actions en vez
      // de buscar en directo. Solo cubre la lista habitual definida en
      // data/lista_compra_habitual.json — un producto fuera de esa lista
      // simplemente no tendrá opciones aquí.
      const estaticos = await cargarPreciosEstaticos();
      if (!estaticos) throw errorBackend;
      data = filtrarPreciosEstaticos(estaticos, nombre, productos);
      modoEstatico = true;
      modoEstaticoActivo = true;
    }

    const segundos = Math.round((Date.now() - comienzo) / 1000);
    const total = (data.resultados || []).reduce((n, r) => n + r.opciones.length, 0);
    const aviso = (data.avisos || [])[0];

    if (aviso) {
      progresoSupers[nombre] = { estado: "error", detalle: aviso.motivo };
    } else {
      const etiquetaModo = modoEstatico
        ? ` · nube, actualizado ${formatearFecha(data.generado_en)}`
        : "";
      progresoSupers[nombre] = {
        estado: total > 0 ? "ok" : "vacio",
        detalle: `${total} opciones · ${segundos}s${data.desde_cache && !modoEstatico ? " (guardado)" : ""}${etiquetaModo}`,
      };
    }

    fusionarResultados(data.resultados || []);
    preseleccionarBaratos(ultimosResultados);
    renderTodo();
  } catch (e) {
    progresoSupers[nombre] = { estado: "error", detalle: e.message };
  }
  renderProgreso();
}

async function buscarPrecios() {
  const lista = cargarLista();

  if (lista.length === 0) {
    estadoEl.textContent = "Añade al menos un producto a la lista.";
    return;
  }

  const activos = [];
  if (incluirHipercorEl.checked)
    activos.push(["Hipercor", { incluir_hipercor: true, incluir_alimerka: false, incluir_mercadona: false }]);
  if (incluirAlimerkaEl.checked)
    activos.push(["Alimerka", { incluir_hipercor: false, incluir_alimerka: true, incluir_mercadona: false }]);
  if (incluirMercadonaEl.checked)
    activos.push(["Mercadona", { incluir_hipercor: false, incluir_alimerka: false, incluir_mercadona: true }]);

  if (activos.length === 0) {
    estadoEl.textContent = "Marca al menos un supermercado para comparar.";
    return;
  }

  compararBtn.disabled = true;
  estadoEl.textContent = "";
  ultimosResultados = [];
  progresoSupers = {};
  resumenSeccion.style.display = "none";
  resultadosSeccion.style.display = "none";

  const productos = lista.map((p) => p.nombre);

  try {
    await Promise.all(activos.map(([nombre, flags]) => buscarEnSuper(nombre, flags, productos)));
    if (ultimosResultados.length === 0) {
      estadoEl.innerHTML = `<div class="error">Ningún supermercado devolvió resultados.</div>`;
    }
  } catch (e) {
    estadoEl.innerHTML = `<div class="error">No se pudo conectar con el servidor local. ¿Está corriendo "python app.py"?</div>`;
  } finally {
    compararBtn.disabled = false;
  }
}

// Si un producto no tiene todavía una selección guardada (o la que
// tenía ya no aparece en los resultados nuevos), preseleccionamos la
// opción más barata automáticamente. El usuario puede cambiarla luego.
// Ordena las opciones por lo que REALMENTE costaría lo que has pedido,
// no por el precio de la etiqueta. En gramos no es lo mismo: para 300 g
// de jamón, un paquete de 500 g a 5,00 € sale más barato que tres de
// 120 g a 2,29 € (6,87 €), aunque su etiqueta sea más cara.
function opcionesOrdenadas(item) {
  const copia = item.opciones.slice();
  if (ordenPorMedida) {
    // Por €/kg: las que no lo publican van al final.
    copia.sort((a, b) => (a.precio_unidad || Infinity) - (b.precio_unidad || Infinity));
  } else {
    copia.sort((a, b) => costeDe(a, item.producto) - costeDe(b, item.producto));
  }
  return copia;
}

function opcionMasBarata(item) {
  if (item.opciones.length === 0) return null;
  return item.opciones.reduce((mejor, o) =>
    costeDe(o, item.producto) < costeDe(mejor, item.producto) ? o : mejor
  );
}

function preseleccionarBaratos(resultados) {
  const selecciones = cargarSelecciones();
  resultados.forEach((item) => {
    if (item.opciones.length === 0) return;
    const claveActual = selecciones[item.producto]
      ? claveOpcion(selecciones[item.producto])
      : null;
    const sigueExistiendo =
      claveActual && item.opciones.some((o) => claveOpcion(o) === claveActual);
    if (!sigueExistiendo) {
      selecciones[item.producto] = opcionMasBarata(item);
    }
  });
  guardarSelecciones(selecciones);
}

function elegirLoMasBaratoEnTodo() {
  const selecciones = cargarSelecciones();
  ultimosResultados.forEach((item) => {
    const mejor = opcionMasBarata(item);
    if (mejor) selecciones[item.producto] = mejor;
  });
  guardarSelecciones(selecciones);
  renderTodo();
}

masBaratoBtn.addEventListener("click", elegirLoMasBaratoEnTodo);

ordenEl.addEventListener("change", () => {
  ordenPorMedida = ordenEl.value === "medida";
  renderResultados();
});

function renderTodo() {
  renderResumenSeleccion();
  renderResultados();
}

// Total de lo elegido (precio x cantidad de cada producto) y cuántos
// productos se han quedado sin opción. Lo usan tanto el resumen de arriba
// como el total del final de "Productos encontrados".
function calcularTotalSeleccion() {
  const selecciones = cargarSelecciones();
  let total = 0;
  let elegidos = 0;
  let sinElegir = 0;
  ultimosResultados.forEach((item) => {
    const sel = selecciones[item.producto];
    if (sel) {
      total += costeDe(sel, item.producto);
      elegidos++;
    } else {
      sinElegir++;
    }
  });
  return { total: redondear2(total), elegidos, sinElegir };
}

function renderResumenSeleccion() {
  if (ultimosResultados.length === 0) {
    resumenSeccion.style.display = "none";
    return;
  }
  const { total, sinElegir } = calcularTotalSeleccion();

  resumenEl.innerHTML = `
    <div class="resumen-card">
      <span>Total de tu compra (según lo elegido)</span>
      <span class="valor">${euros(redondear2(total))}</span>
    </div>
    ${
      sinElegir > 0
        ? `<div class="error">${sinElegir} producto(s) sin resultados encontrados</div>`
        : ""
    }
  `;
  resumenSeccion.style.display = "block";
}

function renderResultados() {
  if (ultimosResultados.length === 0) {
    resultadosSeccion.style.display = "none";
    return;
  }
  const selecciones = cargarSelecciones();

  resultadosListaEl.innerHTML = "";
  ultimosResultados.forEach((item) => {
    resultadosListaEl.appendChild(crearProductoCard(item, selecciones[item.producto]));
  });

  const { total, elegidos, sinElegir } = calcularTotalSeleccion();
  resultadosTotalEl.innerHTML = `
    <div class="total-final">
      <div class="total-final-linea">
        <span>TOTAL de lo elegido</span>
        <span class="total-final-valor">${euros(total)}</span>
      </div>
      <div class="total-final-detalle">
        ${elegidos} producto(s) elegidos${sinElegir > 0 ? ` · ${sinElegir} sin elegir` : ""}
      </div>
    </div>
  `;

  resultadosSeccion.style.display = "block";
}

function crearProductoCard(item, seleccion) {
  const card = document.createElement("div");
  card.className = "producto-card";

  const header = document.createElement("div");
  header.className = "producto-card-header";

  if (item.opciones.length === 0) {
    // En la versión sin backend (nube), "sin opciones" casi siempre
    // significa que el producto no está en la lista fija que revisa el
    // cron, no que los supermercados no lo tengan — son cosas muy
    // distintas y conviene no confundirlas (ver README, "Versión en la
    // nube").
    const mensaje =
      modoEstaticoActivo && productosFueraDeListaCloud.has(item.producto)
        ? "No está en la lista de productos de la nube (búsqueda libre solo en modo LAN)"
        : "No se encontró en ningún supermercado";
    header.innerHTML = `
      <div class="producto-card-info">
        <span class="producto-nombre">${item.producto}</span>
        <span class="producto-sin-resultados">${mensaje}</span>
      </div>
    `;
    card.appendChild(header);
    return card;
  }

  const linea = lineaDe(item.producto);
  // El rango se calcula sobre el coste real de lo pedido, igual que el
  // orden y la etiqueta de "más barato": si no, no cuadraría con nada.
  const costes = item.opciones.map((o) => costeDe(o, item.producto));
  const min = Math.min(...costes);
  const max = Math.max(...costes);
  const rangoTexto = min === max ? euros(min) : `${euros(min)} – ${euros(max)}`;

  let seleccionTexto = "Elegir";
  if (seleccion) {
    const coste = costeDe(seleccion, item.producto);
    if (linea.unidad === "g") {
      // Se enseña de dónde sale el importe, que no es lo mismo comprando
      // a granel (se paga lo que pides) que en paquete (paquetes enteros).
      if (sinPrecioAlPeso(seleccion, item.producto)) {
        seleccionTexto = `${euros(seleccion.precio)} (paquete, peso desconocido)`;
      } else if (esAlPeso(seleccion)) {
        seleccionTexto = `${euros(seleccion.precio_unidad)}/kg × ${linea.cantidad} g = ${euros(coste)}`;
      } else {
        const n = paquetesNecesarios(seleccion, linea.cantidad);
        const peso = Math.round(pesoPaqueteEnGramos(seleccion));
        seleccionTexto = `${n} × ${euros(seleccion.precio)} (${peso} g) = ${euros(coste)}`;
      }
    } else {
      seleccionTexto =
        linea.cantidad > 1
          ? `${euros(seleccion.precio)} × ${linea.cantidad} = ${euros(coste)}`
          : euros(seleccion.precio);
    }
    seleccionTexto += " · " + seleccion.supermercado;
  }

  // Debajo del nombre buscado se enseña QUÉ opción concreta está elegida
  // (marca y nombre real), no solo su precio: si no, no hay forma de
  // saber qué llevas sin desplegar la tarjeta.
  const subtitulo = seleccion
    ? `<span class="producto-elegido">✓ ${seleccion.marca ? seleccion.marca + " " : ""}${seleccion.nombre_real}</span>`
    : `<span class="producto-rango">${item.opciones.length} opciones · ${rangoTexto}</span>`;

  header.innerHTML = `
    <div class="producto-card-info">
      <span class="producto-nombre">${item.producto}${
        linea.unidad === "g" || linea.cantidad > 1
          ? ` <span class="producto-cantidad">(${formatCantidad(linea)})</span>`
          : ""
      }</span>
      ${subtitulo}
    </div>
    <span class="producto-seleccion">${seleccionTexto}</span>
    <span class="flecha">▾</span>
  `;
  header.addEventListener("click", () => {
    card.classList.toggle("abierta");
  });
  card.appendChild(header);

  // Alerta: ¿lo elegido tiene una alternativa parecida y más barata?
  if (seleccion) {
    const alternativa = encontrarAlternativaMasBarata(seleccion, item.opciones);
    if (alternativa) {
      const alerta = document.createElement("div");
      alerta.className = "producto-card-alerta";
      const diferencia = redondear2(seleccion.precio - alternativa.precio);
      alerta.innerHTML = `
        <span>
          ⚠️ Podría ser el mismo producto ${euros(diferencia)} más barato en
          <strong>${alternativa.supermercado}</strong>: "${alternativa.nombre_real}" (${euros(alternativa.precio)})
        </span>
        <button type="button">Usar este</button>
      `;
      alerta.querySelector("button").addEventListener("click", (e) => {
        e.stopPropagation();
        elegirOpcion(item.producto, alternativa);
      });
      card.appendChild(alerta);
    }
  }

  // El paquete más barato no siempre sale mejor al peso: 90 g a 2,30 €
  // es más caro por kilo que 120 g a 2,29 €. Se marcan las dos cosas.
  const porMedida = item.opciones.filter((o) => o.precio_unidad);
  const mejorPorMedida =
    porMedida.length > 1 ? Math.min(...porMedida.map((o) => o.precio_unidad)) : null;

  const opcionesEl = document.createElement("div");
  opcionesEl.className = "producto-card-opciones";
  opcionesOrdenadas(item).forEach((opt) => {
    const fila = document.createElement("div");
    const esElegida = seleccion && claveOpcion(seleccion) === claveOpcion(opt);
    const coste = costeDe(opt, item.producto);
    const esMasBarata = coste === min;
    const esMejorMedida = mejorPorMedida !== null && opt.precio_unidad === mejorPorMedida;
    fila.className = "opcion-fila" + (esElegida ? " elegida" : "");
    // El precio por kilo/litro es lo que permite comparar de verdad
    // cuando los formatos no coinciden (120 g de jamón frente a 90 g).
    const porMedida = opt.precio_unidad
      ? `<span class="opcion-medida">${euros(opt.precio_unidad)}/${opt.unidad}</span>`
      : "";
    // Cuando se pide en gramos, el precio de la etiqueta no es lo que
    // pagas: se enseña el coste real y debajo, pequeño, el del paquete.
    const costeDistinto = Math.abs(coste - opt.precio) > 0.005;

    fila.innerHTML = `
      <span class="opcion-super">${opt.supermercado}</span>
      <span class="opcion-nombre">
        ${opt.marca ? `<span class="opcion-marca">${opt.marca}</span> ` : ""}${opt.nombre_real}
      </span>
      ${esMasBarata ? '<span class="badge-barato">Más barato</span>' : ""}
      ${esMejorMedida && !esMasBarata ? `<span class="badge-medida">Mejor €/${opt.unidad}</span>` : ""}
      <span class="opcion-precios">
        <span class="opcion-precio">${euros(coste)}</span>
        ${costeDistinto ? `<span class="opcion-medida">${euros(opt.precio)}/paq.</span>` : ""}
        ${porMedida}
      </span>
    `;
    fila.addEventListener("click", () => elegirOpcion(item.producto, opt));
    opcionesEl.appendChild(fila);
  });
  card.appendChild(opcionesEl);

  return card;
}

function elegirOpcion(producto, opcion) {
  const selecciones = cargarSelecciones();
  selecciones[producto] = opcion;
  guardarSelecciones(selecciones);
  renderTodo();
}

function registrarCompra() {
  if (ultimosResultados.length === 0) return;
  const { total } = calcularTotalSeleccion();

  // El "ahorro" de esta compra: la diferencia entre lo que pagarías
  // comprando cada cosa en el supermercado donde salió más cara, y lo
  // que realmente vas a pagar con tu selección.
  let totalSiTodoCaro = 0;
  ultimosResultados.forEach((item) => {
    if (item.opciones.length === 0) return;
    const costes = item.opciones.map((o) => costeDe(o, item.producto));
    totalSiTodoCaro += Math.max(...costes);
  });
  const ahorro = redondear2(totalSiTodoCaro - total);

  const historial = cargarHistorial();
  historial.push({
    fecha: new Date().toISOString().slice(0, 10),
    total: redondear2(total),
    ahorro,
    numProductos: ultimosResultados.length,
  });
  guardarHistorial(historial);

  // Empezamos una lista nueva para la próxima compra.
  guardarLista([]);
  localStorage.removeItem(LS_SELECCIONES);
  renderLista();
  ultimosResultados = [];
  resumenSeccion.style.display = "none";
  resultadosSeccion.style.display = "none";
  estadoEl.textContent = "Compra registrada. ¡A por la siguiente lista!";

  renderPresupuesto();
}

registrarBtn.addEventListener("click", registrarCompra);
compararBtn.addEventListener("click", buscarPrecios);

renderLista();
renderPresupuesto();

// --- Instalación como PWA ---
let promptDiferido = null;
const instalarBtn = document.getElementById("instalar-btn");

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  promptDiferido = e;
  instalarBtn.style.display = "inline-block";
});

instalarBtn.addEventListener("click", async () => {
  if (!promptDiferido) return;
  promptDiferido.prompt();
  await promptDiferido.userChoice;
  promptDiferido = null;
  instalarBtn.style.display = "none";
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

} // fin del bloque "typeof document !== 'undefined'"
