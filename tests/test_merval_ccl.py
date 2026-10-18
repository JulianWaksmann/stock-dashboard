"""
Tests del dólar implícito del panel argentino (`merval/ccl.py`).

Todo el panel cuelga de este número: cada precio que se muestra es un precio en
pesos dividido por él. Lo que importa fijar es que un solo par con el ratio mal
cargado **no** pueda mover el resultado —para eso se usa la mediana— y que la
conversión a dólares no invente tipos de cambio en los días en que una de las
dos puntas no operó.
"""

import numpy as np
import pandas as pd
import pytest

from constants import MERVAL_CCL_MAX_STALE_BARS
from merval.catalog import MervalStock
from merval.ccl import implied_ccl_series, to_usd

CCL = 1000.0
FECHAS = pd.bdate_range("2026-01-05", periods=10)


def _par(nombre, adr, ratio, precio_adr=10.0, ccl=CCL, fechas=FECHAS):
    """Un par local/ADR coherente con el CCL pedido."""
    activo = MervalStock(f"{nombre}.BA", nombre, "Prueba", adr, ratio)
    adr_df = pd.DataFrame({"Close": [precio_adr] * len(fechas)}, index=fechas)
    local_df = pd.DataFrame(
        {"Close": [precio_adr * ccl / ratio] * len(fechas)}, index=fechas
    )
    return activo, local_df, adr_df


def _armar(pares):
    activos, locales, adrs = [], {}, {}
    for activo, local_df, adr_df in pares:
        activos.append(activo)
        locales[activo.ticker] = local_df
        adrs[activo.adr] = adr_df
    return locales, adrs, tuple(activos)


class TestSerieImplicita:
    def test_recupera_el_tipo_de_cambio_de_los_pares(self):
        locales, adrs, activos = _armar([
            _par("UNO", "ONE", 10),
            _par("DOS", "TWO", 5, precio_adr=25.0),
            _par("TRES", "THREE", 1, precio_adr=40.0),
        ])
        ccl = implied_ccl_series(locales, adrs, activos)

        assert ccl.disponible
        assert ccl.ultimo == pytest.approx(CCL)
        assert len(ccl.pares_usados) == 3
        assert ccl.dispersion_pct == pytest.approx(0.0)

    def test_un_ratio_mal_cargado_no_mueve_la_mediana(self):
        """
        Es la propiedad que hace tolerable una tabla de ratios sin verificar:
        el par equivocado queda como valor extremo.
        """
        bueno_1 = _par("UNO", "ONE", 10)
        bueno_2 = _par("DOS", "TWO", 5, precio_adr=25.0)
        bueno_3 = _par("TRES", "THREE", 20, precio_adr=5.0)
        # Mismo par que UNO, pero con el ratio diez veces más grande.
        activo, local_df, adr_df = _par("MALO", "BAD", 10)
        malo = (
            MervalStock("MALO.BA", "MALO", "Prueba", "BAD", 100),
            local_df,
            adr_df,
        )

        locales, adrs, activos = _armar([bueno_1, bueno_2, bueno_3, malo])
        ccl = implied_ccl_series(locales, adrs, activos)

        assert ccl.ultimo == pytest.approx(CCL)

    def test_el_par_equivocado_queda_marcado_con_su_ratio_sugerido(self):
        locales, adrs, activos = _armar([
            _par("UNO", "ONE", 10),
            _par("DOS", "TWO", 5, precio_adr=25.0),
            _par("TRES", "THREE", 20, precio_adr=5.0),
            (
                MervalStock("MALO.BA", "MALO", "Prueba", "BAD", 100),
                _par("MALO", "BAD", 10)[1],
                _par("MALO", "BAD", 10)[2],
            ),
        ])
        detalle = implied_ccl_series(locales, adrs, activos).detalle.set_index("Ticker")

        assert bool(detalle.loc["MALO.BA", "Sospechoso"])
        assert detalle.loc["MALO.BA", "Ratio sugerido"] == 10
        assert not bool(detalle.loc["UNO.BA", "Sospechoso"])
        # Al par correcto no se le sugiere cambiar nada.
        assert pd.isna(detalle.loc["UNO.BA", "Ratio sugerido"])

    def test_solo_usa_las_fechas_en_que_operaron_las_dos_puntas(self):
        """
        Un precio local de feriado norteamericano contra el ADR del día
        anterior daría un salto de tipo de cambio que no existió.
        """
        activo, local_df, adr_df = _par("UNO", "ONE", 10)
        adr_recortado = adr_df.iloc[:5]

        ccl = implied_ccl_series({activo.ticker: local_df}, {activo.adr: adr_recortado}, (activo,))
        assert len(ccl.serie.dropna()) == 5

    def test_sin_pares_utilizables_no_hay_ccl(self):
        activo, local_df, adr_df = _par("UNO", "ONE", 10)

        assert not implied_ccl_series({}, {}, ()).disponible
        assert not implied_ccl_series({activo.ticker: local_df}, {}, (activo,)).disponible
        assert not implied_ccl_series(
            {activo.ticker: pd.DataFrame()}, {activo.adr: adr_df}, (activo,)
        ).disponible

    def test_los_precios_no_positivos_se_descartan(self):
        activo, local_df, adr_df = _par("UNO", "ONE", 10)
        adr_df = adr_df.copy()
        adr_df.iloc[0] = 0.0

        ccl = implied_ccl_series({activo.ticker: local_df}, {activo.adr: adr_df}, (activo,))
        assert len(ccl.serie.dropna()) == len(FECHAS) - 1


class TestConversionADolares:
    @staticmethod
    def _ohlcv(fechas=FECHAS, precio=2000.0):
        return pd.DataFrame(
            {
                "Open": precio,
                "High": precio * 1.02,
                "Low": precio * 0.98,
                "Close": precio,
                "Volume": 1_000.0,
            },
            index=fechas,
        )

    def test_divide_los_precios_y_deja_el_volumen(self):
        """
        El volumen está en cantidad de acciones, que es lo que necesita el OBV:
        convertirlo cambiaría la lectura de flujo sin que nada lo avise.
        """
        ccl = pd.Series(CCL, index=FECHAS)
        en_dolares = to_usd(self._ohlcv(), ccl)

        assert en_dolares["Close"].iloc[0] == pytest.approx(2.0)
        assert en_dolares["High"].iloc[0] == pytest.approx(2.04)
        assert en_dolares["Volume"].iloc[0] == pytest.approx(1_000.0)

    def test_puentea_los_dias_sin_ccl_hasta_el_limite(self):
        ccl = pd.Series(CCL, index=FECHAS)
        ccl.iloc[3:3 + MERVAL_CCL_MAX_STALE_BARS] = np.nan

        en_dolares = to_usd(self._ohlcv(), ccl)
        assert len(en_dolares) == len(FECHAS)

    def test_descarta_las_barras_que_quedan_sin_ccl(self):
        """Una semana sin tipo de cambio no se puentea: sería inventarlo."""
        ccl = pd.Series(CCL, index=FECHAS)
        ccl.iloc[2:] = np.nan

        en_dolares = to_usd(self._ohlcv(), ccl)
        assert len(en_dolares) == 2 + MERVAL_CCL_MAX_STALE_BARS

    def test_un_ccl_que_se_mueve_se_aplica_dia_por_dia(self):
        ccl = pd.Series(np.linspace(1000.0, 2000.0, len(FECHAS)), index=FECHAS)
        en_dolares = to_usd(self._ohlcv(), ccl)

        assert en_dolares["Close"].iloc[0] == pytest.approx(2.0)
        assert en_dolares["Close"].iloc[-1] == pytest.approx(1.0)

    def test_sin_datos_devuelve_vacio(self):
        assert to_usd(pd.DataFrame(), pd.Series(CCL, index=FECHAS)).empty
        assert to_usd(self._ohlcv(), pd.Series(dtype=float)).empty
        assert to_usd(None, None).empty
