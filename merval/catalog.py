"""
merval/catalog.py - Universo del panel argentino y sus pares con ADR.

Es código y no un CSV editable, igual que `crypto/catalog.py`: son un ticker,
un nombre, un sector y —cuando la empresa tiene ADR— el **ratio de conversión**
del programa, o sea cuántas acciones locales equivalen a un ADR. No hay
condiciones contractuales que cargar a mano como en las ONs.

Por qué el ratio importa tanto: es lo único que falta para calcular el dólar
implícito (CCL) de cada par. Con el precio local en pesos, el del ADR en
dólares y el ratio, el tipo de cambio sale de una división. Un ratio mal
cargado no rompe nada: devuelve un dólar silenciosamente equivocado para ese
par, y con él un precio en dólares equivocado para toda la acción.

Cómo se protege el panel de eso, porque `ratio_verificado` arranca en False
para todas:

  * El CCL del panel es la **mediana** de todos los pares, no el promedio ni el
    de un par elegido: un ratio mal cargado queda como un valor extremo y la
    mediana no se mueve.
  * `merval/ccl.py` publica un diagnóstico por par con su desvío contra esa
    mediana y el ratio que lo volvería consistente. Es la forma práctica de
    verificar la tabla: correr `scripts/panel_merval.py --ccl` contra precios
    reales y mirar qué par se despega.

Los ratios de los programas de ADR **cambian** (un split o una reestructuración
los altera), así que la marca de verificación vale contra la fecha en que se
miró, no para siempre.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTOR_BANCOS = "Bancos"
SECTOR_ENERGIA = "Energía y utilities"
SECTOR_MATERIALES = "Materiales"
SECTOR_CONSUMO = "Consumo"
SECTOR_INMOBILIARIO = "Inmobiliario y agro"
SECTOR_TELECOM = "Telecomunicaciones"
SECTOR_FINANCIERO = "Servicios financieros"


@dataclass(frozen=True)
class MervalStock:
    """
    Una acción del panel local, con su par en Nueva York si lo tiene.

    `adr_ratio` son acciones locales por ADR. `ratio_verificado` dice si ese
    número se comprobó contra el programa del ADR (y no solo contra el
    diagnóstico de consistencia, que detecta un ratio absurdo pero no
    distingue entre dos plausibles).
    """

    ticker: str
    nombre: str
    sector: str
    adr: str | None = None
    adr_ratio: int | None = None
    ratio_verificado: bool = False

    @property
    def tiene_adr(self) -> bool:
        return bool(self.adr) and bool(self.adr_ratio)


# Panel líder. Los tickers locales llevan el sufijo `.BA`, que es como publica
# Yahoo Finance las especies de BYMA.
MERVAL_UNIVERSE: tuple[MervalStock, ...] = (
    MervalStock("GGAL.BA", "Grupo Financiero Galicia", SECTOR_BANCOS, "GGAL", 10),
    # Ratio 10 y no 1: medido contra el panel el 2026-10-18, los otros doce
    # pares coincidían en un dólar implícito de ~1616 y YPF daba ~162, o sea
    # exactamente diez veces menos. Es el diagnóstico de `merval/ccl.py`
    # haciendo su trabajo; queda sin verificar contra el programa del ADR.
    MervalStock("YPFD.BA", "YPF", SECTOR_ENERGIA, "YPF", 10),
    MervalStock("PAMP.BA", "Pampa Energía", SECTOR_ENERGIA, "PAM", 25),
    MervalStock("BMA.BA", "Banco Macro", SECTOR_BANCOS, "BMA", 10),
    MervalStock("BBAR.BA", "BBVA Argentina", SECTOR_BANCOS, "BBAR", 3),
    MervalStock("SUPV.BA", "Grupo Supervielle", SECTOR_BANCOS, "SUPV", 5),
    MervalStock("TGSU2.BA", "Transportadora de Gas del Sur", SECTOR_ENERGIA, "TGS", 5),
    MervalStock("CEPU.BA", "Central Puerto", SECTOR_ENERGIA, "CEPU", 10),
    MervalStock("EDN.BA", "Edenor", SECTOR_ENERGIA, "EDN", 20),
    MervalStock("LOMA.BA", "Loma Negra", SECTOR_MATERIALES, "LOMA", 5),
    MervalStock("TECO2.BA", "Telecom Argentina", SECTOR_TELECOM, "TEO", 5),
    MervalStock("CRES.BA", "Cresud", SECTOR_INMOBILIARIO, "CRESY", 10),
    MervalStock("IRSA.BA", "IRSA", SECTOR_INMOBILIARIO, "IRS", 10),
    # Sin ADR: cotizan solo en Buenos Aires. Se miden en dólares con el CCL
    # del panel, que es justamente para lo que sirve tenerlo.
    MervalStock("ALUA.BA", "Aluar", SECTOR_MATERIALES),
    MervalStock("TXAR.BA", "Ternium Argentina", SECTOR_MATERIALES),
    MervalStock("TRAN.BA", "Transener", SECTOR_ENERGIA),
    MervalStock("TGNO4.BA", "Transportadora de Gas del Norte", SECTOR_ENERGIA),
    MervalStock("METR.BA", "MetroGAS", SECTOR_ENERGIA),
    MervalStock("BYMA.BA", "Bolsas y Mercados Argentinos", SECTOR_FINANCIERO),
    MervalStock("VALO.BA", "Grupo Financiero Valores", SECTOR_FINANCIERO),
    MervalStock("COME.BA", "Sociedad Comercial del Plata", SECTOR_CONSUMO),
    MervalStock("MIRG.BA", "Mirgor", SECTOR_CONSUMO),
    MervalStock("CVH.BA", "Cablevisión Holding", SECTOR_TELECOM),
)


def local_tickers() -> tuple[str, ...]:
    """Tickers locales del panel, en el orden en que se muestran."""
    return tuple(a.ticker for a in MERVAL_UNIVERSE)


def adr_pairs() -> tuple[MervalStock, ...]:
    """Las acciones que tienen ADR: las únicas que aportan al CCL implícito."""
    return tuple(a for a in MERVAL_UNIVERSE if a.tiene_adr)


def adr_tickers() -> tuple[str, ...]:
    return tuple(a.adr for a in adr_pairs())


def stock_for(ticker: str) -> MervalStock | None:
    """Ficha de un ticker local, o None si no está en el panel."""
    objetivo = (ticker or "").strip().upper()
    for activo in MERVAL_UNIVERSE:
        if activo.ticker.upper() == objetivo:
            return activo
    return None
