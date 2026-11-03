// Pruebas del cálculo de paquetes de webapp/static/app.js con productos
// REALES de Más y Más (2026-11-03). Ejecutar: node --test tests_js/
const test = require("node:test");
const assert = require("node:assert/strict");
const { esAlPeso, paquetesNecesarios } = require("../webapp/static/app.js");

const opcion = (precio, precio_unidad, unidad = "kg") => ({ precio, precio_unidad, unidad });

test("pedir el peso exacto del paquete es UN paquete aunque el peso deducido sea 199,999 g", () => {
  // Jamón cocido Extra 85% ALTEZA 200 g: 1,95 € y 9,75 €/kg -> 1,95/9,75 = 0,19999...
  assert.equal(paquetesNecesarios(opcion(1.95, 9.75), 200), 1);
  // Jamón cocido Extra Finíssimas CAMPOFRÍO 170 g: 2,49 € y 14,65 €/kg
  assert.equal(paquetesNecesarios(opcion(2.49, 14.65), 170), 1);
});

test("un precio por kilo redondeado no añade un paquete de más (1,5 kg)", () => {
  // 4,99 € y 3,33 €/kg (redondeado de 3,3267) -> peso deducido 1.498,5 g
  assert.equal(paquetesNecesarios(opcion(4.99, 3.33), 1500), 1);
});

test("si de verdad hace falta más, se cuentan los paquetes enteros", () => {
  assert.equal(paquetesNecesarios(opcion(1.0, 13.33), 200), 3);   // CAMPOFRÍO 75 g
  assert.equal(paquetesNecesarios(opcion(1.0, 15.38), 200), 4);   // EL POZO 65 g
  assert.equal(paquetesNecesarios(opcion(2.89, 32.11), 200), 3);  // la selva 90 g
  assert.equal(paquetesNecesarios(opcion(1.95, 9.75), 250), 2);   // ALTEZA 200 g, pidiendo 250 g
});

test("a granel el precio coincide con el del kilo; un paquete no", () => {
  assert.ok(esAlPeso(opcion(10.95, 10.95)));   // Jamon cocido Extra CAMPOFRÍO (al corte)
  assert.ok(!esAlPeso(opcion(1.95, 9.75)));    // paquete de 200 g
});
