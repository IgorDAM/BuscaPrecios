const CLAVE_LISTA = "buscaprecios_lista";
const CLAVE_PRESUPUESTO = "buscaprecios_presupuesto";
const CLAVE_HISTORIAL = "buscaprecios_historial";
const CLAVE_SELECCIONES = "buscaprecios_selecciones";

function leerEstado(clave, valorDefecto) {
  const valor = localStorage.getItem(clave);
  if (!valor) return valorDefecto;
  try {
    return JSON.parse(valor);
  } catch {
    return valorDefecto;
  }
}

function guardarEstado(clave, valor) {
  localStorage.setItem(clave, JSON.stringify(valor));
}

function normalizarTexto(texto) {
  return texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenizar(texto) {
  const base = normalizarTexto(texto);
  if (!base) return [];
  return base.split(" ");
}

function encontrarAlternativaMasBarata(productoSeleccionado, opcionesPorSupermercado) {
  const tokensReferencia = tokenizar(productoSeleccionado?.nombre || "");
  if (tokensReferencia.length === 0) return null;

  const frecuenciaGlobal = new Map();
  const candidatas = [];

  for (const opciones of Object.values(opcionesPorSupermercado || {})) {
    for (const opcion of opciones || []) {
      const tokens = Array.from(new Set(tokenizar(opcion.nombre || "")));
      for (const token of tokens) {
        frecuenciaGlobal.set(token, (frecuenciaGlobal.get(token) || 0) + 1);
      }
      candidatas.push(opcion);
    }
  }

  if (candidatas.length === 0) return null;

  const puntuacion = (opcion) => {
    const tokens = new Set(tokenizar(opcion.nombre || ""));
    let suma = 0;
    for (const token of tokensReferencia) {
      if (!tokens.has(token)) continue;
      const frecuencia = frecuenciaGlobal.get(token) || 1;
      suma += 1 / frecuencia;
    }
    return suma;
  };

  let mejor = null;
  let mejorScore = -1;
  let mejorCoste = Number.POSITIVE_INFINITY;

  for (const opcion of candidatas) {
    const score = puntuacion(opcion);
    const cantidad = Number(opcion.cantidad || 1) || 1;
    const coste = Number(opcion.precio || Number.POSITIVE_INFINITY) / cantidad;

    if (
      score > mejorScore ||
      (score === mejorScore && coste < mejorCoste)
    ) {
      mejor = opcion;
      mejorScore = score;
      mejorCoste = coste;
    }
  }

  return mejor;
}

window.BUSCAPRECIOS = {
  leerLista: () => leerEstado(CLAVE_LISTA, []),
  guardarLista: (lista) => guardarEstado(CLAVE_LISTA, lista),
  leerPresupuesto: () => leerEstado(CLAVE_PRESUPUESTO, null),
  guardarPresupuesto: (presupuesto) => guardarEstado(CLAVE_PRESUPUESTO, presupuesto),
  leerHistorial: () => leerEstado(CLAVE_HISTORIAL, []),
  guardarHistorial: (historial) => guardarEstado(CLAVE_HISTORIAL, historial),
  leerSelecciones: () => leerEstado(CLAVE_SELECCIONES, {}),
  guardarSelecciones: (selecciones) => guardarEstado(CLAVE_SELECCIONES, selecciones),
  encontrarAlternativaMasBarata,
};
