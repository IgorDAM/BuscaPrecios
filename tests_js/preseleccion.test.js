// Preselección automática: no elegir un producto de otra "familia" de
// medida (huevos de chocolate por kilo frente a huevos de verdad por
// docena/unidad). Opciones REALES de Alimerka y Más y Más (2026-11-03).
// Ejecutar: node --test tests_js/
const test = require("node:test");
const assert = require("node:assert/strict");
const { familiaMedida, filtrarFamiliaMayoritaria } = require("../webapp/static/app.js");

const op = (nombre, precio, precio_unidad, unidad) => ({ nombre_real: nombre, precio, precio_unidad, unidad });

const HUEVOS = [
  op("Huevos de chocolate SAN ISIDRO 80g", 1.0, 12.5, "kg"),
  op("Huevos KINDER Sorpresa 20g", 1.49, 74.5, "kg"),
  op("HUEVOS CAMPEROS M/L 6 UDS.", 1.79, 3.58, "docena"),
  op("Huevos 'L' GRANJA RUALMAR 6uds", 1.8, 0.3, "ud"),
  op("Huevo codorniz PITAS PITAS 18uds", 1.85, 0.1, "ud"),
  op("Huevos sin formato reconocible", 2.1, null, ""),
];

test("la docena y la unidad son la misma familia", () => {
  assert.equal(familiaMedida(op("x", 1, 3.5, "docena")), "unidades");
  assert.equal(familiaMedida(op("x", 1, 0.3, "ud")), "unidades");
  assert.equal(familiaMedida(op("x", 1, 12.5, "kg")), "peso");
  assert.equal(familiaMedida(op("x", 1, null, "")), null);
});

test("en 'huevos' fuera los de chocolate (kilo); se quedan los de verdad y los sin medida", () => {
  const nombres = filtrarFamiliaMayoritaria(HUEVOS).map((o) => o.nombre_real);
  assert.ok(!nombres.some((n) => /chocolate|KINDER/.test(n)));
  assert.equal(nombres.length, 4);
});

test("si todo es de la misma familia, no se quita nada", () => {
  const jamones = [op("Jamón 75g", 1, 13.33, "kg"), op("Jamón 200g", 1.95, 9.75, "kg")];
  assert.equal(filtrarFamiliaMayoritaria(jamones).length, 2);
});

test("empate entre familias: no se quita nada (no hay una clara)", () => {
  const mezcla = [op("a", 1, 1, "kg"), op("b", 1, 1, "L")];
  assert.equal(filtrarFamiliaMayoritaria(mezcla).length, 2);
});
