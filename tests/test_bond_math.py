"""
Tests de la matemática financiera de renta fija (`bonds/bond_math.py`).

Cada caso se contrasta contra un resultado conocido por construcción (un bono
comprado a la par rinde su cupón, un cupón a mitad de período devengó la mitad
del interés, etc.) y no contra el output del propio código, para que un cambio
en la implementación no pueda "validarse" contra sí mismo.
"""

from datetime import date

import pytest

from bonds.bond_math import (
    CashFlow,
    accrued_interest,
    add_months,
    analyze_bond,
    build_cashflows,
    convexity,
    days_30_360,
    generate_coupon_dates,
    macaulay_duration,
    modified_duration,
    present_value,
    residual_capital,
    weighted_average_life,
    yield_to_maturity,
)

# Bono de referencia: bullet, cupón 10% semestral, emitido 15/01/2020,
# vence 15/01/2030. Todos los casos que no digan otra cosa lo usan.
ISSUE = date(2020, 1, 15)
MATURITY = date(2030, 1, 15)
COUPON = 10.0
FREQUENCY = 2


class TestAddMonths:
    def test_desplazamiento_simple(self):
        assert add_months(date(2025, 1, 15), 6) == date(2025, 7, 15)

    def test_desplazamiento_negativo_cruza_anio(self):
        assert add_months(date(2025, 2, 10), -3) == date(2024, 11, 10)

    def test_recorta_al_ultimo_dia_del_mes_destino(self):
        # El 31 de marzo movido un mes atrás no existe en febrero.
        assert add_months(date(2025, 3, 31), -1) == date(2025, 2, 28)
        assert add_months(date(2024, 3, 31), -1) == date(2024, 2, 29)


class TestDays30360:
    def test_un_mes_exacto_vale_30_dias(self):
        assert days_30_360(date(2025, 1, 15), date(2025, 2, 15)) == 30

    def test_un_anio_exacto_vale_360_dias(self):
        assert days_30_360(date(2025, 1, 15), date(2026, 1, 15)) == 360

    def test_el_dia_31_se_trata_como_30(self):
        assert days_30_360(date(2025, 1, 31), date(2025, 2, 28)) == 28


class TestGenerateCouponDates:
    def test_el_ultimo_cupon_cae_el_dia_del_vencimiento(self):
        dates = generate_coupon_dates(ISSUE, MATURITY, FREQUENCY)
        assert dates[-1] == MATURITY

    def test_cantidad_de_cupones_semestrales_en_diez_anios(self):
        assert len(generate_coupon_dates(ISSUE, MATURITY, FREQUENCY)) == 20

    def test_cantidad_de_cupones_trimestrales(self):
        assert len(generate_coupon_dates(ISSUE, MATURITY, 4)) == 40

    def test_no_incluye_fechas_anteriores_o_iguales_a_la_emision(self):
        dates = generate_coupon_dates(ISSUE, MATURITY, FREQUENCY)
        assert all(d > ISSUE for d in dates)

    def test_frecuencia_no_soportada_es_error(self):
        with pytest.raises(ValueError, match="Frecuencia"):
            generate_coupon_dates(ISSUE, MATURITY, 3)

    def test_vencimiento_anterior_a_la_emision_es_error(self):
        with pytest.raises(ValueError, match="posterior"):
            generate_coupon_dates(MATURITY, ISSUE, FREQUENCY)


class TestBuildCashflows:
    def test_bullet_devuelve_todo_el_capital_al_vencimiento(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert sum(f.amortization for f in flows) == pytest.approx(100.0)
        assert flows[-1].amortization == pytest.approx(100.0)
        assert all(f.amortization == 0 for f in flows[:-1])

    def test_bullet_paga_siempre_el_mismo_cupon(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert all(f.interest == pytest.approx(5.0) for f in flows)

    def test_el_cupon_baja_con_cada_amortizacion(self):
        # Amortiza 50% un año antes del vencimiento: a partir de ahí el cupón
        # se calcula sobre la mitad del capital.
        amortizations = ((date(2029, 1, 15), 50.0), (MATURITY, 50.0))
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY, amortizations)
        by_date = {f.date: f for f in flows}
        # El cupón del día de la amortización todavía devenga sobre el capital entero.
        assert by_date[date(2029, 1, 15)].interest == pytest.approx(5.0)
        assert by_date[date(2029, 7, 15)].interest == pytest.approx(2.5)
        assert by_date[MATURITY].interest == pytest.approx(2.5)

    def test_las_amortizaciones_suman_el_valor_nominal(self):
        amortizations = ((date(2028, 1, 15), 30.0), (date(2029, 1, 15), 30.0), (MATURITY, 40.0))
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY, amortizations)
        assert sum(f.amortization for f in flows) == pytest.approx(100.0)


class TestResidualCapital:
    def test_bullet_mantiene_el_capital_entero_hasta_el_vencimiento(self):
        assert residual_capital(None, MATURITY, date(2029, 12, 31)) == pytest.approx(100.0)

    def test_baja_con_cada_cuota_de_capital(self):
        amortizations = ((date(2028, 1, 15), 30.0), (MATURITY, 70.0))
        assert residual_capital(amortizations, MATURITY, date(2028, 6, 1)) == pytest.approx(70.0)
        assert residual_capital(amortizations, MATURITY, date(2027, 1, 1)) == pytest.approx(100.0)

    def test_vencido_el_bono_no_queda_capital(self):
        assert residual_capital(None, MATURITY, date(2031, 1, 1)) == pytest.approx(0.0)


class TestAccruedInterest:
    def test_en_fecha_de_cupon_no_hay_interes_corrido(self):
        accrued = accrued_interest(ISSUE, MATURITY, COUPON, FREQUENCY, date(2025, 1, 15))
        assert accrued == pytest.approx(0.0)

    def test_a_mitad_de_periodo_devengo_la_mitad_del_cupon(self):
        accrued = accrued_interest(ISSUE, MATURITY, COUPON, FREQUENCY, date(2025, 4, 15))
        assert accrued == pytest.approx(2.5)

    def test_vencido_el_bono_no_devenga_nada(self):
        accrued = accrued_interest(ISSUE, MATURITY, COUPON, FREQUENCY, date(2030, 6, 1))
        assert accrued == pytest.approx(0.0)

    def test_devenga_sobre_el_capital_residual(self):
        amortizations = ((date(2028, 1, 15), 50.0), (MATURITY, 50.0))
        accrued = accrued_interest(ISSUE, MATURITY, COUPON, FREQUENCY, date(2028, 4, 15), amortizations)
        # Capital residual 50 => cupón semestral 2.5 => medio período = 1.25.
        assert accrued == pytest.approx(1.25)


class TestYieldToMaturity:
    def test_comprado_a_la_par_rinde_su_cupon_capitalizado(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        ytm = yield_to_maturity(flows, date(2025, 1, 15), 100.0)
        # Cupón 10% semestral => tasa efectiva anual (1 + 0.10/2)^2 - 1 = 10.25%.
        assert ytm == pytest.approx(0.1025, abs=0.001)

    def test_bajo_la_par_rinde_mas_que_el_cupon(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        ytm = yield_to_maturity(flows, date(2025, 1, 15), 85.0)
        assert ytm > 0.1025

    def test_sobre_la_par_rinde_menos_que_el_cupon(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        ytm = yield_to_maturity(flows, date(2025, 1, 15), 115.0)
        assert ytm < 0.1025

    def test_la_tir_descuenta_el_flujo_hasta_el_precio_pagado(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        settlement = date(2025, 3, 20)
        price = 92.4
        ytm = yield_to_maturity(flows, settlement, price)
        pending = [f for f in flows if f.date > settlement]
        assert present_value(pending, settlement, ytm) == pytest.approx(price, abs=1e-6)

    def test_sin_flujos_pendientes_no_hay_tir(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert yield_to_maturity(flows, date(2031, 1, 1), 100.0) is None

    def test_precio_no_positivo_no_tiene_tir(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert yield_to_maturity(flows, date(2025, 1, 15), 0.0) is None
        assert yield_to_maturity(flows, date(2025, 1, 15), -10.0) is None

    def test_precio_irrisorio_queda_fuera_del_rango_de_tasas(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        # Pagar una millonésima por un flujo de 150 implicaría una TIR por
        # encima del 1000% anual: fuera del rango que reportamos.
        assert yield_to_maturity(flows, date(2025, 1, 15), 1e-6) is None

    def test_precio_absurdamente_alto_queda_fuera_del_rango_de_tasas(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        # En el otro extremo: un precio que implicaría una TIR por debajo
        # de -99.99% tampoco se reporta.
        assert yield_to_maturity(flows, date(2025, 1, 15), 1e25) is None

    def test_un_precio_de_remate_devuelve_una_tir_altisima_pero_valida(self):
        # Un bono en default cotizando a 8 sigue teniendo TIR calculable: es
        # justamente el caso donde Newton-Raphson suele divergir.
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        ytm = yield_to_maturity(flows, date(2025, 1, 15), 8.0)
        assert ytm is not None and ytm > 0.5


class TestDurations:
    def test_la_duration_es_menor_al_plazo_al_vencimiento(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        settlement = date(2025, 1, 15)
        macaulay = macaulay_duration(flows, settlement, 0.1025)
        assert 0 < macaulay < 5.0

    def test_un_bono_sin_cupon_tiene_duration_igual_al_plazo(self):
        # Cupón cero: el único flujo es el capital al vencimiento.
        flows = build_cashflows(ISSUE, MATURITY, 0.0, FREQUENCY)
        settlement = date(2025, 1, 15)
        macaulay = macaulay_duration(flows, settlement, 0.08)
        assert macaulay == pytest.approx(5.0, abs=0.02)

    def test_la_duration_modificada_es_menor_a_la_de_macaulay(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        settlement = date(2025, 1, 15)
        macaulay = macaulay_duration(flows, settlement, 0.1025)
        modified = modified_duration(flows, settlement, 0.1025)
        assert modified == pytest.approx(macaulay / 1.1025)
        assert modified < macaulay

    def test_la_duration_modificada_aproxima_la_caida_de_precio(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        settlement = date(2025, 1, 15)
        pending = [f for f in flows if f.date > settlement]
        base_rate = 0.1025
        price = present_value(pending, settlement, base_rate)
        modified = modified_duration(flows, settlement, base_rate)

        # Una suba de 10 pb debería mover el precio aproximadamente
        # -duration_modificada * 0.001, con error de segundo orden acotado.
        shocked = present_value(pending, settlement, base_rate + 0.001)
        actual_change = (shocked - price) / price
        assert actual_change == pytest.approx(-modified * 0.001, rel=0.01)

    def test_amortizar_temprano_acorta_la_duration(self):
        settlement = date(2025, 1, 15)
        bullet = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        amortizing = build_cashflows(
            ISSUE, MATURITY, COUPON, FREQUENCY,
            ((date(2026, 1, 15), 50.0), (MATURITY, 50.0)),
        )
        assert macaulay_duration(amortizing, settlement, 0.1025) < macaulay_duration(bullet, settlement, 0.1025)

    def test_sin_flujos_pendientes_no_hay_duration(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert macaulay_duration(flows, date(2031, 1, 1), 0.10) is None
        assert modified_duration(flows, date(2031, 1, 1), 0.10) is None


class TestConvexity:
    def test_la_convexidad_es_positiva_en_un_bono_comun(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert convexity(flows, date(2025, 1, 15), 0.1025) > 0

    def test_mas_plazo_implica_mas_convexidad(self):
        settlement = date(2025, 1, 15)
        corto = build_cashflows(ISSUE, date(2027, 1, 15), COUPON, FREQUENCY)
        largo = build_cashflows(ISSUE, date(2035, 1, 15), COUPON, FREQUENCY)
        assert convexity(largo, settlement, 0.1025) > convexity(corto, settlement, 0.1025)


class TestWeightedAverageLife:
    def test_en_un_bullet_coincide_con_el_plazo_al_vencimiento(self):
        flows = build_cashflows(ISSUE, MATURITY, COUPON, FREQUENCY)
        assert weighted_average_life(flows, date(2025, 1, 15)) == pytest.approx(5.0, abs=0.02)

    def test_amortizar_en_cuotas_acorta_la_vida_promedio(self):
        flows = build_cashflows(
            ISSUE, MATURITY, COUPON, FREQUENCY,
            ((date(2026, 1, 15), 50.0), (MATURITY, 50.0)),
        )
        assert weighted_average_life(flows, date(2025, 1, 15)) == pytest.approx(3.0, abs=0.05)

    def test_sin_capital_por_cobrar_no_hay_vida_promedio(self):
        assert weighted_average_life([CashFlow(date(2026, 1, 1), 5.0, 0.0)], date(2025, 1, 1)) is None


class TestAnalyzeBond:
    def _analyze(self, **overrides):
        params = dict(
            issue_date=ISSUE,
            maturity=MATURITY,
            coupon_rate=COUPON,
            frequency=FREQUENCY,
            settlement=date(2025, 4, 15),
            price=100.0,
        )
        params.update(overrides)
        return analyze_bond(**params)

    def test_paridad_cien_cuando_el_precio_iguala_el_valor_tecnico(self):
        result = self._analyze(price=102.5)  # 100 de capital + 2.5 de interés corrido
        assert result["technical_value"] == pytest.approx(102.5)
        assert result["parity_pct"] == pytest.approx(100.0)

    def test_precio_sucio_y_limpio_difieren_en_el_interes_corrido(self):
        result = self._analyze(price=102.5)
        assert result["dirty_price"] == pytest.approx(102.5)
        assert result["clean_price"] == pytest.approx(100.0)

    def test_precio_limpio_suma_el_corrido_para_obtener_el_sucio(self):
        result = self._analyze(price=100.0, price_is_dirty=False)
        assert result["dirty_price"] == pytest.approx(102.5)
        assert result["clean_price"] == pytest.approx(100.0)

    def test_la_convencion_de_precio_cambia_la_tir(self):
        sucio = self._analyze(price=100.0, price_is_dirty=True)
        limpio = self._analyze(price=100.0, price_is_dirty=False)
        # Pagar 102.5 por el mismo flujo rinde menos que pagar 100.
        assert limpio["ytm_pct"] < sucio["ytm_pct"]

    def test_current_yield_es_cupon_sobre_precio(self):
        result = self._analyze(price=80.0)
        assert result["current_yield_pct"] == pytest.approx(10.0 / 80.0 * 100.0)

    def test_devuelve_metricas_vacias_sin_flujos_pendientes(self):
        result = self._analyze(settlement=date(2031, 1, 1))
        assert result["ytm_pct"] is None
        assert result["macaulay_duration"] is None
        assert result["years_to_maturity"] == pytest.approx(0.0)

    def test_nunca_devuelve_anios_al_vencimiento_negativos(self):
        assert self._analyze(settlement=date(2035, 1, 1))["years_to_maturity"] == 0.0
