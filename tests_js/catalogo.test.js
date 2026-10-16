// Pruebas de webapp/static/catalogo.js con nombres de producto reales de los
// tres súpers (verificados en vivo). Ejecutar: node --test tests_js/
const test = require("node:test");
const assert = require("node:assert/strict");
const { buscarEnCatalogo, filtrarRelevantes, normalizarBusqueda } = require("../webapp/static/catalogo.js");

const CAMPOS = ["pid", "nombre", "marca", "cat", "precio", "precio_unidad", "unidad", "url"];

function catalogo(productos, supermercado = "Hipercor") {
  return {
    supermercado, cp: "33012", generado_en: "2026-10-16T03:00:00+00:00",
    categorias: ["Lácteos > Leche", "Frescos > Huevos", "Otros"], campos: CAMPOS, productos,
  };
}
const fila = (pid, nombre, marca, precio, pu, unidad, cat = 0) => [pid, nombre, marca, cat, precio, pu, unidad, `https://x/${pid}`];

const HIPERCOR = catalogo([
  fila("1", "leche semidesnatada brik 1 l - Asturiana", "asturiana", 1.09, 1.09, "L"),
  fila("2", "leche entera brik 1 l - Puleva", "puleva", 1.2, 1.2, "L"),
  fila("3", "leche semidesnatada sin lactosa brik 1 l - Pascual", "pascual", 1.3, 1.3, "L"),
  fila("4", "huevos grandes L docena - Dagu", "dagu", 3.5, 3.5, "docena", 1),
  fila("5", "pasta fresca al huevo 250 g - Buitoni", "buitoni", 2.0, 8.0, "kg", 2),
  fila("6", "huevo sorpresa de chocolate - Kinder", "kinder", 1.5, null, "", 2),
  fila("7", "jamón cocido en dados - Serrano", "serrano", 2.0, 10.0, "kg", 2),
  fila("8", "jamón serrano reserva 120 g - Campofrío", "campofrio", 2.29, 19.08, "kg", 2),
]);

test("normaliza mayúsculas y acentos: 'Leche Semidesnatada' encuentra las leches", () => {
  const r = buscarEnCatalogo(HIPERCOR, "Leche Semidesnatada");
  assert.deepEqual(r.map((o) => o.nombre_real).sort(), [
    "leche semidesnatada brik 1 l - Asturiana",
    "leche semidesnatada sin lactosa brik 1 l - Pascual",
  ]);
});

test("'huevos' no trae la pasta al huevo (mismo criterio que filtrar_relevantes en Python)", () => {
  const r = buscarEnCatalogo(HIPERCOR, "huevos").map((o) => o.nombre_real).sort();
  assert.deepEqual(r, ["huevo sorpresa de chocolate - Kinder", "huevos grandes L docena - Dagu"]);
});

test("'jamón serrano' no trae el jamón cocido de la marca Serrano", () => {
  const r = buscarEnCatalogo(HIPERCOR, "jamon serrano");
  assert.deepEqual(r.map((o) => o.nombre_real), ["jamón serrano reserva 120 g - Campofrío"]);
});

test("formato de la opción igual al de la app", () => {
  const [o] = buscarEnCatalogo(HIPERCOR, "leche entera");
  assert.deepEqual(o, {
    supermercado: "Hipercor", nombre_real: "leche entera brik 1 l - Puleva", marca: "puleva",
    precio: 1.2, unidad: "L", precio_unidad: 1.2, url: "https://x/2", categoria: "Lácteos > Leche",
  });
});

test("sin coincidencias devuelve lista vacía; término vacío también", () => {
  assert.deepEqual(buscarEnCatalogo(HIPERCOR, "caviar beluga"), []);
  assert.deepEqual(buscarEnCatalogo(HIPERCOR, "  "), []);
  assert.deepEqual(buscarEnCatalogo(HIPERCOR, "de la"), []);
});

test("busca por marca a propósito", () => {
  const r = buscarEnCatalogo(HIPERCOR, "leche puleva");
  assert.equal(r.length, 1);
  assert.equal(r[0].marca, "puleva");
});

test("ordena por precio por unidad y respeta el límite", () => {
  const muchos = catalogo(Array.from({ length: 50 }, (_, i) =>
    fila(String(i), `arroz largo ${i}`, "m", 1 + i / 10, 2 - i / 100, "kg", 2)));
  const r = buscarEnCatalogo(muchos, "arroz", 10);
  assert.equal(r.length, 10);
  assert.ok(r.every((o, i) => i === 0 || r[i - 1].precio_unidad <= o.precio_unidad));
  assert.equal(r[0].nombre_real, "arroz largo 49");
});

test("sin precio por unidad va al final", () => {
  const c = catalogo([
    fila("1", "pan blanco", "", 1.0, null, ""),
    fila("2", "pan integral", "", 2.0, 4.0, "kg"),
  ]);
  assert.deepEqual(buscarEnCatalogo(c, "pan").map((o) => o.nombre_real), ["pan integral", "pan blanco"]);
});

test("filtrarRelevantes: si nada cuadra devuelve la lista original", () => {
  const ops = [{ nombre_real: "queso fresco", marca: "" }];
  assert.deepEqual(filtrarRelevantes("zzzz", ops), ops);
});

test("normalizarBusqueda quita acentos", () => {
  assert.equal(normalizarBusqueda("Jamón ÁÉÍ"), "jamon aei");
});
