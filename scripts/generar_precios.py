"""
Genera webapp/static/precios_generados.json con los precios de la lista
habitual (data/lista_compra_habitual.json) en los tres supermercados.

Pensado para ejecutarse desde el cron de GitHub Actions
(.github/workflows/precios-cron.yml): así la versión desplegada en Azure
Static Web Apps (sin backend propio) tiene datos que enseñar sin depender
de que ningún PC de casa esté encendido. En modo LAN/local la app sigue
buscando en directo vía webapp/app.py; este JSON es solo para esa versión
estática.

Reintentos: verificado en vivo (2026-09-02) que Hipercor y Mercadona
NO están bloqueados de forma sistemática desde un runner de GitHub
Actions, pero sí de forma intermitente (probablemente porque cada job
sale con una IP distinta de un pool compartido, y el bot-score de Akamai
de esa IP varía). De 3 ejecuciones idénticas, 2 fallaron y 1 funcionó.
Por eso aquí se reintenta el conector ENTERO (no solo una búsqueda
suelta) varias veces antes de rendirse con ese supermercado.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.supermarkets import Mercadona, Hipercor, Alimerka
from src.supermarkets.base import Producto, filtrar_relevantes

CP = "33012"
INTENTOS_NAVEGADOR = 3
ESPERA_ENTRE_INTENTOS_S = 20
SALIDA = RAIZ / "webapp" / "static" / "precios_generados.json"
LISTA_HABITUAL = RAIZ / "data" / "lista_compra_habitual.json"


def cargar_lista() -> list[str]:
    datos = json.loads(LISTA_HABITUAL.read_text(encoding="utf-8"))
    nombres = []
    for item in datos["productos"]:
        nombres.append(item if isinstance(item, str) else item["nombre"])
    return nombres


def producto_a_dict(supermercado: str, p: Producto) -> dict:
    return {
        "supermercado": supermercado,
        "nombre_real": p.nombre_real,
        "marca": p.marca,
        "precio": p.precio,
        "unidad": p.unidad,
        "precio_unidad": p.precio_unidad,
        "url": p.url,
    }


def buscar_con_navegador(nombre_super: str, conector, productos: list[str]):
    """
    Reintenta el conector ENTERO (abre/cierra navegador cada vez) hasta
    INTENTOS_NAVEGADOR veces si no ha devuelto NADA para ninguno de los
    productos, o si ha lanzado una excepción (p.ej. SupermercadoCaido).
    Se queda con el primer intento que traiga algo. Devuelve
    (resultado_por_producto, aviso_o_None).
    """
    ultimo_error = None
    for intento in range(1, INTENTOS_NAVEGADOR + 1):
        try:
            resultado = conector.buscar_productos_multiples(productos)
            total = sum(len(v) for v in resultado.values())
            if total > 0:
                print(f"  [{nombre_super}] intento {intento}/{INTENTOS_NAVEGADOR}: "
                      f"{total} opciones en total -> OK")
                return resultado, None
            print(f"  [{nombre_super}] intento {intento}/{INTENTOS_NAVEGADOR}: "
                  f"0 opciones en toda la lista (probable intermitencia de Akamai)")
        except Exception as e:  # incluye SupermercadoCaido
            ultimo_error = str(e) or type(e).__name__
            print(f"  [{nombre_super}] intento {intento}/{INTENTOS_NAVEGADOR}: "
                  f"error: {ultimo_error}")
        if intento < INTENTOS_NAVEGADOR:
            time.sleep(ESPERA_ENTRE_INTENTOS_S)

    motivo = ultimo_error or "No devolvió ningún resultado tras varios intentos."
    return {p: [] for p in productos}, {"supermercado": nombre_super, "motivo": motivo}


def buscar_alimerka(productos: list[str]):
    """Alimerka va con requests normal: no tiene el problema de Akamai de
    los otros dos, pero se reintenta cada producto por si hay un fallo de
    red suelto."""
    alimerka = Alimerka(CP)
    resultado: dict[str, list[Producto]] = {}
    fallos = []
    for nombre in productos:
        for intento in range(1, 3):
            try:
                resultado[nombre] = alimerka.buscar_productos(nombre)
                break
            except Exception as e:
                if intento == 2:
                    fallos.append(f"{nombre}: {e or type(e).__name__}")
                    resultado[nombre] = []
                else:
                    time.sleep(3)
    aviso = {"supermercado": "Alimerka", "motivo": "; ".join(fallos)} if fallos else None
    return resultado, aviso


def main() -> None:
    productos = cargar_lista()
    print(f"Lista habitual ({len(productos)} productos): {', '.join(productos)}")

    opciones_por_producto: dict[str, list[dict]] = {p: [] for p in productos}
    avisos = []

    def registrar(nombre_super: str, resultado_bruto: dict[str, list[Producto]]) -> None:
        for nombre, encontrados in resultado_bruto.items():
            relevantes = filtrar_relevantes(nombre, encontrados)
            opciones_por_producto[nombre].extend(
                producto_a_dict(nombre_super, p) for p in relevantes
            )

    print("\n== Hipercor ==")
    resultado, aviso = buscar_con_navegador("Hipercor", Hipercor(CP), productos)
    registrar("Hipercor", resultado)
    if aviso:
        avisos.append(aviso)

    print("\n== Mercadona ==")
    resultado, aviso = buscar_con_navegador("Mercadona", Mercadona(CP), productos)
    registrar("Mercadona", resultado)
    if aviso:
        avisos.append(aviso)

    print("\n== Alimerka ==")
    resultado, aviso = buscar_alimerka(productos)
    registrar("Alimerka", resultado)
    if aviso:
        avisos.append(aviso)

    resultados = []
    for nombre in productos:
        opciones = sorted(opciones_por_producto[nombre], key=lambda o: o["precio"])
        resultados.append({"producto": nombre, "opciones": opciones})

    salida = {
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cp": CP,
        "resultados": resultados,
        "avisos": avisos,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    total_opciones = sum(len(r["opciones"]) for r in resultados)
    print(f"\nEscrito {SALIDA} con {total_opciones} opciones en total.")
    if avisos:
        print("Avisos:", avisos)


if __name__ == "__main__":
    main()
