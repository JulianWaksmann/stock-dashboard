"""
cartera/mep_source.py - Historia del dólar MEP, de ArgentinaDatos.

Toca la red pero no Streamlit, igual que `crypto/prices_source.py`: el caché
vive en `cartera/data_loader.py`.

Hace falta para Cocos, que exporta movimientos en pesos sin el tipo de cambio
de cada fecha (Balanz sí lo trae en su Excel y no pasa por acá). El endpoint
sin fecha devuelve la serie entera en un solo pedido —unos 2.900 días desde
2018—, así que no hay que pedir día por día.
"""

from __future__ import annotations

import pandas as pd
import requests

MEP_URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa"
_TIMEOUT_SEGUNDOS = 20


def fetch_serie_mep() -> pd.Series:
    """
    Serie diaria del MEP (precio de venta), indexada por fecha ISO y ordenada.

    Lanza `requests.RequestException` o `ValueError` si la fuente no responde
    o cambia de forma: decidir qué hacer sin MEP es cosa de quien llama.
    """
    respuesta = requests.get(MEP_URL, timeout=_TIMEOUT_SEGUNDOS)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if not isinstance(datos, list) or not datos:
        raise ValueError("ArgentinaDatos devolvió una serie de MEP vacía o con otro formato")
    df = pd.DataFrame(datos)
    if not {"fecha", "venta"} <= set(df.columns):
        raise ValueError("ArgentinaDatos cambió el formato de la serie de MEP")
    serie = pd.Series(pd.to_numeric(df["venta"], errors="coerce").values, index=df["fecha"].astype(str).str[:10])
    return serie[serie > 0].sort_index()
