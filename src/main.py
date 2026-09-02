from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.compare import comparar_resultados
from src.supermarkets import crear_supermercados


def cargar_lista_compra(ruta_lista: Path) -> list[str]:
    datos = json.loads(ruta_lista.read_text(encoding="utf-8"))
    if isinstance(datos, list):
        return [str(item) for item in datos]
    if isinstance(datos, dict):
        if "productos" in datos and isinstance(datos["productos"], list):
            return [str(item) for item in datos["productos"]]
        if "lista" in datos and isinstance(datos["lista"], list):
            return [str(item) for item in datos["lista"]]
    raise ValueError("El archivo de lista debe contener una lista o un objeto con 'productos'.")


def ejecutar_comparador(codigo_postal: str, lista_compra: list[str], supermercados: list[str]) -> dict[str, Any]:
    conectores = crear_supermercados(codigo_postal, supermercados)
    resultados_por_supermercado: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for conector in conectores:
        resultados_por_supermercado[conector.nombre] = {}
        for producto in lista_compra:
            resultados_por_supermercado[conector.nombre][producto] = conector.buscar_productos(producto)

    comparacion = comparar_resultados(lista_compra, resultados_por_supermercado)
    return {
        "codigo_postal": codigo_postal,
        "lista_compra": lista_compra,
        "resultados": resultados_por_supermercado,
        "comparacion": comparacion,
    }


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Comparador de precios entre supermercados")
    parser.add_argument("--cp", required=True, help="Código postal")
    parser.add_argument("--lista", required=True, help="Ruta al JSON con la lista de la compra")
    parser.add_argument(
        "--supermercados",
        default="mercadona,hipercor,alimerka",
        help="Supermercados separados por coma",
    )
    return parser


def main() -> None:
    parser = construir_parser()
    args = parser.parse_args()

    lista_compra = cargar_lista_compra(Path(args.lista))
    supermercados = [s.strip() for s in args.supermercados.split(",") if s.strip()]

    salida = ejecutar_comparador(args.cp, lista_compra, supermercados)
    print(json.dumps(salida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
