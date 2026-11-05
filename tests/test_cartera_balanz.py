"""
Tests del lector de Balanz (`cartera/balanz.py`) y del informe (`cartera/informe.py`).

Usan un Excel sintético armado acá, con las mismas hojas y columnas que el
export real. El real no entra al repo: trae nombre, número de cuenta y toda
la historia de operaciones de una persona.

Las trampas que fijan son las que se midieron sobre un export real: los
cupones dicen "Dólares" pero vienen en pesos, los gastos están siempre en
pesos, y el vencimiento de una ON llega con precio de venta negativo.
"""

import io

import pandas as pd
import pytest

from cartera.balanz import HOJA_LOTES, HOJA_REALIZADO
from cartera.balanz import leer_balanz as leer_export
from cartera.informe import armar_informe, rendimiento_anual, tir_anualizada
from cartera.modelo import MOV_CUPON, MOV_DIVIDENDO, MOV_VENTA, ExportInvalido, combinar

MEP = 1000.0


def _realizado(**kw):
    fila = {
        "Cantidad": 0.0, "Descripcion": "CEDEAR TEST", "Fecha": None, "FechaCompra": None, "Gastos": 0.0,
        "Moneda Compra": None, "Moneda Venta": None, "Operacion Compra": None, "Operacion Venta": None,
        "Precio Compra": None, "PrecioVenta": None, "Ticker": "AAA", "Tipo": "Cedears", "Tipo Movimiento": "Orden",
        "Cupones": None, "Dividendos": None, "Intereses": None, "MTMFuturos": None,
        "OperacionCompraDolarCCL": None, "OperacionCompraDolarMEP": None, "OperacionCompraDolarOficial": None,
        "OperacionVentaDolarCCL": MEP, "OperacionVentaDolarMEP": MEP, "OperacionVentaDolarOficial": MEP,
    }
    fila.update(kw)
    return fila


def _venta(ticker, compra, venta, cant, p_compra, p_venta, mep_compra=MEP, mep_venta=MEP, gastos=0.0, **kw):
    return _realizado(
        Ticker=ticker, Fecha=venta, FechaCompra=compra, Cantidad=cant, **{"Precio Compra": p_compra},
        PrecioVenta=p_venta, **{"Moneda Compra": "Pesos", "Moneda Venta": "Pesos"}, Gastos=gastos,
        OperacionCompraDolarMEP=mep_compra, OperacionVentaDolarMEP=mep_venta, **kw,
    )


def _lote(ticker, compra, cant, precio, moneda="Pesos", mep=MEP, tipo="Cedears"):
    return {
        "Cantidad": cant, "Descripcion": "LOTE " + ticker, "Fecha": compra, "Fecha Lote": "2026-10-21",
        "Gastos": 0.0, "Moneda": moneda, "Operacion": "Boleto", "Precio Compra": precio, "Ticker": ticker,
        "Tipo": tipo, "DolarCCL": mep, "DolarMEP": mep, "DolarOficial": mep,
    }


def _xlsx(realizado, lotes=(), hojas=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([]).to_excel(w, sheet_name="resultados_por_lotes_iniciales", index=False)
        if hojas is None or HOJA_REALIZADO in hojas:
            pd.DataFrame(list(realizado)).to_excel(w, sheet_name=HOJA_REALIZADO, index=False)
        if hojas is None or HOJA_LOTES in hojas:
            pd.DataFrame(list(lotes)).to_excel(w, sheet_name=HOJA_LOTES, index=False)
    return buf.getvalue()


class TestFormato:
    def test_un_excel_sin_las_hojas_es_un_error_para_mostrar(self):
        with pytest.raises(ExportInvalido, match="falta la hoja"):
            leer_export(_xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)], hojas={HOJA_REALIZADO}))

    def test_un_archivo_que_no_es_excel_es_un_error_para_mostrar(self):
        with pytest.raises(ExportInvalido, match="No pudimos abrir"):
            leer_export(b"esto no es un xlsx")

    def test_una_columna_que_falta_avisa_cual(self):
        fila = _venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)
        del fila["OperacionVentaDolarMEP"]
        with pytest.raises(ExportInvalido, match="OperacionVentaDolarMEP"):
            leer_export(_xlsx([fila]))


class TestConversion:
    def test_venta_en_pesos_usa_el_mep_de_cada_fecha(self):
        # 10 a $1.000 con MEP 500 = US$ 20; 10 a $3.000 con MEP 1.000 = US$ 30.
        x = leer_export(_xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 10, 1000, 3000, mep_compra=500, gastos=1000)]))
        v = x.operaciones.iloc[0]
        assert v["movimiento"] == MOV_VENTA
        assert v["costo_usd"] == pytest.approx(20)
        assert v["venta_usd"] == pytest.approx(30)
        assert v["gastos_usd"] == pytest.approx(1)  # gastos en pesos, al MEP de la venta
        assert v["resultado_usd"] == pytest.approx(9)
        assert v["dias"] == 152

    def test_dividendo_de_cedear_viene_en_dolares(self):
        fila = _realizado(Fecha="2024-03-01", **{"Tipo Movimiento": "Dividendo", "Moneda Venta": "Dólares C.V. 7000"}, Dividendos=2.5)
        x = leer_export(_xlsx([fila]))
        d = x.operaciones.iloc[0]
        assert d["movimiento"] == MOV_DIVIDENDO
        assert d["resultado_usd"] == pytest.approx(2.5)

    def test_cupon_viene_en_pesos_aunque_diga_dolares(self):
        fila = _realizado(Fecha="2024-03-01", Ticker="ONX", Tipo="Corporativos - Dólar",
                          **{"Tipo Movimiento": "Cupón", "Moneda Venta": "Dólares C.V. 7000"}, Cupones=5000.0)
        d = leer_export(_xlsx([fila])).operaciones.iloc[0]
        assert d["movimiento"] == MOV_CUPON
        assert d["cobro_moneda"] == "ARS"
        assert d["resultado_usd"] == pytest.approx(5)

    def test_la_moneda_del_cupon_sale_del_monto_por_nominal(self):
        # Otra cuenta: un cupón cobrado en dólares. 1.000 nominales que cobran
        # 35 son 0,035 por nominal: dólares. Cobrar 35.000 son 35 por nominal:
        # pesos, aunque la especie diga "Dólares".
        def cupon(fecha, monto):
            return _realizado(Fecha=fecha, Ticker="ONX", Tipo="Corporativos - Dólar",
                              **{"Tipo Movimiento": "Cupón", "Moneda Venta": "Dólares"}, Cupones=monto)

        x = leer_export(_xlsx(
            [cupon("2025-03-01", 35.0), cupon("2025-09-01", 35_000.0)],
            [_lote("ONX", "2025-01-10", 1000, 1.0, moneda="Dólares", tipo="Corporativos - Dólar")],
        ))
        c = x.operaciones.set_index("fecha")
        assert c.loc["2025-03-01", "cobro_moneda"] == "USD"
        assert c.loc["2025-03-01", "resultado_usd"] == pytest.approx(35)
        assert c.loc["2025-09-01", "cobro_moneda"] == "ARS"
        assert c.loc["2025-09-01", "resultado_usd"] == pytest.approx(35)

    def test_vencimiento_de_on_con_precio_negativo_se_rescata_a_la_par(self):
        fila = _venta("ONX", "2023-06-09", "2026-07-02", 300, 1.05, -40.7,
                      **{"Operacion Venta": "Renta y Amortización / ONX"})
        fila["Moneda Compra"] = "Dólares"
        fila["Moneda Venta"] = "Dólares C.V. 7000"
        v = leer_export(_xlsx([fila])).operaciones.iloc[0]
        assert v["venta_usd"] == pytest.approx(300)
        assert v["costo_usd"] == pytest.approx(315)

    def test_precio_negativo_sin_amortizacion_no_se_adivina(self):
        x = leer_export(_xlsx([
            _venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, -5),
            _venta("BBB", "2024-01-01", "2024-06-01", 1, 1000, 1100),
        ]))
        assert list(x.operaciones["ticker"]) == ["BBB"]
        assert list(x.no_reconocidos["ticker"]) == ["AAA"]

    def test_movimiento_desconocido_queda_fuera_de_los_totales_y_listado(self):
        x = leer_export(_xlsx([
            _venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100),
            _realizado(Fecha="2024-05-01", Ticker="FUT", **{"Tipo Movimiento": "Futuro"}),
        ]))
        assert len(x.operaciones) == 1
        assert x.no_reconocidos.iloc[0]["movimiento"] == "Futuro"
        assert x.no_reconocidos.iloc[0]["motivo"] == "movimiento desconocido"

    def test_tipo_de_activo_desconocido_entra_con_el_nombre_de_balanz(self):
        x = leer_export(_xlsx([_venta("OPC", "2024-01-01", "2024-06-01", 1, 1000, 1100, Tipo="Opciones")]))
        assert x.operaciones.iloc[0]["clase"] == "Opciones"

    def test_lotes_abiertos_al_costo_y_fecha_de_corte(self):
        x = leer_export(_xlsx(
            [_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)],
            [_lote("BBB", "2025-01-10", 4, 2500), _lote("FCI", "2026-06-05", 100, 1.2, moneda="Dólares", tipo="Fondos")],
        ))
        assert x.lotes_abiertos["costo_usd"].tolist() == pytest.approx([10, 120])
        assert x.fecha_corte == "2026-10-21"


class TestRendimientoAnual:
    def test_una_venta_de_dos_anios_se_reparte_por_dias(self):
        # Comprada el 2/7/2024, vendida el 1/7/2025: 183 días en 2024 y 181
        # en 2025. Ganó US$ 100 sobre US$ 1.000.
        x = leer_export(_xlsx([_venta("AAA", "2024-07-02", "2025-07-01", 1, 1_000_000, 1_100_000)]))
        anios = {r["anio"]: r for r in rendimiento_anual(x.operaciones, x.lotes_abiertos, x.fecha_corte)}
        assert anios["2024"]["compraventa"] == pytest.approx(100 * 183 / 364, abs=0.01)
        assert anios["2025"]["compraventa"] == pytest.approx(100 * 181 / 364, abs=0.01)
        # El capital es el mismo en los dos tramos, así que rinden lo mismo.
        assert anios["2024"]["rendimiento"] == pytest.approx(anios["2025"]["rendimiento"], abs=0.2)
        assert anios["2024"]["parcial"] and anios["2025"]["parcial"]

    def test_lo_abierto_suma_capital_pero_no_resultado(self):
        x = leer_export(_xlsx(
            [_venta("AAA", "2025-01-01", "2025-12-31", 1, 1_000_000, 1_100_000)],
            [_lote("BBB", "2025-01-01", 1, 1_000_000)],
        ))
        r = {a["anio"]: a for a in rendimiento_anual(x.operaciones, x.lotes_abiertos, x.fecha_corte)}["2025"]
        assert r["resultado"] == pytest.approx(100)
        assert r["capital"] == pytest.approx(2000, rel=0.01)
        assert r["rendimiento"] == pytest.approx(5, abs=0.1)

    def test_la_renta_cuenta_el_anio_del_cobro(self):
        x = leer_export(_xlsx(
            [_realizado(Fecha="2026-03-01", **{"Tipo Movimiento": "Dividendo", "Moneda Venta": "Dólares"}, Dividendos=10.0)],
            [_lote("AAA", "2025-06-01", 1, 1_000_000)],
        ))
        anios = {a["anio"]: a for a in rendimiento_anual(x.operaciones, x.lotes_abiertos, x.fecha_corte)}
        assert anios["2025"]["renta"] == 0
        assert anios["2026"]["renta"] == pytest.approx(10)

    def test_tir_de_una_sola_venta(self):
        # US$ 1.000 → US$ 1.100 en exactamente un año: 10% anual.
        x = leer_export(_xlsx([_venta("AAA", "2024-01-01", "2024-12-31", 1, 1_000_000, 1_100_000)]))
        assert tir_anualizada(x.operaciones, x.lotes_abiertos, x.fecha_corte) == pytest.approx(10, abs=0.1)


class TestInforme:
    def test_el_informe_completo_se_serializa_y_cuadra(self):
        import json

        x = leer_export(_xlsx(
            [
                _venta("AAA", "2024-01-01", "2024-06-01", 10, 1000, 1500),
                _venta("BBB", "2024-02-01", "2025-02-01", 5, 2000, 1000),
                _realizado(Fecha="2025-03-01", Ticker="CCC", **{"Tipo Movimiento": "Dividendo", "Moneda Venta": "Dólares"}, Dividendos=3.0),
            ],
            [_lote("CCC", "2024-06-01", 10, 5000)],
        ))
        inf = armar_informe(combinar([x]))
        json.dumps(inf)  # lo que no serializa no llega al dibujo
        assert inf["kpis"]["total"] == pytest.approx(5 - 5 + 3)
        assert sum(r["total"] for r in inf["por_ticker"]) == pytest.approx(inf["kpis"]["total"])
        assert sum(r["resultado"] for r in inf["rendimiento_anual"]) == pytest.approx(inf["kpis"]["total"], abs=0.05)
        assert [r["ticker"] for r in inf["mejores"]][0] == "AAA"
        assert inf["cartera_mix"][0]["peso"] == 100
