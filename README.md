# BuscaPrecios

Comparador de precios entre Mercadona, Hipercor y Alimerka con CLI y webapp local.

## Uso rápido

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.main --cp 33012 --lista data/lista_compra_ejemplo.json
cd webapp && python app.py
```
