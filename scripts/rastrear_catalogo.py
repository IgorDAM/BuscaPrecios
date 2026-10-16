"""
Rastrea el catálogo completo de cada supermercado y escribe
webapp/static/catalogo_<supermercado>.json (formato en src/catalogo/formato.py).

Lo ejecuta el cron semanal de GitHub Actions
(.github/workflows/catalogo-cron.yml). La web desplegada en Azure Static Web
Apps busca sobre estos archivos, así que cualquier producto del catálogo se
puede buscar sin consultar nada en directo (que en Hipercor y Mercadona no
se puede hacer desde la nube: Akamai).

Protecciones: un supermercado cuyo rastreo sale vacío, con demasiados
fallos o muy por debajo del catálogo anterior NO sobrescribe el archivo
publicado (se queda el bueno, con su fecha) y el script termina con código 1.

Uso:
    python scripts/rastrear_catalogo.py                      # todos
    python scripts/rastrear_catalogo.py --solo alimerka
    python scripts/rastrear_catalogo.py --solo alimerka --max-hojas 3   # prueba rápida
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.catalogo.formato import catalogo_degradado, construir_catalogo, serializar

CP = "33012"
SALIDA_POR_DEFECTO = RAIZ / "webapp" / "static"
# Más de este porcentaje de categorías que fallen = rastreo poco fiable.
MAX_FALLOS_RATIO = 0.05

# Un rastreador devuelve (productos, fallos, n_unidades_rastreadas).
Rastreador = Callable[[str, float, Optional[int], Callable[[str], None]], Tuple[List[dict], List[str], int]]


def _rastrear_alimerka(cp, pausa, max_hojas, log):
    from src.catalogo.alimerka import rastrear
    from src.supermarkets.alimerka import Alimerka

    r = rastrear(Alimerka(cp), pausa_s=pausa, max_hojas=max_hojas, log=log)
    return r.productos, r.fallos, r.n_hojas


def _rastrear_mercadona(cp, pausa, max_hojas, log):
    # Navegador visible (en Actions, bajo xvfb): ver src/catalogo/mercadona.py
    from src.catalogo.mercadona import rastrear_con_navegador

    r = rastrear_con_navegador(cp, min(pausa, 0.5), max_hojas, log)
    return r.productos, r.fallos, r.n_hojas


def _rastrear_hipercor(cp, pausa, max_hojas, log):
    from src.catalogo.hipercor import rastrear_con_navegador

    r = rastrear_con_navegador(cp, pausa, max_hojas, log)
    return r.productos, r.fallos, r.n_hojas


# Nombre -> (nombre para mostrar, rastreador).
RASTREADORES: Dict[str, Tuple[str, Rastreador]] = {
    "alimerka": ("Alimerka", _rastrear_alimerka),
    "mercadona": ("Mercadona", _rastrear_mercadona),
    "hipercor": ("Hipercor", _rastrear_hipercor),
}


def ruta_catalogo(salida: Path, clave: str) -> Path:
    return salida / f"catalogo_{clave}.json"


def _leer(ruta: Path) -> Optional[dict]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ejecutar(
    claves: List[str],
    rastreadores: Dict[str, Tuple[str, Rastreador]],
    salida: Path,
    cp: str = CP,
    pausa: float = 1.0,
    max_hojas: Optional[int] = None,
    log: Callable[[str], None] = print,
) -> int:
    """Rastrea y publica cada supermercado. Devuelve 0 si todo fue bien, 1 si
    alguno falló (los que sí salieron bien quedan publicados igualmente)."""
    codigo = 0
    for clave in claves:
        nombre, rastrear = rastreadores[clave]
        log(f"\n== {nombre} ==")
        try:
            productos, fallos, unidades = rastrear(cp, pausa, max_hojas, log)
        except Exception as e:
            log(f"  ERROR: {e or type(e).__name__}. Se conserva el catálogo anterior.")
            codigo = 1
            continue

        if not productos:
            log("  ERROR: el rastreo no devolvió ningún producto. Se conserva el catálogo anterior.")
            codigo = 1
            continue
        if unidades and len(fallos) / unidades > MAX_FALLOS_RATIO:
            log(f"  ERROR: fallaron {len(fallos)} de {unidades} categorías "
                f"(>{MAX_FALLOS_RATIO:.0%}); no se publica. Primeros fallos:")
            for f in fallos[:5]:
                log(f"    - {f}")
            codigo = 1
            continue

        nuevo = construir_catalogo(nombre, cp, productos)
        destino = ruta_catalogo(salida, clave)
        if catalogo_degradado(_leer(destino), nuevo) and not max_hojas:
            log("  ERROR: el rastreo trae menos de la mitad de productos que el catálogo "
                f"publicado ({len(nuevo['productos'])}); no se sobrescribe.")
            codigo = 1
            continue

        salida.mkdir(parents=True, exist_ok=True)
        destino.write_text(serializar(nuevo), encoding="utf-8")
        kb = destino.stat().st_size / 1024
        log(f"  OK: {len(nuevo['productos'])} productos, {len(nuevo['categorias'])} categorías, "
            f"{kb:,.0f} KB -> {destino.name}" + (f" ({len(fallos)} categorías con fallo)" if fallos else ""))
    return codigo


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--solo", nargs="+", choices=sorted(RASTREADORES), default=sorted(RASTREADORES),
                    help="supermercados a rastrear (por defecto, todos)")
    ap.add_argument("--max-hojas", type=int, default=None,
                    help="solo para pruebas: limita el nº de categorías (no aplica la protección anti-recorte)")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre peticiones (por defecto 1)")
    ap.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    args = ap.parse_args(argv)
    return ejecutar(args.solo, RASTREADORES, args.salida, pausa=args.pausa, max_hojas=args.max_hojas)


if __name__ == "__main__":
    sys.exit(main())
