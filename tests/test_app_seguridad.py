"""Protecciones del backend Flask en modo LAN (conectores simulados, sin red)."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from src.supermarkets.base import Producto

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webapp"))
import webapp.app as servidor  # noqa: E402
import cache  # noqa: E402


class _AlimerkaFalso:
    """Cuenta cuántas veces se consulta la web 'de verdad'."""
    llamadas = []
    pausa = 0.0

    def __init__(self, cp=None):
        pass

    def buscar_productos(self, nombre):
        _AlimerkaFalso.llamadas.append(nombre)
        time.sleep(_AlimerkaFalso.pausa)
        return [Producto(nombre_buscado=nombre, nombre_real=f"{nombre} entera 1 L",
                         precio=1.0, marca="X", unidad="L", precio_unidad=1.0)]


def _peticion(cliente, productos, **extra):
    cuerpo = {"cp": "33012", "productos": productos, "incluir_hipercor": False,
              "incluir_mercadona": False, **extra}
    return cliente.post("/api/buscar", json=cuerpo)


class BackendSeguro(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = cache.DIRECTORIO
        cache.DIRECTORIO = Path(self._tmp.name)
        servidor._visitas.clear()
        _AlimerkaFalso.llamadas = []
        _AlimerkaFalso.pausa = 0.0
        self._parche = mock.patch.object(servidor, "Alimerka", _AlimerkaFalso)
        self._parche.start()
        self.cliente = servidor.app.test_client()

    def tearDown(self):
        self._parche.stop()
        cache.DIRECTORIO = self._dir
        self._tmp.cleanup()

    # --- validación de entrada ---
    def test_cuerpo_que_no_es_objeto_da_400(self):
        r = self.cliente.post("/api/buscar", json=[1, 2])
        self.assertEqual(r.status_code, 400)

    def test_productos_no_lista_da_400(self):
        r = _peticion(self.cliente, "leche")
        self.assertEqual(r.status_code, 400)

    def test_producto_no_texto_da_400(self):
        r = _peticion(self.cliente, [123])
        self.assertEqual(r.status_code, 400)

    def test_nombre_demasiado_largo_da_400(self):
        r = _peticion(self.cliente, ["x" * (servidor.MAX_LARGO_NOMBRE + 1)])
        self.assertEqual(r.status_code, 400)

    def test_demasiados_productos_da_400(self):
        r = _peticion(self.cliente, [f"p{i}" for i in range(servidor.MAX_PRODUCTOS + 1)])
        self.assertEqual(r.status_code, 400)

    def test_duplicados_y_vacios_se_descartan(self):
        r = _peticion(self.cliente, ["leche", " leche ", "", "leche"], incluir_alimerka=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["producto"] for x in r.get_json()["resultados"]], ["leche"])
        self.assertEqual(_AlimerkaFalso.llamadas, ["leche"])

    # --- límite de peticiones ---
    def test_limite_de_peticiones_da_429(self):
        with mock.patch.object(servidor, "LIMITE_PETICIONES", 3):
            codigos = [_peticion(self.cliente, ["leche"], incluir_alimerka=True).status_code
                       for _ in range(5)]
        self.assertEqual(codigos, [200, 200, 200, 429, 429])

    # --- DELETE /api/cache ---
    def test_delete_cache_desde_la_red_es_403(self):
        r = self.cliente.delete("/api/cache", environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
        self.assertEqual(r.status_code, 403)

    def test_delete_cache_local_es_200(self):
        r = self.cliente.delete("/api/cache", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        self.assertEqual(r.status_code, 200)

    def test_delete_cache_con_token_desde_la_red(self):
        with mock.patch.dict(os.environ, {"BUSCAPRECIOS_TOKEN": "secreto"}):
            malo = self.cliente.delete("/api/cache", headers={"X-Token": "otro"},
                                       environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
            bueno = self.cliente.delete("/api/cache", headers={"X-Token": "secreto"},
                                        environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
        self.assertEqual((malo.status_code, bueno.status_code), (403, 200))

    def test_delete_cache_sin_token_configurado_ignora_cabecera_vacia(self):
        """Sin BUSCAPRECIOS_TOKEN, una cabecera vacía NO debe contar como válida."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUSCAPRECIOS_TOKEN", None)
            r = self.cliente.delete("/api/cache", headers={"X-Token": ""},
                                    environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
        self.assertEqual(r.status_code, 403)

    def test_health(self):
        self.assertEqual(self.cliente.get("/api/health").get_json(), {"ok": True})

    # --- cerrojo por supermercado ---
    def test_dos_dispositivos_a_la_vez_solo_consultan_la_web_una_vez(self):
        _AlimerkaFalso.pausa = 0.3
        resultados = []

        def lanzar():
            c = servidor.app.test_client()
            resultados.append(_peticion(c, ["leche"], incluir_alimerka=True).status_code)

        hilos = [threading.Thread(target=lanzar) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(resultados, [200, 200])
        # El segundo esperó al cerrojo y encontró los precios en caché.
        self.assertEqual(_AlimerkaFalso.llamadas, ["leche"])


if __name__ == "__main__":
    unittest.main()
