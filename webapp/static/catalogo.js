// Búsqueda sobre los catálogos completos que publica el cron semanal
// (catalogo_alimerka.json, catalogo_mercadona.json, catalogo_hipercor.json;
// formato en src/catalogo/formato.py).
//
// Se usa cuando no hay servidor detrás (Azure Static Web Apps): el móvil
// descarga el catálogo de cada súper y busca aquí mismo, sin más peticiones.
//
// Es un port a JavaScript de `filtrar_relevantes` (src/supermarkets/base.py),
// que es lo que ya decide en modo local qué resultados "tienen que ver" con
// lo buscado. Si cambias un criterio allí, cámbialo aquí (los tests de
// tests_js/catalogo.test.js comprueban los casos reales).

// Nº máximo de opciones que se devuelven por producto buscado.
const LIMITE_OPCIONES = 30;

// Minúsculas y sin acentos, para poder comparar textos (= `_normalizar`).
function normalizarBusqueda(texto) {
  return (texto || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Quita el plural para que "huevos" case con "huevo" (= `_raiz`).
function raizPalabra(palabra) {
  if (palabra.length > 3 && palabra.endsWith("es")) return palabra.slice(0, -2);
  if (palabra.length > 3 && palabra.endsWith("s")) return palabra.slice(0, -1);
  return palabra;
}

// Filtra opciones {nombre_real, marca, ...} como `filtrar_relevantes`:
// frase exacta > todas las palabras en el nombre > palabras en marca+nombre,
// exigiendo que la primera palabra buscada empiece el nombre; si nada cuadra,
// devuelve la lista original (mejor enseñar de más que nada).
function filtrarRelevantes(termino, opciones) {
  const palabras = normalizarBusqueda(termino)
    .split(/\s+/)
    .filter((p) => p.length > 2)
    .map(raizPalabra);
  if (palabras.length === 0) return opciones;

  const nombreNorm = new Map(opciones.map((o) => [o, normalizarBusqueda(o.nombre_real)]));
  const empiezaPorLoBuscado = (o) => {
    const primera = nombreNorm.get(o).split(/\s+/).filter(Boolean)[0] || "";
    return primera.includes(palabras[0]);
  };

  const frase = palabras.join(" ");
  const exactos = opciones.filter((o) => nombreNorm.get(o).includes(frase));
  const porNombre = opciones.filter((o) => palabras.every((w) => nombreNorm.get(o).includes(w)));
  const conMarca = opciones.filter((o) => {
    const t = normalizarBusqueda(`${o.marca || ""} ${o.nombre_real}`);
    return palabras.every((w) => t.includes(w));
  });

  for (const candidatos of [exactos, porNombre, conMarca]) {
    const estrictos = candidatos.filter(empiezaPorLoBuscado);
    if (estrictos.length > 0) return estrictos;
  }
  if (exactos.length) return exactos;
  if (porNombre.length) return porNombre;
  if (conMarca.length) return conMarca;
  return opciones;
}

// Fila del catálogo -> opción con el mismo formato que usa la app.
function filaAOpcion(catalogo, fila) {
  const c = {};
  catalogo.campos.forEach((campo, i) => { c[campo] = fila[i]; });
  return {
    supermercado: catalogo.supermercado,
    nombre_real: c.nombre,
    marca: c.marca || "",
    precio: c.precio,
    unidad: c.unidad || "",
    precio_unidad: c.precio_unidad == null ? null : c.precio_unidad,
    url: c.url || "",
    categoria: (catalogo.categorias || [])[c.cat] || "",
  };
}

// Busca `termino` en un catálogo y devuelve como mucho `limite` opciones,
// las de menor precio por kilo/litro primero (las que no lo tienen, al final).
// Preselección previa barata: solo se filtra con el criterio completo lo que
// contiene alguna de las palabras buscadas.
function buscarEnCatalogo(catalogo, termino, limite = LIMITE_OPCIONES) {
  const palabras = normalizarBusqueda(termino)
    .split(/\s+/)
    .filter((p) => p.length > 2)
    .map(raizPalabra);
  if (palabras.length === 0) return [];

  const iNombre = catalogo.campos.indexOf("nombre");
  const iMarca = catalogo.campos.indexOf("marca");
  const candidatas = [];
  for (const fila of catalogo.productos) {
    const texto = normalizarBusqueda(`${fila[iMarca] || ""} ${fila[iNombre]}`);
    if (palabras.every((w) => texto.includes(w))) candidatas.push(filaAOpcion(catalogo, fila));
  }
  // Si ninguna contiene TODAS las palabras, no hay nada que enseñar
  // (filtrarRelevantes devolvería la lista entera, que aquí es vacía).
  if (candidatas.length === 0) return [];

  const relevantes = filtrarRelevantes(termino, candidatas);
  relevantes.sort(
    (a, b) => (a.precio_unidad ?? Infinity) - (b.precio_unidad ?? Infinity) || a.precio - b.precio
  );
  return relevantes.slice(0, limite);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { normalizarBusqueda, raizPalabra, filtrarRelevantes, filaAOpcion, buscarEnCatalogo, LIMITE_OPCIONES };
}
