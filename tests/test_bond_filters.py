"""
Tests de los filtros del panel de ONs (`bonds.panel.apply_bond_filters`).

El orden en que se aplican los filtros cambia el resultado, y de forma nada
obvia: rankear por volumen antes o después de elegir la moneda da listas
distintas porque el volumen de cada especie está en su propia moneda. Por eso
el filtrado es código puro con tests, y no lógica suelta dentro del componente
de Streamlit.
"""

import numpy as np
import pandas as pd

from bonds.panel import apply_bond_filters
from constants import (
    BOND_FILTER_LAW_ALL,
    BOND_FILTER_LAW_NY,
    BOND_FILTER_LIQUIDITY_ALL,
    BOND_FILTER_LIQUIDITY_TOP_20,
    BOND_FILTER_LIQUIDITY_TRADED,
    BOND_FILTER_SETTLEMENT_ALL,
    BOND_FILTER_SETTLEMENT_MEP,
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SIGNAL_ALL,
    BOND_FILTER_SIGNAL_VERY_ATTRACTIVE,
    BOND_SETTLEMENT_CABLE,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SIGNAL_NEUTRAL,
    BOND_SIGNAL_VERY_ATTRACTIVE,
)

_ESPECIES = {
    "O": (BOND_SETTLEMENT_PESOS, "ARS"),
    "D": (BOND_SETTLEMENT_MEP, "USD"),
    "C": (BOND_SETTLEMENT_CABLE, "USD"),
}


def fila(ticker: str, volumen: float, tir: float = 9.0, puntaje: float = 50.0, **overrides) -> dict:
    liquidacion, moneda = _ESPECIES[ticker[-1]]
    fila_base = {
        "Ticker": ticker,
        "Puntaje": puntaje,
        "Liquidación": liquidacion,
        "Moneda Precio": moneda,
        "Volumen": volumen,
        "TIR (%)": tir,
        "Duration Mod.": 3.0,
        "Atractivo": BOND_SIGNAL_NEUTRAL,
        "Ley": "NY",
    }
    fila_base.update(overrides)
    return fila_base


def filtrar(rows, **overrides) -> pd.DataFrame:
    params = dict(
        settlement_filter=BOND_FILTER_SETTLEMENT_ALL,
        liquidity_filter=BOND_FILTER_LIQUIDITY_ALL,
        signal_filter=BOND_FILTER_SIGNAL_ALL,
        law_filter=BOND_FILTER_LAW_ALL,
    )
    params.update(overrides)
    return apply_bond_filters(pd.DataFrame(rows), **params)


class TestOrdenDeAplicacion:
    def test_el_ranking_por_volumen_corre_dentro_de_la_moneda_elegida(self):
        # El volumen en pesos es numéricamente enorme frente al de la especie
        # en dólares: si el ranking corriera antes del filtro de moneda, el
        # top se llenaría de filas en pesos y después quedarían descartadas.
        rows = [fila("AAAAO", 500_000_000.0), fila("BBBBO", 400_000_000.0), fila("CCCCD", 900.0)]
        resultado = filtrar(
            rows,
            settlement_filter=BOND_FILTER_SETTLEMENT_USD,
            liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20,
        )
        assert list(resultado["Ticker"]) == ["CCCCD"]

    def test_el_top_n_no_depende_de_los_filtros_posteriores(self):
        # Filtrar por ley después no puede cambiar quiénes eran las más
        # operadas: el ranking se arma contra todo el universo de la moneda.
        rows = [
            fila("AAAAD", 900.0, ley="ARG") | {"Ley": "ARG"},
            fila("BBBBD", 800.0),
            fila("CCCCD", 700.0),
        ]
        sin_ley = filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20)
        con_ley = filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20, law_filter=BOND_FILTER_LAW_NY)
        assert set(con_ley["Ticker"]) <= set(sin_ley["Ticker"])
        assert set(con_ley["Ticker"]) == {"BBBBD", "CCCCD"}


class TestUnaFilaPorBono:
    def test_pidiendo_las_dos_especies_en_dolares_no_se_duplica_el_bono(self):
        rows = [fila("YMCJD", 900.0), fila("YMCJC", 100.0), fila("PNDCD", 500.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_USD)
        assert sorted(resultado["Ticker"]) == ["PNDCD", "YMCJD"]

    def test_se_conserva_la_especie_mas_operada(self):
        rows = [fila("YMCJD", 100.0), fila("YMCJC", 900.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_USD)
        assert list(resultado["Ticker"]) == ["YMCJC"]

    def test_pidiendo_una_especie_concreta_no_se_deduplica_nada(self):
        rows = [fila("YMCJD", 900.0), fila("PNDCD", 500.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_MEP)
        assert len(resultado) == 2

    def test_deduplicar_no_deja_afuera_bonos_distintos(self):
        rows = [fila("YMCJD", 900.0), fila("YMCID", 800.0), fila("YMCQD", 700.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_USD)
        assert len(resultado) == 3


class TestLiquidez:
    def test_descarta_las_que_no_operaron(self):
        rows = [fila("AAAAD", 900.0), fila("BBBBD", 0.0)]
        resultado = filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TRADED)
        assert list(resultado["Ticker"]) == ["AAAAD"]

    def test_sin_dato_de_volumen_la_especie_no_se_descarta(self):
        # Volumen desconocido no es volumen cero: si el feed dejara de
        # publicar la columna, el filtro vaciaría el panel entero.
        rows = [fila("AAAAD", np.nan)]
        assert len(filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TRADED)) == 1

    def test_la_opcion_todas_no_descarta_las_que_no_operaron(self):
        rows = [fila("AAAAD", 900.0), fila("BBBBD", 0.0)]
        assert len(filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_ALL)) == 2

    def test_el_top_n_corta_por_volumen(self):
        rows = [fila(f"{chr(65 + i) * 4}D", float(i)) for i in range(25)]
        resultado = filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20)
        assert len(resultado) == 20
        assert resultado["Volumen"].min() == 5.0


class TestRecortesSimples:
    def test_filtra_por_atractivo(self):
        rows = [
            fila("AAAAD", 900.0, Atractivo=BOND_SIGNAL_VERY_ATTRACTIVE),
            fila("BBBBD", 800.0),
        ]
        resultado = filtrar(rows, signal_filter=BOND_FILTER_SIGNAL_VERY_ATTRACTIVE)
        assert list(resultado["Ticker"]) == ["AAAAD"]

    def test_la_duration_desconocida_no_se_descarta_por_el_tope(self):
        rows = [fila("AAAAD", 900.0, **{"Duration Mod.": np.nan}), fila("BBBBD", 800.0)]
        resultado = filtrar(rows, max_duration=1.0)
        assert list(resultado["Ticker"]) == ["AAAAD"]

    def test_puede_ocultar_las_que_no_tienen_tir(self):
        rows = [fila("AAAAD", 900.0), fila("BBBBD", 800.0, tir=np.nan)]
        assert list(filtrar(rows, only_with_yield=True)["Ticker"]) == ["AAAAD"]

    def test_devuelve_ordenado_por_puntaje_descendente(self):
        rows = [fila("AAAAD", 900.0, puntaje=30.0), fila("BBBBD", 800.0, puntaje=80.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_USD)
        assert list(resultado["Ticker"]) == ["BBBBD", "AAAAD"]

    def test_a_igual_puntaje_desempata_por_tir(self):
        rows = [fila("AAAAD", 900.0, puntaje=60.0, tir=5.0), fila("BBBBD", 800.0, puntaje=60.0, tir=12.0)]
        resultado = filtrar(rows, settlement_filter=BOND_FILTER_SETTLEMENT_USD)
        assert list(resultado["Ticker"]) == ["BBBBD", "AAAAD"]

    def test_un_panel_vacio_no_rompe(self):
        vacio = pd.DataFrame(columns=["Ticker", "Puntaje", "Liquidación", "Moneda Precio", "Volumen", "TIR (%)", "Duration Mod.", "Atractivo", "Ley"])
        assert apply_bond_filters(
            vacio,
            settlement_filter=BOND_FILTER_SETTLEMENT_USD,
            liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20,
            signal_filter=BOND_FILTER_SIGNAL_ALL,
            law_filter=BOND_FILTER_LAW_ALL,
        ).empty
