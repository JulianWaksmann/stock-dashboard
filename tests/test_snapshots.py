"""
Tests del registro diario (`snapshots.py`).

Lo que hay que fijar es la regla que vuelve comparables dos días: **una foto
por día, la primera**. Si cada recarga sobreescribiera el archivo, el "cambio
desde ayer" dependería de a qué hora miró cada uno. Y que la comparación sea
contra la última foto anterior, no contra el día de ayer: si el tablero no se
abrió el viernes, el lunes se compara contra el jueves.

Todo corre contra un directorio temporal: la suite no escribe en `data/`.
"""

from datetime import date

import pandas as pd
import pytest

from snapshots import (
    available_snapshots,
    compare_snapshots,
    load_snapshot,
    previous_snapshot,
    record_and_compare,
    save_snapshot,
)

HOY = date(2026, 3, 10)
AYER = date(2026, 3, 9)
VIERNES = date(2026, 3, 6)


def panel(semaforos, precios=None, tickers=None):
    tickers = tickers or [f"T{i}" for i in range(len(semaforos))]
    precios = precios or [100.0] * len(semaforos)
    return pd.DataFrame({
        "Ticker": tickers,
        "Semáforo": semaforos,
        "Precio Actual": precios,
        "RSI_VAL": [50.0] * len(semaforos),
        "Columna Ignorada": ["x"] * len(semaforos),
    })


@pytest.fixture
def carpeta(tmp_path):
    return tmp_path / "snapshots"


class TestGrabado:
    def test_graba_la_foto_del_dia(self, carpeta):
        destino = save_snapshot(panel(["🟡", "🟢"]), "acciones", fecha=HOY, directorio=carpeta)

        assert destino is not None and destino.exists()
        assert available_snapshots("acciones", carpeta) == [HOY]

    def test_no_sobreescribe_la_foto_del_dia(self, carpeta):
        """La foto del día es la de la primera consulta, no la de la última."""
        save_snapshot(panel(["🟡"], precios=[100.0]), "acciones", fecha=HOY, directorio=carpeta)
        segunda = save_snapshot(panel(["🟢"], precios=[200.0]), "acciones", fecha=HOY, directorio=carpeta)

        assert segunda is None
        guardado = load_snapshot("acciones", HOY, carpeta)
        assert guardado["Semáforo"].iloc[0] == "🟡"

    def test_guarda_solo_las_columnas_del_registro(self, carpeta):
        save_snapshot(panel(["🟡"]), "acciones", fecha=HOY, directorio=carpeta)
        guardado = load_snapshot("acciones", HOY, carpeta)

        assert "Columna Ignorada" not in guardado.columns
        assert {"Ticker", "Semáforo", "Precio Actual", "RSI_VAL"} <= set(guardado.columns)

    def test_cada_motor_tiene_su_carpeta(self, carpeta):
        save_snapshot(panel(["🟡"]), "acciones", fecha=HOY, directorio=carpeta)
        save_snapshot(panel(["🟡"]), "cripto", fecha=HOY, directorio=carpeta)

        assert available_snapshots("acciones", carpeta) == [HOY]
        assert available_snapshots("cripto", carpeta) == [HOY]
        assert available_snapshots("bonos", carpeta) == []

    def test_un_panel_vacio_o_sin_ticker_no_graba_nada(self, carpeta):
        assert save_snapshot(pd.DataFrame(), "acciones", fecha=HOY, directorio=carpeta) is None
        assert save_snapshot(
            pd.DataFrame({"Otra": [1]}), "acciones", fecha=HOY, directorio=carpeta
        ) is None

    def test_leer_una_fecha_sin_foto_devuelve_vacio(self, carpeta):
        assert load_snapshot("acciones", HOY, carpeta).empty


class TestFotoAnterior:
    def test_toma_la_ultima_anterior_y_no_la_de_ayer(self, carpeta):
        """Sin tablero abierto el viernes, el lunes compara contra el jueves."""
        save_snapshot(panel(["🟡"]), "acciones", fecha=VIERNES, directorio=carpeta)
        save_snapshot(panel(["🟢"]), "acciones", fecha=HOY, directorio=carpeta)

        fecha, df = previous_snapshot("acciones", fecha=HOY, directorio=carpeta)
        assert fecha == VIERNES
        assert df["Semáforo"].iloc[0] == "🟡"

    def test_el_primer_dia_no_hay_anterior(self, carpeta):
        save_snapshot(panel(["🟡"]), "acciones", fecha=HOY, directorio=carpeta)
        assert previous_snapshot("acciones", fecha=HOY, directorio=carpeta) is None

    def test_los_archivos_con_nombre_raro_se_ignoran(self, carpeta):
        save_snapshot(panel(["🟡"]), "acciones", fecha=AYER, directorio=carpeta)
        (carpeta / "acciones" / "notas.csv").write_text("algo")

        assert available_snapshots("acciones", carpeta) == [AYER]


class TestComparacion:
    def test_detecta_los_cambios_de_semaforo(self):
        antes = panel(["🟡", "🟢", "🟡"])
        ahora = panel(["🟢", "🟢", "🟡"])

        cambios = compare_snapshots(antes, ahora, fecha_anterior=AYER)

        assert len(cambios.señales) == 1
        assert cambios.señales.iloc[0]["Ticker"] == "T0"
        assert cambios.señales.iloc[0]["Antes"] == "🟡"
        assert cambios.señales.iloc[0]["Ahora"] == "🟢"
        assert cambios.hay_cambios
        assert cambios.fecha_anterior == AYER

    def test_detecta_altas_y_bajas_del_panel(self):
        antes = panel(["🟡", "🟡"], tickers=["A", "B"])
        ahora = panel(["🟡", "🟡"], tickers=["B", "C"])

        cambios = compare_snapshots(antes, ahora)

        assert cambios.nuevos == ("C",)
        assert cambios.salidos == ("A",)

    def test_mide_la_variacion_de_precio_y_ordena_por_magnitud(self):
        antes = panel(["🟡", "🟡", "🟡"], precios=[100.0, 100.0, 100.0])
        ahora = panel(["🟡", "🟡", "🟡"], precios=[101.0, 80.0, 105.0])

        movimientos = compare_snapshots(antes, ahora).movimientos

        assert list(movimientos["Ticker"]) == ["T1", "T2", "T0"]
        assert movimientos.iloc[0]["Var. (%)"] == pytest.approx(-20.0)

    def test_un_panel_sin_cambios_no_reporta_ninguno(self):
        igual = panel(["🟡", "🟢"])
        cambios = compare_snapshots(igual, igual)

        assert not cambios.hay_cambios
        assert cambios.señales.empty

    def test_la_columna_de_señal_se_puede_cambiar(self):
        """El panel de ONs llama "Atractivo" a lo que acciones llama "Semáforo"."""
        antes = pd.DataFrame({"Ticker": ["ON1"], "Atractivo": ["⚪ NEUTRAL"]})
        ahora = pd.DataFrame({"Ticker": ["ON1"], "Atractivo": ["🟢 ATRACTIVO"]})

        cambios = compare_snapshots(antes, ahora, columna_senal="Atractivo")
        assert len(cambios.señales) == 1

    def test_sin_foto_anterior_no_hay_comparacion(self):
        cambios = compare_snapshots(pd.DataFrame(), panel(["🟡"]))
        assert not cambios.hay_cambios


class TestGrabarYComparar:
    def test_el_primer_dia_no_se_compara_contra_si_mismo(self, carpeta):
        cambios = record_and_compare(panel(["🟡"]), "acciones", fecha=HOY, directorio=carpeta)

        assert not cambios.hay_cambios
        assert cambios.fecha_anterior is None
        assert available_snapshots("acciones", carpeta) == [HOY]

    def test_el_segundo_dia_compara_contra_el_primero(self, carpeta):
        record_and_compare(panel(["🟡"]), "acciones", fecha=AYER, directorio=carpeta)
        cambios = record_and_compare(panel(["🟢"]), "acciones", fecha=HOY, directorio=carpeta)

        assert cambios.fecha_anterior == AYER
        assert len(cambios.señales) == 1
        assert available_snapshots("acciones", carpeta) == [AYER, HOY]
