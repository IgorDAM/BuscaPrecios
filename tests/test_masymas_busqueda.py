"""Paginación de la búsqueda de Más y Más (sin red: sesión simulada)."""
import unittest

from src.supermarkets.masymas import MasYMas, TAM_PAGINA_BUSQUEDA


def _tarjeta(pid, nombre="Leche", precio="1.00"):
    return (f'<div class="product" data-pid="{pid}" data-brand="X" data-price="{precio}">'
            f'<a class="link" href="/p/{pid}.html">{nombre} {pid} 1 L</a></div>')


class _Resp:
    def __init__(self, html):
        self.text = html

    def raise_for_status(self):
        pass


class _Sesion:
    def __init__(self, paginas, ignora_start=False):
        self.paginas, self.ignora_start, self.llamadas = paginas, ignora_start, []

    def get(self, url, params=None, timeout=0):
        self.llamadas.append(dict(params))
        i = 0 if self.ignora_start else params["start"] // TAM_PAGINA_BUSQUEDA
        return _Resp("<html>" + "".join(self.paginas[i] if i < len(self.paginas) else []) + "</html>")


def _con(sesion):
    m = MasYMas()
    m._session = sesion
    return m


class BusquedaMasYMas(unittest.TestCase):
    def test_pagina_corta_no_pide_mas(self):
        s = _Sesion([[_tarjeta(i) for i in range(18)]])
        r = _con(s).buscar_productos("leche")
        self.assertEqual(len(r), 18)
        self.assertEqual(len(s.llamadas), 1)

    def test_pagina_llena_pide_la_siguiente(self):
        p1 = [_tarjeta(i) for i in range(TAM_PAGINA_BUSQUEDA)]
        p2 = [_tarjeta(1000 + i) for i in range(10)]
        s = _Sesion([p1, p2])
        r = _con(s).buscar_productos("leche")
        self.assertEqual(len(r), TAM_PAGINA_BUSQUEDA + 10)
        self.assertEqual([c["start"] for c in s.llamadas], [0, TAM_PAGINA_BUSQUEDA])

    def test_si_la_web_ignora_start_no_hay_bucle_ni_duplicados(self):
        p1 = [_tarjeta(i) for i in range(TAM_PAGINA_BUSQUEDA)]
        s = _Sesion([p1], ignora_start=True)
        r = _con(s).buscar_productos("leche")
        self.assertEqual(len(r), TAM_PAGINA_BUSQUEDA)
        self.assertEqual(len(s.llamadas), 2)  # la segunda no aporta nada nuevo: para


if __name__ == "__main__":
    unittest.main()
