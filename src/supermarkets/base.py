from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProductoEncontrado:
    nombre: str
    precio: float
    supermercado: str
    cantidad: float = 1.0
    unidad: str = "ud"

    def como_diccionario(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "precio": self.precio,
            "supermercado": self.supermercado,
            "cantidad": self.cantidad,
            "unidad": self.unidad,
        }


class Supermercado(ABC):
    def __init__(self, codigo_postal: str) -> None:
        self.codigo_postal = codigo_postal

    @property
    @abstractmethod
    def nombre(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def buscar_productos(self, nombre_producto: str) -> list[dict[str, Any]]:
        raise NotImplementedError
