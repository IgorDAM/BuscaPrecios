"""
Formato común de los catálogos publicados (webapp/static/catalogo_<super>.json).

Un archivo por supermercado, con filas en forma de lista (no de objeto) para
que pese poco: el navegador del móvil lo descarga entero para poder buscar
sin ninguna petición más. Las categorías, que se repiten miles de veces, van
en una tabla aparte y cada producto guarda solo su posición.

    {
      "supermercado": "Alimerka",
      "cp": "33012",
      "generado_en": "2026-10-16T16:22:54+00:00",
      "categorias": ["Alimentación > Lo Tienes Hecho > Arroces y Pastas > Arroces", ...],
      "campos": ["pid", "nombre", "marca", "cat", "precio", "precio_unidad", "unidad", "url"],
      "productos": [["10032039", "POLLO AL CURRY CON ARROZ 280 G.", "DELINATUR", 0, 2.99, 10.68, "kg", "https://..."], ...]
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

CAMPOS = ["pid", "nombre", "marca", "cat", "precio", "precio_unidad", "unidad", "url"]


def construir_catalogo(
    supermercado: str,
    cp: str,
    productos: Iterable[Dict],
    ahora: Optional[datetime] = None,
) -> Dict:
    """
    `productos`: dicts con pid, nombre, marca, categoria, precio,
    precio_unidad, unidad y url. Se ordenan por pid para que el archivo sea
    estable entre rastreos (menos ruido en los commits).
    """
    categorias: List[str] = []
    indice: Dict[str, int] = {}
    filas = []
    for p in sorted(productos, key=lambda x: str(x["pid"])):
        cat = p.get("categoria") or ""
        if cat not in indice:
            indice[cat] = len(categorias)
            categorias.append(cat)
        filas.append([
            str(p["pid"]),
            p["nombre"],
            p.get("marca", "") or "",
            indice[cat],
            p["precio"],
            p.get("precio_unidad"),
            p.get("unidad", "") or "",
            p.get("url", "") or "",
        ])
    momento = (ahora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return {
        "supermercado": supermercado,
        "cp": cp,
        "generado_en": momento,
        "categorias": categorias,
        "campos": CAMPOS,
        "productos": filas,
    }


def serializar(catalogo: Dict) -> str:
    """JSON compacto (sin espacios) y con tildes legibles."""
    return json.dumps(catalogo, ensure_ascii=False, separators=(",", ":"))


def catalogo_degradado(previo: Optional[Dict], nuevo: Dict, ratio_minimo: float = 0.5) -> bool:
    """
    True si el rastreo nuevo trae menos de `ratio_minimo` de los productos del
    anterior. Protege el catálogo publicado: un rastreo medio roto (bloqueo de
    Akamai a mitad, cambio de la web...) no debe sustituir a uno bueno.
    """
    if not previo:
        return False
    antes = len(previo.get("productos", []))
    return antes > 0 and len(nuevo.get("productos", [])) < antes * ratio_minimo
