from .alimerka import Alimerka
from .hipercor import Hipercor
from .mercadona import Mercadona


def crear_supermercados(codigo_postal: str, nombres: list[str]):
    disponibles = {
        "alimerka": Alimerka,
        "hipercor": Hipercor,
        "mercadona": Mercadona,
    }
    seleccionados = []
    for nombre in nombres:
        nombre_normalizado = nombre.strip().lower()
        constructor = disponibles.get(nombre_normalizado)
        if constructor is not None:
            seleccionados.append(constructor(codigo_postal))
    return seleccionados
