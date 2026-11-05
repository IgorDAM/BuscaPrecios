"""
Caché en disco de los precios ya buscados.

Motivos, los dos importantes:

  1. Cada búsqueda con Hipercor o Mercadona abre un navegador real y tarda
     entre 20 y 40 segundos. Sin caché, tocar un producto de la lista y
     volver a buscar te obliga a esperar otra vez lo mismo.
  2. Hipercor y Mercadona están detrás de Akamai, que bloquea cuando ve
     demasiadas visitas seguidas (nos pasó el 2026-08-10 y dejó Hipercor
     sin responder un buen rato). Cuantas menos visitas, mejor.

Es un JSON por supermercado y código postal, con la hora de cada búsqueda
para poder caducarla. Los precios de supermercado no cambian de un minuto
para otro, así que unas horas de antigüedad son perfectamente válidas.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import List, Optional

# Dónde se guarda: al lado del código, en una carpeta ignorada por git.
DIRECTORIO = Path(__file__).resolve().parent / ".cache_precios"

# Cuánto vale un precio guardado antes de volver a mirarlo.
HORAS_VALIDEZ = 6

# Flask atiende en hilos y varias pestañas/dispositivos pueden buscar a la
# vez. `guardar()` lee el fichero entero, añade una entrada y lo reescribe:
# sin cerrojo, dos hilos pisan la entrada del otro (gana el último y la
# búsqueda del primero se pierde en silencio). Un cerrojo por fichero.
_CERROJOS: dict = {}
_CERROJOS_GUARDIA = threading.Lock()


def _cerrojo(ruta: Path) -> threading.Lock:
    with _CERROJOS_GUARDIA:
        return _CERROJOS.setdefault(str(ruta), threading.Lock())


def _fichero(supermercado: str, codigo_postal: str) -> Path:
    seguro = "".join(c for c in supermercado.lower() if c.isalnum())
    return DIRECTORIO / f"{seguro}_{codigo_postal}.json"


def _cargar(supermercado: str, codigo_postal: str) -> dict:
    ruta = _fichero(supermercado, codigo_postal)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # caché corrupta: se ignora y se reconstruye sola


def leer(supermercado: str, codigo_postal: str, termino: str) -> Optional[List[dict]]:
    """Opciones guardadas para esa búsqueda, o None si no hay o caducaron."""
    entrada = _cargar(supermercado, codigo_postal).get(termino.strip().lower())
    if not entrada:
        return None
    if time.time() - entrada.get("hora", 0) > HORAS_VALIDEZ * 3600:
        return None
    return entrada.get("opciones", [])


def guardar(supermercado: str, codigo_postal: str, termino: str, opciones: List[dict]) -> None:
    """Guarda el resultado de una búsqueda. Si falla, no rompe la búsqueda."""
    ruta = _fichero(supermercado, codigo_postal)
    with _cerrojo(ruta):
        datos = _cargar(supermercado, codigo_postal)
        datos[termino.strip().lower()] = {"hora": time.time(), "opciones": opciones}
        try:
            DIRECTORIO.mkdir(parents=True, exist_ok=True)
            # Escritura atómica: se escribe a un temporal y se renombra. Si el
            # proceso muere a mitad, queda el fichero anterior intacto en vez
            # de un JSON a medias.
            temporal = ruta.with_suffix(f".{os.getpid()}.tmp")
            temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            os.replace(temporal, ruta)
        except OSError:
            pass  # no poder guardar la caché no debe impedir enseñar los precios


def limpiar() -> None:
    """Borra toda la caché (para forzar precios frescos)."""
    if not DIRECTORIO.exists():
        return
    for f in list(DIRECTORIO.glob("*.json")) + list(DIRECTORIO.glob("*.tmp")):
        try:
            f.unlink()
        except OSError:
            pass
