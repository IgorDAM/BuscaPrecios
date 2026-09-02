"""
Lógica de comparación de precios entre supermercados (la usa el CLI).

Para cada producto de tu lista calcula dos escenarios:

  1. "Lista óptima repartida": comprar cada producto donde sea más
     barato (puede implicar visitar varios supermercados).
  2. "Mejor supermercado único": el supermercado donde, comprando TODO
     ahí, el total sea más bajo (solo un sitio, un viaje).

Y la diferencia de ahorro entre ambos escenarios.

Compara por el COSTE REAL de lo que pides, no por el precio de la
etiqueta, igual que la interfaz web: pedir 300 g de un producto que viene
en paquetes de 120 g son tres paquetes, y a granel se paga exactamente lo
pedido. Comparar por precio de etiqueta daría "el más barato" equivocado
en cuanto los formatos no coinciden.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .supermarkets.base import Producto, filtrar_relevantes


@dataclass
class LineaCompra:
    """Una línea de la lista: qué, cuánto y en qué unidad."""

    nombre: str
    cantidad: int = 1
    unidad: str = "ud"  # "ud" (unidades/paquetes) o "g" (gramos)

    def descripcion(self) -> str:
        if self.unidad == "g":
            return f"{self.nombre} ({self.cantidad} g)"
        if self.cantidad > 1:
            return f"{self.nombre} (x{self.cantidad})"
        return self.nombre


def es_al_peso(p: Producto) -> bool:
    """
    ¿El precio anunciado ES ya el del kilo (producto a granel)? Se nota en
    que coincide con el precio por kilo: carne picada a 13,00 € con 13,00
    €/kg. En un paquete no coinciden (2,29 € el paquete, 19,08 €/kg).
    """
    return (
        p.precio_unidad is not None
        and p.unidad == "kg"
        and abs(p.precio - p.precio_unidad) < 0.005
    )


def coste(p: Producto, linea: LineaCompra) -> float:
    """Lo que costaría de verdad cubrir esa línea con este producto."""
    if linea.unidad == "g":
        if p.precio_unidad is None or p.unidad != "kg":
            return p.precio  # sin peso conocido: solo cabe contar el paquete
        if es_al_peso(p):
            return round(p.precio_unidad * linea.cantidad / 1000, 2)
        # En paquete no puedes comprar media unidad: se redondea hacia arriba.
        gramos_paquete = (p.precio / p.precio_unidad) * 1000
        paquetes = max(1, math.ceil(linea.cantidad / gramos_paquete))
        return round(paquetes * p.precio, 2)
    return round(p.precio * linea.cantidad, 2)


@dataclass
class LineaComparativa:
    linea: LineaCompra
    precios: Dict[str, Optional[Producto]]  # supermercado -> Producto o None

    @property
    def producto(self) -> str:
        return self.linea.nombre

    def coste_en(self, supermercado: str) -> Optional[float]:
        p = self.precios.get(supermercado)
        return None if p is None else coste(p, self.linea)

    def mas_barato(self) -> Optional[tuple[str, Producto]]:
        candidatos = [
            (nombre, p) for nombre, p in self.precios.items() if p is not None
        ]
        if not candidatos:
            return None
        return min(candidatos, key=lambda t: coste(t[1], self.linea))


@dataclass
class ResultadoComparacion:
    lineas: List[LineaComparativa]

    # -- Escenario 1: repartida, cada producto donde sea más barato --
    def lista_optima_repartida(self):
        detalle = []
        total = 0.0
        no_encontrados = []
        for linea in self.lineas:
            mejor = linea.mas_barato()
            if mejor is None:
                no_encontrados.append(linea.linea.descripcion())
                continue
            super_nombre, producto = mejor
            importe = coste(producto, linea.linea)
            detalle.append((linea.linea.descripcion(), super_nombre, importe))
            total += importe
        return {
            "detalle": detalle,
            "total": round(total, 2),
            "no_encontrados": no_encontrados,
        }

    # -- Escenario 2: todo en un único supermercado --
    def mejor_supermercado_unico(self):
        supermercados = set()
        for linea in self.lineas:
            supermercados.update(linea.precios.keys())

        resultados = {}
        for super_nombre in supermercados:
            total = 0.0
            faltantes = []
            for linea in self.lineas:
                importe = linea.coste_en(super_nombre)
                if importe is None:
                    faltantes.append(linea.linea.descripcion())
                else:
                    total += importe
            resultados[super_nombre] = {
                "total": round(total, 2),
                "faltantes": faltantes,
            }

        # el "mejor" es el que tiene el total más bajo ENTRE los que
        # no tienen productos faltantes; si todos tienen faltantes,
        # se muestra igualmente el más barato con aviso.
        completos = {k: v for k, v in resultados.items() if not v["faltantes"]}
        base = completos if completos else resultados
        mejor_nombre = min(base, key=lambda k: base[k]["total"])

        return {
            "mejor": mejor_nombre,
            "detalle_mejor": resultados[mejor_nombre],
            "todos": resultados,
        }

    # -- Estructura completa para la API web (todo serializable a JSON) --
    def a_dict(self) -> dict:
        detalle_lineas = []
        for linea in self.lineas:
            precios = {}
            for super_nombre, p in linea.precios.items():
                precios[super_nombre] = (
                    {
                        "nombre_real": p.nombre_real,
                        "marca": p.marca,
                        "precio": p.precio,
                        "precio_unidad": p.precio_unidad,
                        "unidad": p.unidad,
                        "coste": coste(p, linea.linea),
                        "url": p.url,
                    }
                    if p is not None
                    else None
                )
            mejor = linea.mas_barato()
            detalle_lineas.append({
                "producto": linea.linea.descripcion(),
                "precios": precios,
                "mas_barato_en": mejor[0] if mejor else None,
            })

        repartida = self.lista_optima_repartida()
        unico = self.mejor_supermercado_unico()
        ahorro = round(unico["detalle_mejor"]["total"] - repartida["total"], 2)

        return {
            "lineas": detalle_lineas,
            "lista_optima": {
                "detalle": [
                    {"producto": p, "supermercado": s, "precio": importe}
                    for p, s, importe in repartida["detalle"]
                ],
                "total": repartida["total"],
                "no_encontrados": repartida["no_encontrados"],
            },
            "mejor_supermercado_unico": unico,
            "ahorro_repartiendo": ahorro,
        }

    def resumen(self) -> str:
        repartida = self.lista_optima_repartida()
        unico = self.mejor_supermercado_unico()

        ahorro = unico["detalle_mejor"]["total"] - repartida["total"]

        lineas_texto = []
        lineas_texto.append("=== Lista óptima (cada producto donde es más barato) ===")
        for linea in self.lineas:
            mejor = linea.mas_barato()
            if mejor is None:
                continue
            super_nombre, producto = mejor
            importe = coste(producto, linea.linea)
            lineas_texto.append(
                f"  {linea.linea.descripcion():28s} -> {super_nombre:10s} {importe:6.2f} EUR"
            )
            detalle = producto.nombre_real
            if producto.precio_unidad:
                detalle += f"  [{producto.precio_unidad:.2f} EUR/{producto.unidad}]"
            lineas_texto.append(f"      {detalle}")
        if repartida["no_encontrados"]:
            lineas_texto.append(
                "  (no encontrados en ningún supermercado: "
                + ", ".join(repartida["no_encontrados"])
                + ")"
            )
        lineas_texto.append(f"  TOTAL: {repartida['total']:.2f} EUR")
        lineas_texto.append("")

        lineas_texto.append("=== Mejor supermercado único ===")
        lineas_texto.append(
            f"  {unico['mejor']}: {unico['detalle_mejor']['total']:.2f} EUR"
        )
        if unico["detalle_mejor"]["faltantes"]:
            lineas_texto.append(
                "  (no disponibles ahí: "
                + ", ".join(unico["detalle_mejor"]["faltantes"])
                + ")"
            )
        lineas_texto.append("")

        lineas_texto.append("=== Comparación entre supermercados (todo en 1 sitio) ===")
        for super_nombre, info in sorted(
            unico["todos"].items(), key=lambda kv: kv[1]["total"]
        ):
            aviso = f"  (faltan {len(info['faltantes'])})" if info["faltantes"] else ""
            lineas_texto.append(f"  {super_nombre:12s} {info['total']:6.2f} EUR{aviso}")

        lineas_texto.append("")
        lineas_texto.append(
            f"Ahorro yendo a varios sitios vs. ir solo a {unico['mejor']}: "
            f"{ahorro:.2f} EUR"
        )

        return "\n".join(lineas_texto)


def comparar(
    lista_compra: List[LineaCompra],
    supermercados: dict,  # nombre -> instancia de Supermercado
) -> ResultadoComparacion:
    """
    Busca cada línea en cada supermercado y se queda con la opción más
    barata de cada uno (por coste real de lo pedido, no por etiqueta).
    """
    lineas = []
    for linea in lista_compra:
        precios = {}
        for nombre, conector in supermercados.items():
            try:
                opciones = filtrar_relevantes(
                    linea.nombre, conector.buscar_productos(linea.nombre)
                )
                precios[nombre] = (
                    min(opciones, key=lambda p: coste(p, linea)) if opciones else None
                )
            except NotImplementedError:
                precios[nombre] = None
            except Exception:
                # Un fallo puntual en un supermercado no debe tumbar
                # toda la comparación (uso personal: es aceptable que
                # algún precio falle de vez en cuando).
                precios[nombre] = None
        lineas.append(LineaComparativa(linea=linea, precios=precios))
    return ResultadoComparacion(lineas=lineas)
