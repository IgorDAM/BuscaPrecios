"""Caché en disco de precios: escritura atómica, cerrojo y caducidad (sin red)."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webapp"))
import cache  # noqa: E402


class CacheEnDisco(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original = cache.DIRECTORIO
        cache.DIRECTORIO = Path(self._tmp.name)

    def tearDown(self):
        cache.DIRECTORIO = self._original
        self._tmp.cleanup()

    def test_guardar_y_leer(self):
        cache.guardar("Alimerka", "33012", "Leche ", [{"precio": 1.0}])
        self.assertEqual(cache.leer("Alimerka", "33012", "leche"), [{"precio": 1.0}])

    def test_no_existente_devuelve_none(self):
        self.assertIsNone(cache.leer("Alimerka", "33012", "nada"))

    def test_caducada_devuelve_none(self):
        cache.guardar("Alimerka", "33012", "leche", [{"precio": 1.0}])
        ruta = cache._fichero("Alimerka", "33012")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["leche"]["hora"] = time.time() - (cache.HORAS_VALIDEZ + 1) * 3600
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        self.assertIsNone(cache.leer("Alimerka", "33012", "leche"))

    def test_fichero_corrupto_se_ignora_y_se_reconstruye(self):
        ruta = cache._fichero("Alimerka", "33012")
        ruta.write_text("{esto no es json", encoding="utf-8")
        self.assertIsNone(cache.leer("Alimerka", "33012", "leche"))
        cache.guardar("Alimerka", "33012", "leche", [{"precio": 2.0}])
        self.assertEqual(cache.leer("Alimerka", "33012", "leche"), [{"precio": 2.0}])

    def test_guardado_concurrente_no_pierde_entradas(self):
        """Antes (leer-modificar-escribir sin cerrojo) los hilos se pisaban."""
        terminos = [f"producto{i}" for i in range(40)]
        hilos = [
            threading.Thread(target=cache.guardar, args=("Mercadona", "33012", t, [{"n": t}]))
            for t in terminos
        ]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        for t in terminos:
            self.assertEqual(cache.leer("Mercadona", "33012", t), [{"n": t}], t)

    def test_no_deja_temporales_tras_guardar(self):
        cache.guardar("Alimerka", "33012", "leche", [])
        self.assertEqual(list(cache.DIRECTORIO.glob("*.tmp")), [])

    def test_limpiar_borra_todo(self):
        cache.guardar("Alimerka", "33012", "leche", [])
        cache.guardar("Mercadona", "33012", "leche", [])
        cache.limpiar()
        self.assertIsNone(cache.leer("Alimerka", "33012", "leche"))
        self.assertIsNone(cache.leer("Mercadona", "33012", "leche"))


if __name__ == "__main__":
    unittest.main()
