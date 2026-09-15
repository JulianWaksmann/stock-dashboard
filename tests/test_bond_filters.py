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
    BOND_SIGNAL_VERY_SHORT,
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


class TestTopNPorMoneda:
    """
    El volumen de la especie en pesos está en pesos y el de la MEP en dólares.
    Rankear las dos juntas compara unidades distintas y ganan las filas en
    pesos por magnitud, no por actividad.
    """

    def _panel_mixto(self):
        rows = [fila(f"P{i:03}O", 1e9 + i) for i in range(30)]
        rows += [fila(f"D{i:03}D", 5e6 + i) for i in range(10)]
        return rows

    def test_mostrando_todas_las_especies_el_top_rankea_dentro_de_cada_moneda(self):
        resultado = filtrar(
            self._panel_mixto(),
            settlement_filter=BOND_FILTER_SETTLEMENT_ALL,
            liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20,
        )
        assert (resultado["Moneda Precio"] == "USD").sum() == 10
        assert (resultado["Moneda Precio"] == "ARS").sum() == 20

    def test_el_tope_se_respeta_aunque_haya_empates(self):
        # `keep="all"` devolvía más filas que las pedidas, que es lo contrario
        # de lo que significa un tope.
        rows = [fila(f"E{i:03}D", 100.0) for i in range(30)]
        resultado = filtrar(rows, liquidity_filter=BOND_FILTER_LIQUIDITY_TOP_20)
        assert len(resultado) == 20


class TestFiltroDeVencimientoCercano:
    """
    Las ONs a semanas del vencimiento se ocultan por defecto: su TIR anualizada
    es un artefacto aritmético, no una medida de rendimiento, y por eso mismo
    ya están excluidas del panel comparable y no reciben puntaje.
    """

    def _panel(self):
        return pd.DataFrame(
            [
                {"Ticker": "LARGAD", "Años al Vto.": 4.0, "Moneda Precio": "USD",
                 "Volumen": 100.0, "TIR (%)": 7.0, "Atractivo": BOND_SIGNAL_NEUTRAL,
                 "Ley": "NY", "Duration Mod.": 3.0, "Liquidación": BOND_SETTLEMENT_MEP},
                {"Ticker": "CORTAD", "Años al Vto.": 0.15, "Moneda Precio": "USD",
                 "Volumen": 100.0, "TIR (%)": 22.0, "Atractivo": BOND_SIGNAL_VERY_SHORT,
                 "Ley": "NY", "Duration Mod.": 0.1, "Liquidación": BOND_SETTLEMENT_MEP},
                {"Ticker": "JUSTAD", "Años al Vto.": 0.25, "Moneda Precio": "USD",
                 "Volumen": 100.0, "TIR (%)": 9.0, "Atractivo": BOND_SIGNAL_NEUTRAL,
                 "Ley": "NY", "Duration Mod.": 0.2, "Liquidación": BOND_SETTLEMENT_MEP},
            ]
        )

    def _filtrar(self, **extra):
        return apply_bond_filters(
            self._panel(),
            settlement_filter=BOND_FILTER_SETTLEMENT_ALL,
            liquidity_filter=BOND_FILTER_LIQUIDITY_ALL,
            signal_filter=BOND_FILTER_SIGNAL_ALL,
            law_filter=BOND_FILTER_LAW_ALL,
            **extra,
        )

    def test_por_defecto_se_ocultan(self):
        assert set(self._filtrar()["Ticker"]) == {"LARGAD", "JUSTAD"}

    def test_el_umbral_es_inclusivo(self):
        # Exactamente 3 meses se muestra: el corte es "menos de", no "hasta".
        assert "JUSTAD" in set(self._filtrar()["Ticker"])

    def test_se_pueden_pedir_explicitamente(self):
        resultado = self._filtrar(include_near_maturity=True)
        assert set(resultado["Ticker"]) == {"LARGAD", "CORTAD", "JUSTAD"}

    def test_una_on_sin_plazo_conocido_no_se_oculta(self):
        # Sin fecha de vencimiento no se sabe si está por vencer. Ocultarla
        # sería castigarla por un dato que falta en la fuente.
        panel = self._panel()
        panel.loc[panel["Ticker"] == "LARGAD", "Años al Vto."] = np.nan
        resultado = apply_bond_filters(
            panel,
            settlement_filter=BOND_FILTER_SETTLEMENT_ALL,
            liquidity_filter=BOND_FILTER_LIQUIDITY_ALL,
            signal_filter=BOND_FILTER_SIGNAL_ALL,
            law_filter=BOND_FILTER_LAW_ALL,
        )
        assert "LARGAD" in set(resultado["Ticker"])
