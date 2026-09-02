from __future__ import annotations

from typing import Any

from .base import ProductoEncontrado, Supermercado


class Alimerka(Supermercado):
    _catalogo_simulado: dict[str, list[tuple[str, float, float, str]]] = {
        "leche": [
            ("Leche entera Alimerka 1L", 1.08, 1.0, "l"),
            ("Leche semidesnatada Alimerka 1L", 1.05, 1.0, "l"),
        ],
        "arroz": [("Arroz redondo Alimerka 1kg", 1.69, 1.0, "kg")],
        "pan": [("Pan de molde Alimerka 820g", 1.75, 0.82, "kg")],
    }

    @property
    def nombre(self) -> str:
        return "alimerka"

    def buscar_productos(self, nombre_producto: str) -> list[dict[str, Any]]:
        clave = nombre_producto.strip().lower()
        resultados: list[dict[str, Any]] = []
        for termino, opciones in self._catalogo_simulado.items():
            if termino in clave or clave in termino:
                for nombre, precio, cantidad, unidad in opciones:
                    resultados.append(
                        ProductoEncontrado(nombre, precio, self.nombre, cantidad, unidad).como_diccionario()
                    )
        return resultados
