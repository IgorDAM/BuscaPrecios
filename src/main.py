"""
CLI: compara los precios de tu lista de la compra entre supermercados.

Los precios de Hipercor, Alimerka y Mercadona son los mismos en toda
Oviedo (Asturias), así que el CP está fijado internamente al centro de
entrega ya verificado (33012) y no hace falta indicarlo.

La lista admite dos formatos, para no romper las que ya tuvieras:

    ["leche entera", "huevos"]

    [{"nombre": "jamon serrano", "cantidad": 300, "unidad": "g"},
     {"nombre": "leche entera",  "cantidad": 2,   "unidad": "ud"}]

Uso:
    python -m src.main --lista data/lista_compra_ejemplo.json
"""

import argparse
import json
import sys
from pathlib import Path

from .compare import LineaCompra, comparar
from .supermarkets import Mercadona, Hipercor, Alimerka

CP_OVIEDO = "33012"


def cargar_lista(ruta: str) -> list[LineaCompra]:
    data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("productos", [])

    lineas = []
    for item in data:
        if isinstance(item, str):
            lineas.append(LineaCompra(nombre=item))
        else:
            lineas.append(
                LineaCompra(
                    nombre=item["nombre"],
                    cantidad=int(item.get("cantidad", 1)),
                    unidad=item.get("unidad", "ud"),
                )
            )
    return lineas


def main():
    parser = argparse.ArgumentParser(description="Comparador de precios de supermercados (Oviedo)")
    parser.add_argument(
        "--lista", required=True, help="Ruta al JSON con la lista de la compra"
    )
    parser.add_argument(
        "--solo",
        nargs="+",
        choices=["mercadona", "hipercor", "alimerka"],
        help="Comparar solo estos supermercados (por defecto, los tres)",
    )
    args = parser.parse_args()

    lista_compra = cargar_lista(args.lista)
    if not lista_compra:
        print("La lista de la compra está vacía.", file=sys.stderr)
        sys.exit(1)

    disponibles = {
        "Mercadona": lambda: Mercadona(CP_OVIEDO),
        "Hipercor": lambda: Hipercor(CP_OVIEDO),
        "Alimerka": lambda: Alimerka(CP_OVIEDO),
    }
    if args.solo:
        elegidos = {s.lower() for s in args.solo}
        disponibles = {k: v for k, v in disponibles.items() if k.lower() in elegidos}

    supermercados = {nombre: crear() for nombre, crear in disponibles.items()}

    print(f"Comparando {len(lista_compra)} productos en Oviedo, Asturias...")
    print("(Hipercor y Mercadona abren un navegador real; puede tardar)\n")
    resultado = comparar(lista_compra, supermercados)
    print(resultado.resumen())


if __name__ == "__main__":
    main()
