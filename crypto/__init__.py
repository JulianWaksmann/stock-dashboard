"""
crypto/ - Motor de criptomonedas del tablero.

Es el tercer motor, junto al de acciones y el de renta fija, y respeta el
mismo reparto de capas que ellos:

    I/O con red + Streamlit  →  cálculo puro  →  dibujo
    crypto/data_loader.py       crypto/panel.py   components/crypto_*.py

`crypto/catalog.py` y `crypto/panel.py` no importan `streamlit` ni tocan la
red: se testean con OHLCV fijo, sin mocks. `scripts/panel_cripto.py` corre
esa misma cadena desde la terminal y se rompe si la separación se pierde.

Comparte con acciones la lectura técnica (`indicators.py`) pero no el modelo
de datos: una cripto no tiene balances, así que no hay PER ni sector, y opera
los siete días de la semana, así que las ventanas de calendario se miden en
otra cantidad de barras.
"""
