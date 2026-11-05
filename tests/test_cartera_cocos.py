"""
Tests del lector de movimientos de Cocos (`cartera/cocos.py`) y de cómo se
combina con Balanz (`cartera/lectura.py`).

CSV sintéticos con el mismo formato que el export real (punto y coma, números
con coma decimal y punto de miles, fechas dd-mm-aaaa). El MEP es una serie
fija: el lector no toca la red.
"""

import pandas as pd
import pytest

from cartera.cocos import es_cocos, leer_cocos, mep_en
from cartera.modelo import (
    BROKER_BALANZ,
    BROKER_COCOS,
    MOV_DIVIDENDO,
    MOV_INTERES,
    MOV_VENTA,
    TICKER_CAUCION,
    Cartera,
    ExportInvalido,
    combinar,
    filtrar_broker,
)

ENCABEZADO = "nroTicket;nroComprobante;fechaEjecucion;fechaLiquidacion;tipoOperacion;instrumento;moneda;mercado;cantidad;precio;montoBruto;comision;ddmm;iva;otros;total"

# MEP 1.000 hasta fin de 2025 y 2.000 desde 2026: así se ve qué fecha se usó.
MEP = pd.Series({"2025-01-02": 1000.0, "2026-01-02": 2000.0})


def _fila(ticket, fecha, tipo, instrumento="", cantidad="", monto="", total=None, liq=None, moneda="ARS"):
    total = monto if total is None else total
    return f"{ticket};1;{fecha};{liq or fecha};{tipo};{instrumento};{moneda};BYMA;{cantidad};;{monto};0;0;0;0;{total}"


def _csv(*filas):
    return ("\n".join([ENCABEZADO, *filas]) + "\n").encode("utf-8")


MSFT = "CEDEAR DE MICROSOFT CORP. (MSFT)"


class TestFormato:
    def test_reconoce_el_export_por_el_encabezado(self):
        assert es_cocos(_csv())
        assert not es_cocos(b"PK\x03\x04")

    def test_sin_mep_no_inventa_dolares(self):
        with pytest.raises(ExportInvalido, match="MEP"):
            leer_cocos([_csv(_fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000"))], None)

    def test_una_fecha_en_otro_formato_no_tumba_la_lectura(self):
        x = leer_cocos([_csv(
            _fila(1, "2025/01/02", "Compra", MSFT, "1", "-1.000"),
            _fila(2, "02-01-2025", "Compra", MSFT, "2", "-2.000"),
        )], MEP)
        assert x.lotes_abiertos["cantidad"].tolist() == [2]
        assert x.no_reconocidos.iloc[0]["motivo"] == "sin fecha"

    def test_sin_nada_para_analizar_avisa_en_vez_de_dar_un_informe_vacio(self):
        with pytest.raises(ExportInvalido, match="no tienen compras"):
            leer_cocos([_csv(_fila(1, "02-01-2025", "Orden De Pago", monto="-10"))], MEP)

    def test_csv_en_latin1(self):
        contenido = _csv(_fila(1, "02-01-2025", "Compra", "ACCIÓN ÑANDÚ ESCRIT. (NAN)", "1", "-1.000"))
        x = leer_cocos([contenido.decode().encode("latin-1")], MEP)
        assert x.lotes_abiertos.iloc[0]["descripcion"] == "ACCIÓN ÑANDÚ ESCRIT."

    def test_mep_de_un_dia_sin_dato_usa_el_anterior(self):
        assert mep_en(MEP, "2025-07-15") == 1000
        assert mep_en(MEP, "2026-01-01") == 1000
        assert mep_en(MEP, "2024-12-31") is None


class TestLotes:
    def test_venta_consume_las_compras_mas_viejas_y_usa_el_mep_de_cada_fecha(self):
        x = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000", "-1.010.000"),
            _fila(2, "03-03-2025", "Compra", MSFT, "10", "-2.000.000"),
            _fila(3, "05-01-2026", "Venta", MSFT, "-15", "6.000.000", "5.970.000"),
        )], MEP)
        v = x.operaciones
        assert list(v["movimiento"]) == [MOV_VENTA, MOV_VENTA]
        assert list(v["fecha_compra"]) == ["2025-01-02", "2025-03-03"]
        assert list(v["cantidad"]) == [10, 5]
        # Costo al MEP de la compra (1.000); venta al de la venta (2.000).
        assert v["costo_usd"].tolist() == pytest.approx([1000, 1000])
        assert v["venta_usd"].tolist() == pytest.approx([2000, 1000])
        # Comisión de compra (10.000) al primer lote; la de venta (30.000) por cantidad.
        assert v["gastos_usd"].tolist() == pytest.approx([10 + 10, 5])
        # Lo que no se vendió queda abierto, al costo.
        assert x.lotes_abiertos["cantidad"].tolist() == [5]
        assert x.lotes_abiertos["costo_usd"].tolist() == pytest.approx([1000])

    def test_venta_sin_compra_no_inventa_costo(self):
        x = leer_cocos([_csv(_fila(1, "02-01-2025", "Venta", MSFT, "-3", "300.000"))], MEP)
        assert x.operaciones.empty
        assert "sin una compra" in x.no_reconocidos.iloc[0]["motivo"]

    def test_las_ventas_sin_compra_se_informan_agrupadas_por_activo(self):
        fci = "FCI COCOS RENDIMIENTO CL. A $ ESC (COCORMA)"
        x = leer_cocos([_csv(
            _fila(1, "11-02-2025", "Liquidacion Rescate Fci", fci, "-1.000", "7.000"),
            _fila(2, "17-02-2025", "Liquidacion Rescate Fci", fci, "-500,5", "3.500"),
            _fila(3, "18-02-2025", "Compra", MSFT, "1", "-1.000"),
        )], MEP)
        assert len(x.no_reconocidos) == 1
        r = x.no_reconocidos.iloc[0]
        assert r["movimiento"] == "2 rescates hasta el 17/02/2025"
        assert r["motivo"].startswith("1.500,50 cuotapartes sin una compra")
        # No supone la causa: puede ser una compra vieja o una transferencia.
        assert "transferencia" in r["motivo"]
        assert "11/02/2025" in r["motivo"]  # sale del archivo, no de una fecha fija

    def test_dos_archivos_superpuestos_no_duplican(self):
        compra = _fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000")
        venta = _fila(2, "05-01-2026", "Venta", MSFT, "-10", "3.000.000")
        x = leer_cocos([_csv(compra, venta), _csv(venta)], MEP)
        assert len(x.operaciones) == 1

    def test_la_especie_en_dolares_se_junta_solo_si_es_el_mismo_instrumento(self):
        x = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000"),
            _fila(2, "02-01-2025", "Compra", "CEDEAR DE MICROSOFT CORP. (MSFTD)", "10", "-1000", moneda="USD"),
            _fila(3, "02-01-2025", "Compra", "YPF S.A. ESCRIT.  D  1 VOTO (YPFD)", "1", "-40.000"),
            _fila(4, "02-01-2025", "Compra", "YPF S.A. ESCRIT. (YPF)", "1", "-40.000"),
        )], MEP)
        assert sorted(set(x.lotes_abiertos["ticker"])) == ["MSFT", "YPF", "YPFD"]


class TestRenta:
    def test_caucion_contado_y_termino_del_mismo_dia_dan_el_interes(self):
        x = leer_cocos([_csv(
            _fila(1, "15-10-2025", "Colocador Caucion Contado", cantidad="", monto="-1.000.000"),
            _fila(2, "15-10-2025", "Colocador Caucion Termino", monto="1.010.000", total="1.009.000", liq="16-10-2025"),
        )], MEP)
        r = x.operaciones.iloc[0]
        assert (r["movimiento"], r["ticker"], r["fecha"]) == (MOV_INTERES, TICKER_CAUCION, "2025-10-16")
        assert r["resultado_usd"] == pytest.approx(9)
        assert r["gastos_usd"] == pytest.approx(1)

    def test_lo_colocado_en_caucion_cuenta_como_capital_del_anio(self):
        from cartera.informe import rendimiento_anual

        # Un millón colocado todo 2025 en cauciones de un día (aquí, una de
        # 364 días por simplicidad) que rinde 100.000: 10% sobre US$ 1.000.
        x = leer_cocos([_csv(
            _fila(1, "01-01-2025", "Colocador Caucion Contado", monto="-1.000.000"),
            _fila(2, "01-01-2025", "Colocador Caucion Termino", monto="1.100.000", liq="31-12-2025"),
        )], pd.Series({"2024-12-01": 1000.0}))
        anio = rendimiento_anual(x.operaciones, x.lotes_abiertos, x.fecha_corte)[0]
        assert anio["renta"] == pytest.approx(100)
        assert anio["capital"] == pytest.approx(1000, rel=0.01)
        assert anio["rendimiento"] == pytest.approx(10, abs=0.1)

    def test_caucion_que_cruza_el_anio_entre_dos_archivos(self):
        x = leer_cocos([
            _csv(_fila(1, "30-12-2025", "Colocador Caucion Contado", monto="-1.000.000")),
            _csv(_fila(2, "30-12-2025", "Colocador Caucion Termino", monto="1.004.000", liq="02-01-2026")),
        ], MEP)
        assert x.operaciones.iloc[0]["resultado_usd"] == pytest.approx(2)  # cobra al MEP del 2/1/2026

    def test_caucion_sin_volver_queda_abierta(self):
        x = leer_cocos([_csv(_fila(1, "30-12-2025", "Colocador Caucion Contado", monto="-1.000.000"))], MEP)
        assert x.lotes_abiertos.iloc[0]["ticker"] == TICKER_CAUCION

    def test_dividendo_en_dolares_neto_de_impuestos(self):
        x = leer_cocos([_csv(
            _fila(1, "13-03-2026", "DIVIDENDOS EN ESPECIE", "Dolar Especie CV 7000", "4,56", "0", "-20"),
            _fila(2, "16-03-2026", "Nota De Credito Conversion", monto="4,56", moneda="USD"),
        )], MEP)
        assert len(x.operaciones) == 1
        d = x.operaciones.iloc[0]
        assert d["movimiento"] == MOV_DIVIDENDO
        assert d["resultado_usd"] == pytest.approx(4.56 - 0.01)

    def test_dividendo_en_acciones_entra_como_lote_a_costo_cero(self):
        x = leer_cocos([_csv(
            _fila(1, "13-03-2026", "DIVIDENDOS EN ESPECIE", "GRUPO SUPERVIELLE ESCRIT. (SUPV)", "12", "0", "0"),
        )], MEP)
        assert x.operaciones.empty
        lote = x.lotes_abiertos.iloc[0]
        assert (lote["ticker"], lote["cantidad"], lote["costo_usd"]) == ("SUPV", 12, 0)

    def test_transferencias_no_son_resultado_y_lo_desconocido_se_lista(self):
        x = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Orden De Pago", monto="-10.000"),
            _fila(2, "02-01-2025", "Recibo De Cobro", monto="10.000"),
            _fila(3, "02-01-2025", "Nota De Credito Usd", monto="3,88", moneda="USD"),
        )], MEP)
        assert x.operaciones.empty
        assert list(x.no_reconocidos["movimiento"]) == ["Nota De Credito Usd"]


class TestCombinar:
    def test_el_mismo_ticker_de_dos_brokers_se_suma_pero_se_puede_filtrar(self):
        cocos = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "1", "-1.000.000"),
            _fila(2, "05-03-2025", "Venta", MSFT, "-1", "1.500.000"),
        )], MEP)
        balanz = Cartera(
            operaciones=pd.DataFrame([{
                "broker": BROKER_BALANZ, "fecha": "2024-06-01", "anio": "2024", "ticker": "MSFT",
                "descripcion": "CEDEAR MICROSOFT", "clase": "CEDEARs", "movimiento": MOV_VENTA,
                "fecha_compra": "2024-01-01", "dias": 152, "costo_usd": 100.0, "venta_usd": 150.0,
                "gastos_usd": 0.0, "resultado_usd": 50.0,
            }]),
            lotes_abiertos=pd.DataFrame(columns=cocos.lotes_abiertos.columns),
            no_reconocidos=pd.DataFrame(columns=cocos.no_reconocidos.columns),
            fecha_corte="2026-10-21",
        )
        todo = combinar([balanz, cocos])
        assert todo.operaciones["id"].tolist() == [1, 2]
        assert todo.operaciones.groupby("ticker")["resultado_usd"].sum()["MSFT"] == pytest.approx(550)
        assert filtrar_broker(todo, BROKER_COCOS).operaciones["resultado_usd"].sum() == pytest.approx(500)
        assert todo.fecha_corte == "2026-10-21"


class TestLecturaMixta:
    """`cartera/lectura.py`: lo que falla en un archivo no frena a los demás."""

    def _balanz(self):
        from tests.test_cartera_balanz import _venta, _xlsx

        return _xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)])

    def test_un_archivo_ajeno_se_avisa_y_el_resto_se_lee(self):
        from cartera.lectura import leer_archivos

        c, avisos = leer_archivos([("b.xlsx", self._balanz()), ("x.txt", b"nada")], MEP)
        assert len(c.operaciones) == 1
        assert "x.txt" in avisos[0]

    def test_sin_mep_cocos_queda_afuera_y_balanz_sigue(self):
        from cartera.lectura import leer_archivos

        cocos = _csv(_fila(1, "02-01-2025", "Compra", MSFT, "1", "-1.000"))
        c, avisos = leer_archivos([("b.xlsx", self._balanz()), ("c.csv", cocos)], None)
        assert set(c.operaciones["broker"]) == {BROKER_BALANZ}
        assert "MEP" in avisos[0]

    def test_nada_legible_es_un_error_para_mostrar(self):
        from cartera.lectura import leer_archivos

        with pytest.raises(ExportInvalido, match="no es un export"):
            leer_archivos([("a.csv", b""), ("b.txt", b"hola")], MEP)

    def test_dos_reportes_de_balanz_usan_el_mas_reciente(self):
        from cartera.lectura import leer_archivos
        from tests.test_cartera_balanz import _lote, _venta, _xlsx

        viejo = _xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)])
        nuevo = _xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)], [_lote("BBB", "2025-01-10", 4, 2500)])
        c, avisos = leer_archivos([("nuevo.xlsx", nuevo), ("viejo.xlsx", viejo)], MEP)
        assert len(c.operaciones) == 1  # no se cuenta dos veces
        assert "nuevo.xlsx" in avisos[0]

    @pytest.mark.parametrize("caso", ["solo_lotes", "solo_dividendo", "venta_mismo_dia"])
    def test_el_informe_se_arma_con_carteras_minimas(self, caso):
        import json

        from cartera.informe import armar_informe
        from cartera.lectura import leer_archivos
        from tests.test_cartera_balanz import _lote, _realizado, _venta, _xlsx

        archivo = {
            "solo_lotes": _xlsx([], [_lote("AAA", "2025-01-10", 4, 2500)]),
            "solo_dividendo": _xlsx([_realizado(Fecha="2025-03-01", **{"Tipo Movimiento": "Dividendo", "Moneda Venta": "Dólares"}, Dividendos=3.0)]),
            "venta_mismo_dia": _xlsx([_venta("AAA", "2024-01-01", "2024-01-01", 1, 1000, 1100)]),
        }[caso]
        c, _ = leer_archivos([("b.xlsx", archivo)], MEP)
        json.dumps(armar_informe(c), allow_nan=False)  # sin NaN: el JSON del dibujo no los admite
