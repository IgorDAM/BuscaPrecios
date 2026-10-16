"""Pruebas de la orquestación (scripts/rastrear_catalogo.py) con rastreadores simulados."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("rastrear_catalogo", RAIZ / "scripts" / "rastrear_catalogo.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def productos(n, prefijo="p"):
    return [{"pid": f"{prefijo}{i}", "nombre": f"PRODUCTO {i}", "marca": "M", "categoria": "Cat",
             "precio": 1.0 + i, "precio_unidad": None, "unidad": "", "url": ""} for i in range(n)]


def rastreador(prods, fallos=(), unidades=10):
    return lambda cp, pausa, max_hojas, log: (list(prods), list(fallos), unidades)


def reg(clave="alimerka", **kw):
    return {clave: ("Alimerka", rastreador(**kw))}


class Orquestacion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.log = []

    def correr(self, rastreadores, **kw):
        return script.ejecutar(list(rastreadores), rastreadores, self.dir, log=self.log.append, **kw)

    def leer(self, clave="alimerka"):
        return json.loads((self.dir / f"catalogo_{clave}.json").read_text(encoding="utf-8"))

    def test_rastreo_correcto_publica_el_catalogo(self):
        self.assertEqual(self.correr(reg(prods=productos(5))), 0)
        c = self.leer()
        self.assertEqual((c["supermercado"], c["cp"], len(c["productos"])), ("Alimerka", "33012", 5))

    def test_rastreo_vacio_no_sobrescribe_el_anterior(self):
        self.correr(reg(prods=productos(5)))
        self.assertEqual(self.correr(reg(prods=[])), 1)
        self.assertEqual(len(self.leer()["productos"]), 5)

    def test_rastreo_muy_recortado_no_sobrescribe(self):
        self.correr(reg(prods=productos(100)))
        self.assertEqual(self.correr(reg(prods=productos(40))), 1)
        self.assertEqual(len(self.leer()["productos"]), 100)

    def test_con_demasiados_fallos_no_se_publica(self):
        codigo = self.correr(reg(prods=productos(5), fallos=["a", "b"], unidades=10))  # 20 %
        self.assertEqual(codigo, 1)
        self.assertFalse((self.dir / "catalogo_alimerka.json").exists())

    def test_pocos_fallos_se_publica_y_se_anota(self):
        self.assertEqual(self.correr(reg(prods=productos(5), fallos=["a"], unidades=100)), 0)
        self.assertIn("1 categorías con fallo", "\n".join(self.log))

    def test_excepcion_del_rastreador_conserva_lo_anterior_y_sigue_con_el_resto(self):
        def roto(cp, pausa, max_hojas, log):
            raise RuntimeError("403 Akamai")
        rastreadores = {"hipercor": ("Hipercor", roto), "alimerka": ("Alimerka", rastreador(productos(3)))}
        self.assertEqual(script.ejecutar(["hipercor", "alimerka"], rastreadores, self.dir, log=self.log.append), 1)
        self.assertFalse((self.dir / "catalogo_hipercor.json").exists())
        self.assertEqual(len(self.leer()["productos"]), 3)  # alimerka sí se publicó

    def test_max_hojas_de_prueba_no_aplica_la_proteccion_anti_recorte(self):
        self.correr(reg(prods=productos(100)))
        self.assertEqual(self.correr(reg(prods=productos(3)), max_hojas=1), 0)


if __name__ == "__main__":
    unittest.main()
