// Escenarios repartido/único, agrupación por súper, escape de HTML y copia de
// seguridad (webapp/static/app.js). Ejecutar: node --test tests_js/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  escapar, calcularEscenarios, agruparPorSuper, validarCopiaSeguridad,
} = require("../webapp/static/app.js");

const opt = (supermercado, nombre_real, precio, extra = {}) => ({ supermercado, nombre_real, precio, ...extra });
const coste = (o) => o.precio; // sin cantidades: lo que importa aquí es el reparto

// ---------- escapar ----------

test("escapar neutraliza HTML y comillas (nombres de webs de terceros)", () => {
  assert.equal(escapar('<img src=x onerror="alert(1)">'), "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  assert.equal(escapar("Ben & Jerry's"), "Ben &amp; Jerry&#39;s");
});

test("escapar tolera null, undefined y números", () => {
  assert.equal(escapar(null), "");
  assert.equal(escapar(undefined), "");
  assert.equal(escapar(0.96), "0.96");
});

// ---------- calcularEscenarios ----------

test("repartida compra cada producto donde es más barato; el ahorro es frente al mejor súper único", () => {
  const resultados = [
    { producto: "leche", opciones: [opt("Alimerka", "Leche", 1.0), opt("Mercadona", "Leche", 0.9)] },
    { producto: "huevos", opciones: [opt("Alimerka", "Huevos", 3.0), opt("Mercadona", "Huevos", 3.4)] },
  ];
  const e = calcularEscenarios(resultados, coste);
  assert.equal(e.repartida.total, 3.9); // leche en Mercadona + huevos en Alimerka
  assert.deepEqual(e.repartida.supersUsados, ["Alimerka", "Mercadona"]);
  assert.equal(e.mejorUnico.supermercado, "Alimerka"); // 4,00 € frente a 4,30 €
  assert.equal(e.mejorUnico.total, 4.0);
  assert.equal(e.ahorro, 0.1);
});

test("un súper al que le falta un producto no puede ser el 'mejor único' aunque sea más barato", () => {
  const resultados = [
    { producto: "leche", opciones: [opt("Alimerka", "Leche", 1.0), opt("Mercadona", "Leche", 0.5)] },
    { producto: "huevos", opciones: [opt("Alimerka", "Huevos", 3.0)] }, // Mercadona no los tiene
  ];
  const e = calcularEscenarios(resultados, coste);
  assert.equal(e.mejorUnico.supermercado, "Alimerka");
  assert.deepEqual(e.unicos[1].faltan, ["huevos"]);
  assert.equal(e.ahorro, 0.5);
});

test("si ningún súper tiene toda la lista no se inventa un ahorro", () => {
  const resultados = [
    { producto: "leche", opciones: [opt("Alimerka", "Leche", 1.0)] },
    { producto: "huevos", opciones: [opt("Mercadona", "Huevos", 3.0)] },
  ];
  const e = calcularEscenarios(resultados, coste);
  assert.equal(e.ahorro, null);
  assert.equal(e.mejorUnico.faltan.length, 1);
  assert.equal(e.repartida.total, 4.0);
});

test("los productos sin ninguna opción se listan aparte y no cuentan en los totales", () => {
  const resultados = [
    { producto: "leche", opciones: [opt("Alimerka", "Leche", 1.0)] },
    { producto: "mango", opciones: [] },
  ];
  const e = calcularEscenarios(resultados, coste);
  assert.deepEqual(e.sinResultados, ["mango"]);
  assert.equal(e.repartida.total, 1.0);
  assert.equal(e.mejorUnico.faltan.length, 0); // 'mango' no obliga a ningún súper
});

test("no elige huevos de chocolate (por kilo) como 'los huevos más baratos'", () => {
  // Caso real del 2026-11-03: la familia mayoritaria es la de unidades/docena.
  const resultados = [{
    producto: "huevos",
    opciones: [
      opt("Alimerka", "Huevos M 12 ud", 2.9, { precio_unidad: 2.9, unidad: "docena" }),
      opt("Mercadona", "Huevos L docena", 3.1, { precio_unidad: 3.1, unidad: "docena" }),
      opt("Hipercor", "Huevos camperos", 3.5, { precio_unidad: 3.5, unidad: "docena" }),
      opt("Alimerka", "Huevo de chocolate Pascua", 1.0, { precio_unidad: 12.0, unidad: "kg" }),
    ],
  }];
  const e = calcularEscenarios(resultados, coste);
  assert.equal(e.repartida.lineas[0].opcion.nombre_real, "Huevos M 12 ud");
  assert.equal(e.repartida.total, 2.9);
});

test("sin resultados devuelve estructuras vacías sin romper", () => {
  const e = calcularEscenarios([], coste);
  assert.equal(e.repartida.total, 0);
  assert.equal(e.mejorUnico, null);
  assert.equal(e.ahorro, null);
});

test("los totales se redondean a céntimos (0,1 + 0,2 = 0,3)", () => {
  const resultados = [
    { producto: "a", opciones: [opt("Alimerka", "A", 0.1)] },
    { producto: "b", opciones: [opt("Alimerka", "B", 0.2)] },
  ];
  assert.equal(calcularEscenarios(resultados, coste).repartida.total, 0.3);
});

// ---------- agruparPorSuper ----------

test("agruparPorSuper junta lo elegido por tienda con su subtotal, ordenado por nombre", () => {
  const grupos = agruparPorSuper([
    { producto: "leche", opcion: opt("Mercadona", "Leche", 0.9), coste: 0.9 },
    { producto: "huevos", opcion: opt("Alimerka", "Huevos", 3.0), coste: 3.0 },
    { producto: "pan", opcion: opt("Mercadona", "Pan", 0.7), coste: 0.7 },
  ]);
  assert.deepEqual(grupos.map((g) => g.supermercado), ["Alimerka", "Mercadona"]);
  assert.equal(grupos[1].subtotal, 1.6);
  assert.deepEqual(grupos[1].lineas.map((l) => l.producto), ["leche", "pan"]);
});

// ---------- validarCopiaSeguridad ----------

const copiaBuena = () => ({
  version: 1,
  lista: [{ nombre: "leche entera", cantidad: 2, unidad: "ud" }, { nombre: "jamón", cantidad: 300, unidad: "g" }],
  presupuesto: 300,
  historial: [{ fecha: "2026-11-03", total: 69.21, ahorro: 4.5, numProductos: 25 }],
});

test("una copia válida se acepta tal cual", () => {
  const r = validarCopiaSeguridad(copiaBuena());
  assert.equal(r.ok, true);
  assert.deepEqual(r.datos.lista[1], { nombre: "jamón", cantidad: 300, unidad: "g" });
  assert.equal(r.datos.presupuesto, 300);
});

test("el presupuesto puede ser null (aún no se puso)", () => {
  const c = copiaBuena();
  c.presupuesto = null;
  assert.equal(validarCopiaSeguridad(c).ok, true);
});

test("se rechazan formas que no son una copia", () => {
  for (const malo of [null, [], "texto", 5, {}, { version: 2, lista: [], historial: [] }]) {
    assert.equal(validarCopiaSeguridad(malo).ok, false, JSON.stringify(malo));
  }
});

test("se rechazan líneas con unidad, cantidad o nombre no válidos", () => {
  const casos = [
    (c) => { c.lista[0].unidad = "kg"; },
    (c) => { c.lista[0].cantidad = -1; },
    (c) => { c.lista[0].cantidad = "2"; },
    (c) => { c.lista[0].nombre = "   "; },
    (c) => { c.lista[0].nombre = "x".repeat(101); },
  ];
  for (const rompe of casos) {
    const c = copiaBuena();
    rompe(c);
    assert.equal(validarCopiaSeguridad(c).ok, false);
  }
});

test("se rechazan compras con fecha o importes no válidos (iría luego a innerHTML)", () => {
  const casos = [
    (c) => { c.historial[0].fecha = '<script>alert(1)</script>'; },
    (c) => { c.historial[0].total = "69"; },
    (c) => { c.historial[0].ahorro = NaN; },
    (c) => { c.historial[0].numProductos = 2.5; },
  ];
  for (const rompe of casos) {
    const c = copiaBuena();
    rompe(c);
    assert.equal(validarCopiaSeguridad(c).ok, false);
  }
});

test("se rechaza un presupuesto no positivo y las copias gigantes", () => {
  const c = copiaBuena();
  c.presupuesto = 0;
  assert.equal(validarCopiaSeguridad(c).ok, false);
  const grande = copiaBuena();
  grande.lista = Array.from({ length: 501 }, (_, i) => ({ nombre: `p${i}`, cantidad: 1, unidad: "ud" }));
  assert.equal(validarCopiaSeguridad(grande).ok, false);
});

test("los campos desconocidos se descartan al importar", () => {
  const c = copiaBuena();
  c.lista[0].extra = "<img onerror=x>";
  c.historial[0].otro = 1;
  const r = validarCopiaSeguridad(c);
  assert.equal(r.ok, true);
  assert.equal("extra" in r.datos.lista[0], false);
  assert.equal("otro" in r.datos.historial[0], false);
});
