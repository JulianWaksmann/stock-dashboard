"""
bonds/bond_math.py - Matemática financiera de renta fija.

Todo lo que este módulo calcula sale de una única fuente: el **flujo de fondos
contractual** del bono (cuándo paga intereses, cuándo devuelve capital y cuánto).
A partir de ese flujo y de un precio de mercado se derivan TIR, duration,
paridad y el resto de las métricas que la pestaña de Bonos muestra.

Convenciones adoptadas (explícitas porque cambian los resultados):

  * **Base 100 de valor nominal original.** Todos los importes son "por cada
    100 VN emitidos". Es la convención de cotización local: el precio de
    pantalla de una ON se lee contra 100 nominales.
  * **Interés corrido: 30/360.** Es la base usual de las ONs corporativas en
    dólares. Solo afecta al devengamiento intra-cupón (interés corrido, valor
    técnico y paridad), no al descuento.
  * **Descuento: ACT/365 con capitalización anual.** La TIR que se devuelve es
    una tasa **efectiva anual**, comparable de forma directa entre bonos con
    distinta frecuencia de pago (que es justamente para lo que se la usa).
  * **Cupón único.** No se modelan cupones escalonados (step-up) ni tasas
    variables (Badlar/TAMAR/CER). El catálogo describe tasa fija; un bono a
    tasa variable cargado acá daría una TIR sin sentido económico.

Ninguna función de este módulo toca la red ni Streamlit: es aritmética pura y
determinista, para que la suite de tests pueda verificarla contra casos con
resultado conocido.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Final

# Base de cálculo: todos los importes se expresan por cada 100 VN originales.
FACE_VALUE: Final[float] = 100.0

# Frecuencias de pago admitidas (pagos por año). Cualquier otro valor no
# divide en meses enteros el año y produciría fechas de cupón inconsistentes.
VALID_FREQUENCIES: Final[tuple[int, ...]] = (1, 2, 4, 12)

# Cota de seguridad al generar el cronograma hacia atrás desde el vencimiento:
# 12 pagos por año durante 60 años. Existe solo para que una fecha de emisión
# corrupta en el CSV no genere un bucle infinito.
_MAX_COUPON_PERIODS: Final[int] = 720

# Rango de búsqueda de la TIR por bisección, en tasa efectiva anual decimal.
# El piso es casi -100% (pérdida total) y el techo 1000%: cubre desde un bono
# en default cotizando centavos hasta cualquier rendimiento realista.
_YTM_LOWER_BOUND: Final[float] = -0.9999
_YTM_UPPER_BOUND: Final[float] = 10.0
_YTM_ITERATIONS: Final[int] = 200

# Días por año usados para expresar los plazos al descontar (ACT/365).
DAYS_PER_YEAR: Final[float] = 365.0


@dataclass(frozen=True)
class CashFlow:
    """
    Un pago del bono, expresado por cada 100 VN originales.

    `split_known` distingue las dos formas en que puede llegar un flujo. Cuando
    se reconstruye desde las condiciones de emisión se sabe qué parte del pago
    es renta y qué parte devolución de capital. Cuando la fuente publica
    directamente el cronograma ya resuelto, muchas veces solo informa el total
    del pago; entonces el importe se guarda entero y la bandera queda en False,
    para que las métricas que dependen del capital (vida promedio, paridad) se
    abstengan en vez de responder sobre un supuesto inventado.
    """

    date: date
    interest: float
    amortization: float
    split_known: bool = True

    @property
    def total(self) -> float:
        return self.interest + self.amortization

    @classmethod
    def unsplit(cls, flow_date: date, amount: float) -> CashFlow:
        """Construye un pago del que solo se conoce el importe total."""
        return cls(date=flow_date, interest=amount, amortization=0.0, split_known=False)


def add_months(reference: date, months: int) -> date:
    """
    Desplaza una fecha una cantidad de meses (positiva o negativa).

    Si el día no existe en el mes destino (por ejemplo, el 31 de marzo movido
    a febrero) se recorta al último día de ese mes, que es como trabajan los
    cronogramas de pago reales.
    """
    total_months = reference.month - 1 + months
    year = reference.year + total_months // 12
    month = total_months % 12 + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def days_30_360(start: date, end: date) -> int:
    """
    Días entre dos fechas según la base 30/360 (convención US/NASD).

    Cada mes vale 30 días y cada año 360. Es la base con la que se devenga el
    interés corrido de las ONs en dólares.
    """
    d1, d2 = start.day, end.day
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 == 30:
        d2 = 30
    return (end.year - start.year) * 360 + (end.month - start.month) * 30 + (d2 - d1)


def year_fraction(start: date, end: date) -> float:
    """Plazo en años entre dos fechas, base ACT/365 (la usada para descontar)."""
    return (end - start).days / DAYS_PER_YEAR


def generate_coupon_dates(issue_date: date, maturity: date, frequency: int) -> list[date]:
    """
    Reconstruye las fechas de pago de cupón del bono.

    Se generan **hacia atrás desde el vencimiento**, no hacia adelante desde la
    emisión: el último cupón siempre cae exactamente el día del vencimiento, y
    arrastrar el día del mes desde la fecha de emisión (que puede ser un 31)
    desalinearía todo el cronograma. Se descartan las fechas anteriores o
    iguales a la emisión.
    """
    if frequency not in VALID_FREQUENCIES:
        raise ValueError(f"Frecuencia de pago no soportada: {frequency} (esperado {VALID_FREQUENCIES})")
    if maturity <= issue_date:
        raise ValueError("El vencimiento debe ser posterior a la fecha de emisión")

    step_months = 12 // frequency
    dates: list[date] = []
    for k in range(_MAX_COUPON_PERIODS):
        coupon_date = add_months(maturity, -step_months * k)
        if coupon_date <= issue_date:
            break
        dates.append(coupon_date)
    return sorted(dates)


def _normalize_amortizations(
    amortizations: tuple[tuple[date, float], ...] | None,
    maturity: date,
) -> tuple[tuple[date, float], ...]:
    """
    Devuelve el cronograma de amortización, aplicando el default *bullet*.

    Un cronograma vacío significa "bullet": el 100% del capital se devuelve de
    una sola vez al vencimiento, que es la estructura más común en las ONs
    corporativas argentinas en dólares.
    """
    if not amortizations:
        return ((maturity, FACE_VALUE),)
    return tuple(sorted(amortizations))


def residual_capital(
    amortizations: tuple[tuple[date, float], ...] | None,
    maturity: date,
    reference: date,
) -> float:
    """
    Capital todavía no amortizado a una fecha dada ("capital residual").

    Es la base sobre la que se calculan los cupones siguientes: un bono que ya
    devolvió la mitad del capital paga, en pesos o dólares, la mitad de cupón
    aunque su tasa nominal no haya cambiado.
    """
    schedule = _normalize_amortizations(amortizations, maturity)
    paid = sum(pct for amort_date, pct in schedule if amort_date <= reference)
    return max(FACE_VALUE - paid, 0.0)


def build_cashflows(
    issue_date: date,
    maturity: date,
    coupon_rate: float,
    frequency: int,
    amortizations: tuple[tuple[date, float], ...] | None = None,
) -> list[CashFlow]:
    """
    Construye el flujo de fondos completo del bono, desde la emisión hasta el
    vencimiento, por cada 100 VN originales.

    El interés de cada cupón se calcula sobre el capital residual *previo* a
    ese pago: la amortización que se cobra el mismo día todavía devengó interés
    durante el período que cierra.
    """
    coupon_dates = generate_coupon_dates(issue_date, maturity, frequency)
    schedule = _normalize_amortizations(amortizations, maturity)

    amortization_by_date: dict[date, float] = {}
    for amort_date, pct in schedule:
        amortization_by_date[amort_date] = amortization_by_date.get(amort_date, 0.0) + pct

    coupon_dates_set = set(coupon_dates)
    flows: list[CashFlow] = []
    for flow_date in sorted(coupon_dates_set | set(amortization_by_date)):
        outstanding = FACE_VALUE - sum(pct for d, pct in schedule if d < flow_date)
        interest = 0.0
        if flow_date in coupon_dates_set:
            interest = max(outstanding, 0.0) * (coupon_rate / 100.0) / frequency
        flows.append(
            CashFlow(
                date=flow_date,
                interest=interest,
                amortization=amortization_by_date.get(flow_date, 0.0),
            )
        )
    return flows


def accrued_interest(
    issue_date: date,
    maturity: date,
    coupon_rate: float,
    frequency: int,
    settlement: date,
    amortizations: tuple[tuple[date, float], ...] | None = None,
) -> float:
    """
    Interés corrido a la fecha de liquidación, base 30/360.

    Es la porción del próximo cupón que el vendedor ya devengó y que el
    comprador le paga por encima del precio limpio. Vencido el bono (o pasado
    el último cupón) no hay nada que devengar y devuelve 0.
    """
    # Antes de la emisión no hay nada devengado. Sin esta guarda, el
    # devengamiento 30/360 sale negativo y arrastra al valor técnico, con lo
    # cual un bono a precio 100 puede mostrar paridad de 106%.
    if settlement <= issue_date:
        return 0.0

    coupon_dates = generate_coupon_dates(issue_date, maturity, frequency)
    future_coupons = [d for d in coupon_dates if d > settlement]
    if not future_coupons:
        return 0.0

    next_coupon = future_coupons[0]
    past_coupons = [d for d in coupon_dates if d <= settlement]
    accrual_start = past_coupons[-1] if past_coupons else issue_date

    schedule = _normalize_amortizations(amortizations, maturity)
    outstanding = FACE_VALUE - sum(pct for d, pct in schedule if d < next_coupon)
    full_coupon = max(outstanding, 0.0) * (coupon_rate / 100.0) / frequency

    elapsed = days_30_360(accrual_start, settlement)
    period = days_30_360(accrual_start, next_coupon)
    if period <= 0:
        return 0.0
    return full_coupon * elapsed / period


def remaining_cashflows(flows: list[CashFlow], settlement: date) -> list[CashFlow]:
    """Flujos pendientes de cobro: los estrictamente posteriores a la liquidación."""
    return [flow for flow in flows if flow.date > settlement]


def present_value(flows: list[CashFlow], settlement: date, rate: float) -> float:
    """Valor presente de un flujo a una tasa efectiva anual dada (decimal)."""
    total = 0.0
    for flow in flows:
        exponent = year_fraction(settlement, flow.date)
        total += flow.total / (1.0 + rate) ** exponent
    return total


def yield_to_maturity(flows: list[CashFlow], settlement: date, dirty_price: float) -> float | None:
    """
    TIR (tasa interna de retorno) efectiva anual que iguala el valor presente
    del flujo pendiente al precio sucio pagado.

    Se resuelve por bisección y no por Newton-Raphson: el valor presente es
    estrictamente decreciente en la tasa, así que la bisección converge siempre
    dentro del intervalo y no depende de una semilla ni puede divergir con
    precios extremos (un bono en default cotizando a 5).

    Devuelve `None` cuando no hay solución dentro del rango razonable de tasas
    (precio no positivo, sin flujos pendientes, o un precio tan bajo/alto que
    implicaría una TIR fuera de [-99.99%, 1000%]).
    """
    pending = remaining_cashflows(flows, settlement)
    if not pending or dirty_price is None or dirty_price <= 0:
        return None

    low, high = _YTM_LOWER_BOUND, _YTM_UPPER_BOUND
    pv_low = present_value(pending, settlement, low)
    pv_high = present_value(pending, settlement, high)

    # El precio queda fuera del rango de tasas que estamos dispuestos a reportar.
    if dirty_price > pv_low or dirty_price < pv_high:
        return None

    for _ in range(_YTM_ITERATIONS):
        mid = (low + high) / 2.0
        pv_mid = present_value(pending, settlement, mid)
        if pv_mid > dirty_price:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def macaulay_duration(flows: list[CashFlow], settlement: date, rate: float) -> float | None:
    """
    Duration de Macaulay en años: plazo promedio de cobro del bono, ponderado
    por el valor presente de cada pago.

    Es el "centro de gravedad" temporal del flujo. Un bono bullet largo tiene
    duration alta; uno que amortiza temprano, mucho más baja aunque venzan el
    mismo día.
    """
    pending = remaining_cashflows(flows, settlement)
    if not pending:
        return None

    weighted_sum = 0.0
    pv_total = 0.0
    for flow in pending:
        years = year_fraction(settlement, flow.date)
        pv = flow.total / (1.0 + rate) ** years
        weighted_sum += years * pv
        pv_total += pv
    if pv_total <= 0:
        return None
    return weighted_sum / pv_total


def modified_duration(flows: list[CashFlow], settlement: date, rate: float) -> float | None:
    """
    Duration modificada: variación porcentual aproximada del precio ante una
    suba de 1 punto porcentual en la tasa de descuento.

    Es la medida directa de riesgo de tasa: duration modificada 4 significa que
    si el rendimiento exigido sube 1 pp, el precio cae aproximadamente 4%.
    """
    macaulay = macaulay_duration(flows, settlement, rate)
    if macaulay is None or rate <= -1.0:
        return None
    return macaulay / (1.0 + rate)


def convexity(flows: list[CashFlow], settlement: date, rate: float) -> float | None:
    """
    Convexidad: curvatura de la relación precio/tasa, es decir el error que
    deja la duration sola.

    A igual duration, más convexidad es preferible: el precio sube más de lo
    que la duration anticipa cuando las tasas bajan, y cae menos cuando suben.
    """
    pending = remaining_cashflows(flows, settlement)
    if not pending or rate <= -1.0:
        return None

    weighted_sum = 0.0
    pv_total = 0.0
    for flow in pending:
        years = year_fraction(settlement, flow.date)
        pv = flow.total / (1.0 + rate) ** years
        weighted_sum += years * (years + 1.0) * pv
        pv_total += pv
    if pv_total <= 0:
        return None
    return weighted_sum / (pv_total * (1.0 + rate) ** 2)


def weighted_average_life(flows: list[CashFlow], settlement: date) -> float | None:
    """
    Vida promedio (WAL) en años: plazo promedio de devolución del **capital**,
    sin descontar y sin contar los cupones.

    Responde "¿en cuánto tiempo recupero el capital?", que en un bono con
    amortizaciones parciales puede ser mucho menos que el plazo al vencimiento.
    """
    pending = remaining_cashflows(flows, settlement)
    # Sin el desglose renta/capital no se puede decir cuándo vuelve el capital,
    # que es exactamente lo que esta métrica mide.
    if any(not flow.split_known for flow in pending):
        return None
    total_amortization = sum(flow.amortization for flow in pending)
    if total_amortization <= 0:
        return None
    weighted = sum(year_fraction(settlement, flow.date) * flow.amortization for flow in pending)
    return weighted / total_amortization


def analyze_cashflows(flows: list[CashFlow], settlement: date, dirty_price: float) -> dict:
    """
    Métricas que se derivan únicamente del flujo total y el precio pagado.

    Es el núcleo compartido entre las dos formas de conocer un bono: a partir
    de sus condiciones de emisión, o a partir de un cronograma de pagos ya
    resuelto publicado por un tercero. Rendimiento y sensibilidad a la tasa no
    necesitan saber qué parte de cada pago es renta y qué parte capital.
    """
    ytm = yield_to_maturity(flows, settlement, dirty_price)
    return {
        "ytm_pct": ytm * 100.0 if ytm is not None else None,
        "macaulay_duration": macaulay_duration(flows, settlement, ytm) if ytm is not None else None,
        "modified_duration": modified_duration(flows, settlement, ytm) if ytm is not None else None,
        "convexity": convexity(flows, settlement, ytm) if ytm is not None else None,
        "weighted_average_life": weighted_average_life(flows, settlement),
        "cashflows": flows,
    }


def analyze_bond(
    *,
    issue_date: date,
    maturity: date,
    coupon_rate: float,
    frequency: int,
    settlement: date,
    price: float,
    amortizations: tuple[tuple[date, float], ...] | None = None,
    price_is_dirty: bool = True,
) -> dict:
    """
    Calcula de una sola pasada todas las métricas de un bono.

    `price_is_dirty` describe qué convención sigue el precio de pantalla:
      - `True` (default): el precio ya incluye el interés corrido. Es la
        convención local de BYMA para renta fija.
      - `False`: el precio es "limpio" y hay que sumarle el interés corrido
        para obtener lo que realmente se desembolsa.

    Elegir mal esta convención sesga la TIR y la paridad, por eso es un
    parámetro explícito y no un supuesto enterrado en el cálculo.

    Devuelve un diccionario con `None` en las métricas que no se pueden
    calcular, nunca una excepción por datos incompletos.
    """
    flows = build_cashflows(issue_date, maturity, coupon_rate, frequency, amortizations)
    accrued = accrued_interest(issue_date, maturity, coupon_rate, frequency, settlement, amortizations)
    outstanding = residual_capital(amortizations, maturity, settlement)
    technical_value = outstanding + accrued

    dirty_price = price if price_is_dirty else price + accrued
    clean_price = price - accrued if price_is_dirty else price

    parity = (dirty_price / technical_value * 100.0) if technical_value > 0 else None
    # La renta anual se mide contra el precio LIMPIO. Dividir por el sucio
    # mete el interés corrido en el denominador, así que el mismo bono mostraría
    # una renta que baja a lo largo del período de cupón y salta el día que
    # paga, sin que haya cambiado nada del bono.
    annual_coupon = outstanding * (coupon_rate / 100.0)
    current_yield = (annual_coupon / clean_price * 100.0) if clean_price > 0 else None

    return {
        **analyze_cashflows(flows, settlement, dirty_price),
        "current_yield_pct": current_yield,
        "accrued_interest": accrued,
        "residual_capital": outstanding,
        "technical_value": technical_value,
        "parity_pct": parity,
        "dirty_price": dirty_price,
        "clean_price": clean_price,
        "years_to_maturity": max(year_fraction(settlement, maturity), 0.0),
    }
