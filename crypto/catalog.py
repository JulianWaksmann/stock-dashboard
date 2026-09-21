"""
crypto/catalog.py - Universo de criptomonedas del panel.

Es código y no un CSV editable (a diferencia de `data/ons_catalog.csv`)
porque acá no hay condiciones contractuales que cargar a mano: son apenas
un ticker, un nombre y una categoría. El dato que importa —precio e
historial— se baja entero de Yahoo Finance.

Sobre los tickers: Yahoo Finance publica cada cripto como `SÍMBOLO-USD`,
pero cuando el símbolo choca con el de otro instrumento le agrega un número
(`UNI7083-USD` es Uniswap, `PEPE24478-USD` es Pepe). Por eso varios tickers
de acá no se parecen al símbolo que muestra cualquier exchange: el que vale
es el de Yahoo, y está verificado contra el feed.

**Las stablecoins quedan afuera a propósito.** USDT, USDC y DAI cotizan
pegadas a un dólar por diseño: su RSI, sus medias y sus bandas de Bollinger
describen ruido de centésimas, y el semáforo las leería como si ese ruido
fuera una tendencia. No es que falten, es que no hay nada técnico que leer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from constants import (
    CRYPTO_UNIVERSE_DEFI,
    CRYPTO_UNIVERSE_LAYER1,
    CRYPTO_UNIVERSE_MEME,
    CRYPTO_UNIVERSE_TOP,
)

# Categorías internas del catálogo. Son la etiqueta que se muestra en la
# tabla; los universos del selector se arman más abajo a partir de ellas.
CATEGORY_LAYER1: Final[str] = "Capa 1"
CATEGORY_DEFI: Final[str] = "DeFi / Infraestructura"
CATEGORY_MEME: Final[str] = "Memecoin"


@dataclass(frozen=True)
class CryptoAsset:
    """
    Una cripto del universo.

    `ticker` es el símbolo de Yahoo Finance (el que se baja), `simbolo` el
    que usa el mercado (el que se muestra). Casi siempre coinciden salvo el
    sufijo `-USD`, pero no siempre: ver el docstring del módulo.
    """

    ticker: str
    simbolo: str
    nombre: str
    categoria: str


# Universo completo, ordenado de mayor a menor capitalización dentro de cada
# categoría. Todos los tickers están verificados contra el feed de Yahoo.
CRYPTO_UNIVERSE: Final[tuple[CryptoAsset, ...]] = (
    # --- Capa 1: las redes base ---
    CryptoAsset("BTC-USD", "BTC", "Bitcoin", CATEGORY_LAYER1),
    CryptoAsset("ETH-USD", "ETH", "Ethereum", CATEGORY_LAYER1),
    CryptoAsset("BNB-USD", "BNB", "BNB", CATEGORY_LAYER1),
    CryptoAsset("SOL-USD", "SOL", "Solana", CATEGORY_LAYER1),
    CryptoAsset("XRP-USD", "XRP", "XRP", CATEGORY_LAYER1),
    CryptoAsset("ADA-USD", "ADA", "Cardano", CATEGORY_LAYER1),
    CryptoAsset("TRX-USD", "TRX", "TRON", CATEGORY_LAYER1),
    CryptoAsset("AVAX-USD", "AVAX", "Avalanche", CATEGORY_LAYER1),
    CryptoAsset("DOT-USD", "DOT", "Polkadot", CATEGORY_LAYER1),
    CryptoAsset("NEAR-USD", "NEAR", "NEAR Protocol", CATEGORY_LAYER1),
    CryptoAsset("LTC-USD", "LTC", "Litecoin", CATEGORY_LAYER1),
    CryptoAsset("BCH-USD", "BCH", "Bitcoin Cash", CATEGORY_LAYER1),
    CryptoAsset("XLM-USD", "XLM", "Stellar", CATEGORY_LAYER1),
    CryptoAsset("HBAR-USD", "HBAR", "Hedera", CATEGORY_LAYER1),
    CryptoAsset("ICP-USD", "ICP", "Internet Computer", CATEGORY_LAYER1),
    CryptoAsset("ATOM-USD", "ATOM", "Cosmos", CATEGORY_LAYER1),
    CryptoAsset("ETC-USD", "ETC", "Ethereum Classic", CATEGORY_LAYER1),
    CryptoAsset("ALGO-USD", "ALGO", "Algorand", CATEGORY_LAYER1),
    CryptoAsset("VET-USD", "VET", "VeChain", CATEGORY_LAYER1),
    # --- DeFi e infraestructura ---
    CryptoAsset("LINK-USD", "LINK", "Chainlink", CATEGORY_DEFI),
    CryptoAsset("UNI7083-USD", "UNI", "Uniswap", CATEGORY_DEFI),
    CryptoAsset("AAVE-USD", "AAVE", "Aave", CATEGORY_DEFI),
    CryptoAsset("MKR-USD", "MKR", "Maker", CATEGORY_DEFI),
    CryptoAsset("INJ-USD", "INJ", "Injective", CATEGORY_DEFI),
    CryptoAsset("RENDER-USD", "RENDER", "Render", CATEGORY_DEFI),
    CryptoAsset("ARB11841-USD", "ARB", "Arbitrum", CATEGORY_DEFI),
    CryptoAsset("OP-USD", "OP", "Optimism", CATEGORY_DEFI),
    CryptoAsset("FIL-USD", "FIL", "Filecoin", CATEGORY_DEFI),
    CryptoAsset("GRT6719-USD", "GRT", "The Graph", CATEGORY_DEFI),
    CryptoAsset("CRV-USD", "CRV", "Curve DAO", CATEGORY_DEFI),
    # --- Memecoins ---
    CryptoAsset("DOGE-USD", "DOGE", "Dogecoin", CATEGORY_MEME),
    CryptoAsset("SHIB-USD", "SHIB", "Shiba Inu", CATEGORY_MEME),
    CryptoAsset("PEPE24478-USD", "PEPE", "Pepe", CATEGORY_MEME),
    CryptoAsset("BONK-USD", "BONK", "Bonk", CATEGORY_MEME),
    CryptoAsset("WIF-USD", "WIF", "dogwifhat", CATEGORY_MEME),
    CryptoAsset("FLOKI-USD", "FLOKI", "Floki", CATEGORY_MEME),
)

# Las veinte de mayor capitalización, que es el universo por omisión. Se
# enumeran a mano en vez de recortar las primeras N del catálogo porque el
# orden de arriba agrupa por categoría, no por tamaño.
_TOP_TICKERS: Final[tuple[str, ...]] = (
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "DOGE-USD", "ADA-USD", "TRX-USD", "LINK-USD", "AVAX-USD",
    "XLM-USD", "BCH-USD", "LTC-USD", "DOT-USD", "HBAR-USD",
    "SHIB-USD", "ICP-USD", "NEAR-USD", "UNI7083-USD", "AAVE-USD",
)

_BY_TICKER: Final[dict[str, CryptoAsset]] = {a.ticker: a for a in CRYPTO_UNIVERSE}


def find_asset(ticker: str) -> CryptoAsset | None:
    """Devuelve la cripto del catálogo con ese ticker de Yahoo, o None."""
    return _BY_TICKER.get(ticker.strip().upper())


def assets_for_universe(universe: str) -> tuple[CryptoAsset, ...]:
    """
    Criptos que integran el universo elegido en el selector.

    `universe` es uno de los literales de `CRYPTO_UNIVERSE_OPTIONS`. Un texto
    desconocido devuelve el universo por omisión en vez de una lista vacía:
    una sección en blanco no se distingue de un error de red.
    """
    if universe == CRYPTO_UNIVERSE_LAYER1:
        return tuple(a for a in CRYPTO_UNIVERSE if a.categoria == CATEGORY_LAYER1)
    if universe == CRYPTO_UNIVERSE_DEFI:
        return tuple(a for a in CRYPTO_UNIVERSE if a.categoria == CATEGORY_DEFI)
    if universe == CRYPTO_UNIVERSE_MEME:
        return tuple(a for a in CRYPTO_UNIVERSE if a.categoria == CATEGORY_MEME)
    if universe != CRYPTO_UNIVERSE_TOP:
        return assets_for_universe(CRYPTO_UNIVERSE_TOP)
    return tuple(_BY_TICKER[t] for t in _TOP_TICKERS)


def tickers_for_universe(universe: str) -> list[str]:
    """Tickers de Yahoo del universo elegido, en el orden del catálogo."""
    return [a.ticker for a in assets_for_universe(universe)]
