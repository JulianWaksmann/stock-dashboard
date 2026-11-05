"""
Casos borde de "Mi cartera", salidos de una revisión adversarial del código.

Cada test reproduce un caso que antes se caía o daba un número falso sin
avisar. Son de otras cuentas posibles, no de la del autor: la herramienta es
pública y lo que se midió sobre un export propio no alcanza.
"""

import json

import pandas as pd
import pytest

import cartera.balanz as balanz_mod
from cartera.cocos import leer_cocos
from cartera.informe import armar_informe, calendario_cobros, rendimiento_anual, tir_anualizada
from cartera.lectura import leer_archivos
from cartera.modelo import (
    BROKER_BALANZ,
    BROKER_COCOS,
    MOV_INTERES,
    ExportInvalido,
    combinar,
    filtrar_broker,
)
from tests.test_cartera_balanz import _lote, _realizado, _venta, _xlsx
from tests.test_cartera_cocos import ENCABEZADO, MSFT, _csv, _fila

MEP = pd.Series({"2020-01-02": 1000.0})


def _dividendo(ticker, fecha, monto, **kw):
    return _realizado(Ticker=ticker, Fecha=fecha, **{"Tipo Movimiento": "Dividendo", "Moneda Venta": "Dólares"},
                      Dividendos=monto, **kw)


class TestInforme:
    def test_compro_nunca_vendio_y_cobro_dividendos(self):
        # El perfil más común: sin ninguna venta, `fecha_compra` era NaN y el
        # calendario de cobros reventaba al compararla con una fecha.
        c, _ = leer_archivos([("b.xlsx", _xlsx(
            [_dividendo("AAA", "2025-06-10", 10.0)],
            [{**_lote("AAA", "2024-01-10", 10, 100000), "Fecha Lote": "2025-10-21"}],
        ))], None)
        inf = armar_informe(c)
        assert inf["calendario_cobros"]["total"] == pytest.approx(10)

    def test_el_cobro_que_falta_este_mes_aparece_en_el_calendario(self):
        c, _ = leer_archivos([("b.xlsx", _xlsx(
            [_dividendo("AAA", "2024-10-25", 10.0)],
            [{**_lote("AAA", "2024-01-10", 10, 100000), "Fecha Lote": "2025-10-21"}],
        ))], None)
        cal = armar_informe(c)["calendario_cobros"]
        assert cal["desde"] == "2025-10"
        assert cal["proximo_mes"] == "2025-10"

    def test_un_dividendo_se_proyecta_sobre_la_tenencia_del_mismo_broker(self):
        balanz = leer_archivos([("b.xlsx", _xlsx(
            [_dividendo("MSFT", "2025-06-10", 10.0)],
            [{**_lote("MSFT", "2024-01-10", 10, 100000), "Fecha Lote": "2025-10-21"}],
        ))], None)[0]
        cocos = leer_cocos([_csv(_fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000"))], MEP)
        todo = combinar([balanz, cocos])
        # 10 USD sobre 10 en Balanz: se repite 10, no se diluye en las 20 totales.
        cal = calendario_cobros(todo.operaciones, todo.lotes_abiertos, todo.fecha_corte)
        assert cal["total"] == pytest.approx(10)

    def test_la_tir_ve_el_capital_de_las_cauciones(self):
        # Doce cauciones de un mes al 2%: la TIR tiene que andar por 27% anual,
        # no en cientos (antes daba 850%).
        filas = []
        for mes in range(1, 13):
            fecha = f"02-{mes:02d}-2025"
            filas.append(_fila(2 * mes, fecha, "Colocador Caucion Contado", monto="-10.000.000"))
            filas.append(_fila(2 * mes + 1, fecha, "Colocador Caucion Termino", monto="10.200.000",
                               liq=f"01-{mes + 1:02d}-2025" if mes < 12 else "01-01-2026"))
        c = leer_cocos([_csv(*filas)], MEP)
        tir = tir_anualizada(c.operaciones, c.lotes_abiertos, c.fecha_corte)
        assert 20 < tir < 35

    def test_caucion_de_balanz_sin_capital_no_infla_el_rendimiento(self):
        intereses = [
            _realizado(Fecha=f"2024-{m:02d}-15", Ticker="PESOS", Tipo="Efectivo",
                       **{"Tipo Movimiento": "Caución - Pase - Cheque", "Moneda Venta": "Pesos"}, Intereses=30000.0)
            for m in range(1, 13)
        ]
        c, _ = leer_archivos([("b.xlsx", _xlsx([_venta("AAA", "2024-01-01", "2024-12-31", 1, 100000, 100000), *intereses]))], None)
        inf = armar_informe(c)
        anio = {r["anio"]: r for r in inf["rendimiento_anual"]}["2024"]
        assert anio["rendimiento"] == pytest.approx(0, abs=0.5)  # antes: 361%
        assert inf["renta_sin_capital"] == pytest.approx(360)
        assert inf["kpis"]["renta"] == pytest.approx(360)  # en los totales sí cuenta

    def test_cartera_combinada_sin_nan_en_el_json(self):
        balanz = leer_archivos([("b.xlsx", _xlsx(
            [_venta("AAA", "2024-01-01", "2024-06-01", 10, 1000, 1500), _dividendo("MSFT", "2025-06-10", 3.0)],
            [_lote("MSFT", "2024-06-01", 10, 5000)],
        ))], None)[0]
        cocos = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000"),
            _fila(2, "05-03-2025", "Venta", MSFT, "-4", "600.000"),
            _fila(3, "15-03-2025", "Colocador Caucion Contado", monto="-1.000.000"),
            _fila(4, "15-03-2025", "Colocador Caucion Termino", monto="1.010.000", liq="16-03-2025"),
        )], MEP)
        json.dumps(armar_informe(combinar([balanz, cocos])), allow_nan=False)


class TestFiltroPorBroker:
    def test_cada_broker_se_mide_hasta_su_propio_corte(self):
        balanz = leer_archivos([("b.xlsx", _xlsx(
            [_venta("ZZZ", "2024-01-01", "2024-06-01", 1, 1000, 1100)],
            [{**_lote("AAA", "2024-01-10", 10, 100000), "Fecha Lote": "2025-03-01"}],
        ))], None)[0]
        cocos = leer_cocos([_csv(_fila(1, "20-10-2026", "Compra", MSFT, "1", "-1.000"))], MEP)
        todo = combinar([balanz, cocos])
        assert todo.fecha_corte == "2026-10-20"
        solo = filtrar_broker(todo, BROKER_BALANZ)
        assert solo.fecha_corte == "2025-03-01"
        anios = [r["anio"] for r in rendimiento_anual(solo.operaciones, solo.lotes_abiertos, solo.fecha_corte)]
        assert "2026" not in anios


class TestCocos:
    def test_filas_que_terminan_en_punto_y_coma(self):
        filas = [_fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000") + ";"]
        x = leer_cocos([_csv(*filas)], MEP)
        assert x.lotes_abiertos["cantidad"].tolist() == [10]

    def test_una_fila_con_columnas_de_mas_es_un_aviso_y_no_tumba_a_balanz(self):
        rota = _csv(_fila(1, "02-01-2025", "Compra", MSFT, "10", "-1.000.000") + ";x;y;z")
        bueno = _xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)])
        c, avisos = leer_archivos([("b.xlsx", bueno), ("c.csv", rota)], MEP)
        assert len(c.operaciones) == 1
        assert avisos and avisos[0].startswith("Cocos")

    def test_tickets_vacios_no_se_pisan(self):
        div = lambda n: _fila("", "13-03-2026", "DIVIDENDOS EN ESPECIE", "Dolar Especie CV 7000", n, "0", "0")  # noqa: E731
        x = leer_cocos([_csv(div("4,56"), div("7"))], MEP)
        assert x.operaciones["resultado_usd"].sum() == pytest.approx(11.56)

    def test_contado_y_termino_con_el_mismo_ticket(self):
        x = leer_cocos([_csv(
            _fila(9, "15-10-2025", "Colocador Caucion Contado", monto="-1.000.000"),
            _fila(9, "15-10-2025", "Colocador Caucion Termino", monto="1.010.000", liq="16-10-2025"),
        )], MEP)
        assert x.operaciones.iloc[0]["movimiento"] == MOV_INTERES
        assert x.lotes_abiertos.empty

    def test_caucion_con_un_termino_en_el_archivo_que_no_se_subio(self):
        # Dos colocaciones el 30/12 y un solo término (el otro liquida en el
        # archivo del año siguiente): antes daba un interés de −4.999 USD.
        x = leer_cocos([_csv(
            _fila(1, "30-12-2025", "Colocador Caucion Contado", monto="-1.000.000"),
            _fila(2, "30-12-2025", "Colocador Caucion Contado", monto="-5.000.000"),
            _fila(3, "30-12-2025", "Colocador Caucion Termino", monto="1.004.000", liq="31-12-2025"),
        )], MEP)
        assert x.operaciones.iloc[0]["resultado_usd"] == pytest.approx(4)
        assert x.lotes_abiertos["cantidad"].tolist() == [5_000_000]

    @pytest.mark.parametrize(("pesos", "dolares", "base"), [
        ("CEDEAR COCA COLA (KO)", "CEDEAR COCA COLA (KOD)", "KO"),
        ("ON YPF CLASE 6 (YCA6O)", "ON YPF CLASE 6 (YCA6D)", "YCA6O"),
    ])
    def test_la_especie_en_dolares_se_junta_con_la_de_pesos(self, pesos, dolares, base):
        x = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", pesos, "10", "-1.000.000"),
            _fila(2, "05-03-2025", "Venta", dolares, "-10", "1.200", moneda="USD"),
        )], MEP)
        assert x.operaciones["ticker"].tolist() == [base]
        assert x.no_reconocidos.empty

    def test_montos_con_signo_peso_y_monedas_escritas_distinto(self):
        x = leer_cocos([_csv(
            _fila(1, "15-10-2025", "Colocador Caucion Contado", monto="$ -1.000.000"),
            _fila(2, "15-10-2025", "Colocador Caucion Termino", monto="$ 1.010.000", liq="16-10-2025"),
            _fila(3, "02-01-2025", "Compra", MSFT, "1", "-1.000", moneda="U$S"),
        )], MEP)
        assert x.operaciones.iloc[0]["resultado_usd"] == pytest.approx(10)
        assert x.lotes_abiertos["costo_usd"].tolist() == pytest.approx([1000])

    def test_un_monto_ilegible_se_lista_en_vez_de_tomarse_como_cero(self):
        x = leer_cocos([_csv(
            _fila(1, "15-10-2025", "Colocador Caucion Contado", monto="mil"),
            _fila(2, "02-01-2025", "Compra", MSFT, "1", "-1.000"),
        )], MEP)
        assert x.operaciones.empty
        assert "no se pudo leer" in x.no_reconocidos.iloc[0]["motivo"]

    def test_moneda_desconocida_se_lista(self):
        x = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "1", "-1.000", moneda="EUR"),
            _fila(2, "02-01-2025", "Compra", MSFT, "1", "-1.000"),
        )], MEP)
        assert x.no_reconocidos.iloc[0]["motivo"] == "moneda desconocida"

    def test_el_corte_es_la_ultima_ejecucion_no_una_liquidacion_futura(self):
        x = leer_cocos([_csv(
            _fila(1, "30-12-2025", "Colocador Caucion Contado", monto="-1.000.000"),
            _fila(2, "30-12-2025", "Colocador Caucion Termino", monto="1.004.000", liq="05-01-2026"),
        )], MEP)
        assert x.fecha_corte == "2025-12-30"

    def test_csv_solo_con_encabezado_y_filas_vacias(self):
        with pytest.raises(ExportInvalido):
            leer_cocos([(ENCABEZADO + "\n").encode()], MEP)


class TestBalanz:
    def test_texto_en_una_columna_numerica_se_lista(self):
        fila = _venta("AAA", "2024-01-01", "2024-06-01", "10 u", 1000, 1100)
        c, _ = leer_archivos([("b.xlsx", _xlsx([fila, _venta("BBB", "2024-01-01", "2024-06-01", 1, 1000, 1100)]))], None)
        assert c.operaciones["ticker"].tolist() == ["BBB"]
        assert "número" in c.no_reconocidos.iloc[0]["motivo"]

    def test_sin_ninguna_fecha_legible_es_un_error_para_mostrar(self):
        with pytest.raises(ExportInvalido):
            balanz_mod.leer_balanz(_xlsx([], [{**_lote("AAA", "x", 1, 1), "Fecha Lote": None}]))

    @pytest.mark.parametrize(("valor", "esperado"), [
        ("2024-04-03", "2024-04-03"),
        ("03/04/2024", "2024-04-03"),
        ("13/04/2024", "2024-04-13"),
        (45000, "2023-03-15"),
    ])
    def test_formatos_de_fecha(self, valor, esperado):
        assert balanz_mod._fecha(pd.Series([valor])).iloc[0] == esperado

    def test_un_excel_que_se_infla_al_abrirlo_se_rechaza(self, monkeypatch):
        monkeypatch.setattr(balanz_mod, "_MAX_DESCOMPRIMIDO", 1000)
        with pytest.raises(ExportInvalido, match="demasiado grande"):
            balanz_mod.leer_balanz(_xlsx([_venta("AAA", "2024-01-01", "2024-06-01", 1, 1000, 1100)]))


class TestDosBrokersMismoActivo:
    def test_msft_en_los_dos_suma_en_una_fila_y_mantiene_el_broker(self):
        balanz = leer_archivos([("b.xlsx", _xlsx([_venta("MSFT", "2024-01-01", "2024-06-01", 1, 1000, 1500)]))], None)[0]
        cocos = leer_cocos([_csv(
            _fila(1, "02-01-2025", "Compra", MSFT, "1", "-1.000.000"),
            _fila(2, "05-03-2025", "Venta", MSFT, "-1", "1.500.000"),
        )], MEP)
        inf = armar_informe(combinar([balanz, cocos]))
        msft = [r for r in inf["por_ticker"] if r["ticker"] == "MSFT"]
        assert len(msft) == 1
        assert {o["broker"] for o in inf["operaciones"]} == {BROKER_BALANZ, BROKER_COCOS}
