"""
Peso/volumen de los productos y precio por kilo o litro.

Por qué hace falta: comparar por el precio del paquete engaña cuando los
formatos no coinciden. Buscando "jamón serrano" (verificado el
2026-08-10) salía Alimerka a 2,29 € y Mercadona a 2,30 €, pareciendo casi
lo mismo, cuando en realidad son 120 g frente a 90 g: 19,08 €/kg frente a
25,56 €/kg. Lo mismo pasa con cualquier cosa que se venda al peso.

Cada supermercado lo cuenta a su manera (todo verificado en vivo):

  - Hipercor lo da ya calculado (`measurementUnitPrice` + `pum_description`).
  - Mercadona lo pone en el formato de la tarjeta: "Paquete 120 Gramos",
    "2 paquetes x 120 Gramos", "6 briks x 1 Litro".
  - Alimerka no lo da en ningún campo: va dentro del propio nombre
    ("JAMÓN SERRANO RESERVA 120 G.", "LECHE ENTERA 1 LITRO").

Este módulo entiende esos tres formatos y los reduce a kilos o litros.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Cuánto vale cada unidad expresada en la unidad base (kg o L).
_UNIDADES = {
    "kg": ("kg", 1.0),
    "kilo": ("kg", 1.0),
    "kilos": ("kg", 1.0),
    "kilogramo": ("kg", 1.0),
    "kilogramos": ("kg", 1.0),
    "g": ("kg", 0.001),
    "gr": ("kg", 0.001),
    "grs": ("kg", 0.001),  # Alimerka escribe "390 GRS."
    "gramo": ("kg", 0.001),
    "gramos": ("kg", 0.001),
    "l": ("L", 1.0),
    "lt": ("L", 1.0),
    "lts": ("L", 1.0),
    "litro": ("L", 1.0),
    "litros": ("L", 1.0),
    "ml": ("L", 0.001),
    "cc": ("L", 0.001),
    "mililitro": ("L", 0.001),
    "mililitros": ("L", 0.001),
    "cl": ("L", 0.01),
    "centilitro": ("L", 0.01),
    "centilitros": ("L", 0.01),
}

# "6 briks x 1 Litro", "2 paquetes x 120 Gramos", "250 g", "1,5 L"
_MEDIDA_RE = re.compile(
    # Multiplicador opcional: "6 briks x", "6 mini briks x", "2 paquetes x"
    r"(?:(\d+)\s*(?:[a-zá-úü.]+\s+){0,3}x\s*)?"
    r"(\d+(?:[.,]\d+)?)\s*"                     # cantidad: "120", "1,5"
    r"(kg|kilogramos?|kilos?|gramos?|grs|gr|g|litros?|lts|lt|l|mililitros?|ml|centilitros?|cl|cc)\b",
    re.IGNORECASE,
)

# Multiplicador escrito DESPUÉS de la medida: "210 GRS. PACK 3" (Alimerka).
_PACK_POSTERIOR_RE = re.compile(r"\b(?:pack|packs)\s*(?:de\s*)?(\d+)", re.IGNORECASE)

# Fresco de mostrador vendido literalmente "al kilo"/"al litro", SIN
# ningún número delante en el nombre (verificado en vivo, 2026-09-03:
# "CECINA DE VACUNO BABILLA EL KILO", "QUESO EN BARRA EL KILO", "LOMO
# EMBUCHADO EL KILO", "JAMÓN SERRANO RVA DUROC 25% MENOS SAL EL KILO").
# _MEDIDA_RE no lo reconoce porque exige un número pegado a la unidad, y
# sin reconocerlo `precio_unidad` quedaba `None`: la webapp entonces
# cobraba el precio de venta COMPLETO en vez de escalarlo a los gramos
# pedidos (ver CLAUDE.md, "Por qué el total simulado se dispara...").
# Aquí el precio que se ve YA es el del kilo/litro entero, así que basta
# con devolver cantidad=1 en esa unidad.
_AL_KILO_RE = re.compile(r"\b(?:el|al|por)\s+(kilo|litro)\b", re.IGNORECASE)


def parsear_medida(texto: str) -> Optional[Tuple[float, str]]:
    """
    Saca de un texto cuánto producto hay, en kilos o litros.

    Devuelve (cantidad, "kg" | "L"), o None si no se reconoce nada.
    """
    if not texto:
        return None

    for m in _MEDIDA_RE.finditer(texto):
        multiplicador = int(m.group(1)) if m.group(1) else 1
        try:
            cantidad = float(m.group(2).replace(",", "."))
        except ValueError:
            continue
        unidad_texto = m.group(3).lower()
        if unidad_texto not in _UNIDADES:
            continue
        base, factor = _UNIDADES[unidad_texto]

        # "210 GRS. PACK 3" son 630 g, no 210: el pack va detrás. Solo se
        # aplica si no había ya un multiplicador delante ("2 x 120 g").
        if multiplicador == 1:
            posterior = _PACK_POSTERIOR_RE.search(texto[m.end():])
            if posterior:
                multiplicador = int(posterior.group(1))

        total = multiplicador * cantidad * factor
        if total > 0:
            return (total, base)

    m = _AL_KILO_RE.search(texto)
    if m:
        base = "kg" if m.group(1).lower() == "kilo" else "L"
        return (1.0, base)

    return None


def precio_por_medida(precio: float, texto: str) -> Tuple[Optional[float], str]:
    """
    Precio por kilo/litro a partir del precio del paquete y un texto que
    describa el formato. Devuelve (precio_unidad, unidad); si no se puede
    saber el formato, (None, "").
    """
    medida = parsear_medida(texto)
    if not medida:
        return (None, "")
    cantidad, unidad = medida
    return (round(precio / cantidad, 2), unidad)


def normalizar_unidad(texto: str) -> str:
    """Pasa las etiquetas de cada web ('Kilo', 'Litro') a 'kg' / 'L'."""
    clave = (texto or "").strip().lower()
    if clave in _UNIDADES:
        return _UNIDADES[clave][0]
    return texto or ""
