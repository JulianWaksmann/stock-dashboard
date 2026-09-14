"""
Tests del armado del cuadro de ONs (`bonds/panel.py`).

Es la función que junta precios, condiciones de emisión y métricas: todo lo que
el usuario ve en la pestaña pasa por acá. Los tests le pasan precios y catálogo
fijos (sin red) y verifican el contrato de la tabla resultante, sobre todo el
comportamiento ante datos faltantes, que es el caso normal y no el excepcional:
siempre va a haber ONs cotizando fuera del catálogo.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from bonds.catalog import BondTerms
from bonds.panel import build_bonds_panel, interpolate_treasury_yield
from constants import (
    BOND_SETTLEMENT_CABLE,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SETTLEMENT_UNKNOWN,
    BOND_SIGNAL_NO_DATA,
)

SETTLEMENT = date(2025, 1, 15)

# Los tickers de prueba terminan en D (dólar MEP) salvo que el test diga otra
# cosa: la última letra decide la moneda del precio, y con ella si el flujo en
# dólares del bono se puede descontar contra ese precio.


def make_terms(ticker: str, **overrides) -> BondTerms:
    params = dict(
        ticker=ticker,
        issuer=f"Emisor {ticker}",
        sector="Energía",
        currency="USD",
        law="NY",
        coupon_rate=10.0,
        frequency=2,
        issue_date=date(2020, 1, 15),
        maturity=date(2030, 1, 15),
        amortizations=(),
        min_denomination=1000.0,
        rating="AAA",
        verified=True,
        notes="",
    )
    params.update(overrides)
    return BondTerms(**params)


def make_prices(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def quote(ticker: str, price=100.0, bid=99.5, ask=100.5, **extra) -> dict:
    row = {
        "Ticker": ticker,
        "Precio": price,
        "Punta Compra": bid,
        "Punta Venta": ask,
        "Var. (%)": 0.5,
        "Volumen": 1_000_000.0,
        "Operaciones": 50.0,
    }
    row.update(extra)
    return row


class TestPanelVacio:
    def test_sin_precios_devuelve_un_dataframe_vacio(self):
        assert build_bonds_panel(pd.DataFrame(), {}, SETTLEMENT).empty


class TestCruceDePreciosYCatalogo:
    def test_calcula_las_metricas_de_una_on_del_catalogo(self):
        panel = build_bonds_panel(make_prices(quote("TSTAD")), {"TSTAD": make_terms("TSTAD")}, SETTLEMENT)
        row = panel.iloc[0]
        assert bool(row["En Catálogo"]) is True
        assert row["Emisor"] == "Emisor TSTAD"
        assert row["TIR (%)"] == pytest.approx(10.25, abs=0.05)
        assert row["Duration Mod."] > 0
        assert row["Paridad (%)"] == pytest.approx(100.0)

    def test_una_on_fuera_del_catalogo_conserva_precio_pero_no_tiene_tir(self):
        panel = build_bonds_panel(make_prices(quote("RARAD")), {}, SETTLEMENT)
        row = panel.iloc[0]
        assert bool(row["En Catálogo"]) is False
        assert row["Precio"] == pytest.approx(100.0)
        assert row["Spread (%)"] == pytest.approx(1.0, abs=0.01)
        assert np.isnan(row["TIR (%)"])
        assert row["Atractivo"] == BOND_SIGNAL_NO_DATA

    def test_no_se_pierde_ninguna_especie_que_cotiza(self):
        prices = make_prices(quote("TSTAD"), quote("RARAD"), quote("TSTBD"))
        panel = build_bonds_panel(prices, {"TSTAD": make_terms("TSTAD")}, SETTLEMENT)
        assert set(panel["Ticker"]) == {"TSTAD", "RARAD", "TSTBD"}

    def test_un_precio_invalido_no_produce_metricas(self):
        prices = make_prices(quote("TSTAD", price=np.nan), quote("TSTBD", price=0.0))
        panel = build_bonds_panel(
            prices, {"TSTAD": make_terms("TSTAD"), "TSTBD": make_terms("TSTBD")}, SETTLEMENT
        )
        assert panel["TIR (%)"].isna().all()

    def test_las_columnas_numericas_no_quedan_como_objeto(self):
        # `bond_math` usa None para "no calculable" y pandas usa NaN: si se
        # mezclan, la columna deja de ser numérica y rompe el formato y el
        # ordenamiento de la tabla.
        prices = make_prices(quote("TSTAD"), quote("RARAD"))
        panel = build_bonds_panel(prices, {"TSTAD": make_terms("TSTAD")}, SETTLEMENT)
        for column in ("TIR (%)", "Duration Mod.", "Paridad (%)", "Spread (%)", "Convexidad"):
            assert pd.api.types.is_numeric_dtype(panel[column]), column


class TestSpreadDePuntas:
    def test_calcula_el_spread_sobre_el_punto_medio(self):
        panel = build_bonds_panel(make_prices(quote("TSTAD", bid=99.0, ask=101.0)), {}, SETTLEMENT)
        assert panel.iloc[0]["Spread (%)"] == pytest.approx(2.0)

    @pytest.mark.parametrize(
        "bid,ask",
        [
            (np.nan, 100.5),   # sin punta compradora
            (99.5, np.nan),    # sin punta vendedora
            (0.0, 100.5),      # punta en cero
            (101.0, 100.0),    # puntas cruzadas (dato corrupto)
        ],
    )
    def test_sin_dos_puntas_validas_no_hay_spread(self, bid, ask):
        panel = build_bonds_panel(make_prices(quote("TSTAD", bid=bid, ask=ask)), {}, SETTLEMENT)
        assert np.isnan(panel.iloc[0]["Spread (%)"])


class TestMedianaYOrden:
    def test_ordena_de_mayor_a_menor_tir(self):
        prices = make_prices(quote("CARAD", price=120.0), quote("BARAD", price=80.0))
        catalog = {"CARAD": make_terms("CARAD"), "BARAD": make_terms("BARAD")}
        panel = build_bonds_panel(prices, catalog, SETTLEMENT)
        assert list(panel["Ticker"]) == ["BARAD", "CARAD"]

    def test_las_ons_sin_tir_quedan_al_final(self):
        prices = make_prices(quote("RARAD"), quote("TSTAD"))
        panel = build_bonds_panel(prices, {"TSTAD": make_terms("TSTAD")}, SETTLEMENT)
        assert list(panel["Ticker"]) == ["TSTAD", "RARAD"]

    def test_expone_la_mediana_de_tir_del_panel(self):
        prices = make_prices(quote("TSTAD", price=90.0), quote("TSTBD", price=110.0))
        catalog = {"TSTAD": make_terms("TSTAD"), "TSTBD": make_terms("TSTBD")}
        panel = build_bonds_panel(prices, catalog, SETTLEMENT)
        assert panel.attrs["median_ytm_pct"] == pytest.approx(panel["TIR (%)"].median())


class TestConvencionDePrecio:
    def test_precio_limpio_rinde_menos_que_el_mismo_precio_sucio(self):
        prices = make_prices(quote("TSTAD", price=100.0))
        catalog = {"TSTAD": make_terms("TSTAD")}
        settlement = date(2025, 4, 15)  # media rueda de cupón devengada
        sucio = build_bonds_panel(prices, catalog, settlement, price_is_dirty=True)
        limpio = build_bonds_panel(prices, catalog, settlement, price_is_dirty=False)
        assert limpio.iloc[0]["TIR (%)"] < sucio.iloc[0]["TIR (%)"]


class TestSpreadContraElTesoro:
    CURVE = {0.25: 4.0, 5.0: 4.5, 10.0: 4.8, 30.0: 5.0}

    def test_mide_el_spread_contra_el_tramo_de_duration_equivalente(self):
        panel = build_bonds_panel(
            make_prices(quote("TSTAD", price=100.0)),
            {"TSTAD": make_terms("TSTAD")},
            SETTLEMENT,
            treasury_curve=self.CURVE,
        )
        row = panel.iloc[0]
        benchmark = interpolate_treasury_yield(self.CURVE, row["Duration Mod."])
        assert row["Spread vs UST (pb)"] == pytest.approx((row["TIR (%)"] - benchmark) * 100.0)

    def test_sin_curva_no_se_informa_spread(self):
        panel = build_bonds_panel(
            make_prices(quote("TSTAD")), {"TSTAD": make_terms("TSTAD")}, SETTLEMENT, treasury_curve={}
        )
        assert np.isnan(panel.iloc[0]["Spread vs UST (pb)"])


class TestInterpolacionDeLaCurva:
    CURVE = {0.25: 4.0, 5.0: 4.5, 10.0: 4.8, 30.0: 5.0}

    def test_interpola_linealmente_entre_dos_tramos(self):
        assert interpolate_treasury_yield(self.CURVE, 7.5) == pytest.approx(4.65)

    def test_devuelve_el_valor_exacto_en_un_tramo_publicado(self):
        assert interpolate_treasury_yield(self.CURVE, 5.0) == pytest.approx(4.5)

    def test_por_debajo_del_tramo_mas_corto_usa_el_tramo_mas_corto(self):
        assert interpolate_treasury_yield(self.CURVE, 0.05) == pytest.approx(4.0)

    def test_por_encima_del_tramo_mas_largo_usa_el_tramo_mas_largo(self):
        # Extender, no extrapolar: una curva extrapolada más allá de 30 años
        # devuelve tasas que no existen en ningún mercado.
        assert interpolate_treasury_yield(self.CURVE, 50.0) == pytest.approx(5.0)

    @pytest.mark.parametrize("tenor", [None, float("nan")])
    def test_sin_plazo_no_hay_interpolacion(self, tenor):
        assert interpolate_treasury_yield(self.CURVE, tenor) is None

    def test_sin_curva_no_hay_interpolacion(self):
        assert interpolate_treasury_yield({}, 5.0) is None


class TestMonedaDeLaEspecie:
    """
    Una misma ON cotiza en pesos (especie O) y en dólares (D y C). Descontar un
    flujo en dólares contra el precio en pesos devuelve una TIR sin sentido
    económico, así que el panel exige que las monedas coincidan.
    """

    def test_la_especie_en_pesos_de_un_bono_en_dolares_no_tiene_tir(self):
        panel = build_bonds_panel(
            make_prices(quote("TSTAO", price=152_000.0)), {"TSTAO": make_terms("TSTAO")}, SETTLEMENT
        )
        row = panel.iloc[0]
        assert bool(row["En Catálogo"]) is True
        assert np.isnan(row["TIR (%)"])
        assert row["Moneda Precio"] == "ARS"

    def test_la_especie_en_dolares_del_mismo_bono_si_tiene_tir(self):
        panel = build_bonds_panel(
            make_prices(quote("TSTAD", price=100.0)), {"TSTAO": make_terms("TSTAO")}, SETTLEMENT
        )
        row = panel.iloc[0]
        assert row["TIR (%)"] == pytest.approx(10.25, abs=0.05)
        assert row["Moneda Precio"] == "USD"

    def test_una_fila_del_catalogo_cubre_las_tres_especies_del_bono(self):
        prices = make_prices(quote("TSTAO"), quote("TSTAD"), quote("TSTAC"))
        panel = build_bonds_panel(prices, {"TSTAO": make_terms("TSTAO")}, SETTLEMENT)
        assert panel["En Catálogo"].all()
        assert set(panel["Emisor"]) == {"Emisor TSTAO"}

    def test_informa_la_especie_de_liquidacion_de_cada_ticker(self):
        prices = make_prices(quote("TSTAO"), quote("TSTAD"), quote("TSTAC"))
        panel = build_bonds_panel(prices, {}, SETTLEMENT)
        by_ticker = dict(zip(panel["Ticker"], panel["Liquidación"], strict=True))
        assert by_ticker["TSTAO"] == BOND_SETTLEMENT_PESOS
        assert by_ticker["TSTAD"] == BOND_SETTLEMENT_MEP
        assert by_ticker["TSTAC"] == BOND_SETTLEMENT_CABLE

    def test_un_ticker_que_no_sigue_la_convencion_queda_sin_especie(self):
        panel = build_bonds_panel(make_prices(quote("RARO")), {}, SETTLEMENT)
        assert panel.iloc[0]["Liquidación"] == BOND_SETTLEMENT_UNKNOWN
        assert np.isnan(panel.iloc[0]["TIR (%)"])
