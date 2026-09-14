"""
bonds/catalog.py - Catálogo de condiciones de emisión de las ONs.

Los precios de una ON se consiguen en vivo; **sus condiciones de emisión no**.
Ninguna fuente pública y gratuita publica, en formato consultable por máquina,
el cupón, el cronograma de amortización y la ley aplicable de cada obligación
negociable argentina: eso vive en el prospecto de emisión. Por eso el catálogo
es un archivo del repositorio (`data/ons_catalog.csv`) y no una descarga.

Consecuencia directa de diseño: **el catálogo es dato editable, no código**.
Cada fila trae una marca `verificado`; la interfaz muestra las no verificadas
con una advertencia explícita, porque un cupón equivocado no rompe nada, solo
devuelve una TIR mansamente incorrecta.

El parser es deliberadamente estricto y acumulativo: una fila inválida no
aborta la carga ni se ignora en silencio, se reporta con su número de línea y
el resto del catálogo sigue disponible.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

from bonds.bond_math import VALID_FREQUENCIES

logger = logging.getLogger(__name__)

# Ubicación del catálogo por defecto, relativa a la raíz del proyecto.
DEFAULT_CATALOG_PATH: Final[Path] = Path(__file__).resolve().parent.parent / "data" / "ons_catalog.csv"

# Separadores del cronograma de amortización: "fecha:porcentaje" separados por "|".
# Ej.: "2027-06-15:50|2028-06-15:50" (dos pagos de capital del 50% cada uno).
_AMORT_ENTRY_SEPARATOR: Final[str] = "|"
_AMORT_FIELD_SEPARATOR: Final[str] = ":"

# Tolerancia al validar que las amortizaciones sumen 100% del valor nominal.
# Existe para admitir cronogramas con decimales periódicos (33.33 + 33.33 +
# 33.34), no para tapar un cronograma mal cargado.
_AMORTIZATION_SUM_TOLERANCE: Final[float] = 0.05

# Jurisdicciones admitidas. La ley aplicable es una variable de riesgo real
# (dónde se litiga un default), no un dato descriptivo.
LAW_NEW_YORK: Final[str] = "NY"
LAW_ARGENTINA: Final[str] = "ARG"
VALID_LAWS: Final[tuple[str, ...]] = (LAW_NEW_YORK, LAW_ARGENTINA)

REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "ticker",
    "emisor",
    "sector",
    "moneda",
    "ley",
    "cupon_anual",
    "pagos_por_anio",
    "fecha_emision",
    "vencimiento",
    "amortizaciones",
    "lamina_minima",
    "calificacion",
    "verificado",
    "notas",
)


@dataclass(frozen=True)
class BondTerms:
    """Condiciones contractuales de una ON, tal como surgen de su prospecto."""

    ticker: str
    issuer: str
    sector: str
    currency: str
    law: str
    coupon_rate: float
    frequency: int
    issue_date: date
    maturity: date
    amortizations: tuple[tuple[date, float], ...]
    min_denomination: float | None
    rating: str
    verified: bool
    notes: str

    @property
    def is_bullet(self) -> bool:
        """True si devuelve todo el capital de una sola vez al vencimiento."""
        return len(self.amortizations) <= 1


def _parse_amortizations(raw: str, maturity: date, line: int) -> tuple[tuple[date, float], ...]:
    """
    Parsea el cronograma de amortización ("YYYY-MM-DD:pct|YYYY-MM-DD:pct").

    Un valor vacío significa *bullet* (100% al vencimiento) y se representa
    como una tupla vacía; `bond_math` aplica ese default al construir el flujo,
    de modo que el catálogo no tenga que repetir la fecha de vencimiento.
    """
    raw = (raw or "").strip()
    if not raw:
        return ()

    entries: list[tuple[date, float]] = []
    for chunk in raw.split(_AMORT_ENTRY_SEPARATOR):
        chunk = chunk.strip()
        if not chunk:
            continue
        if _AMORT_FIELD_SEPARATOR not in chunk:
            raise ValueError(f"línea {line}: tramo de amortización '{chunk}' sin formato fecha:porcentaje")
        raw_date, raw_pct = chunk.split(_AMORT_FIELD_SEPARATOR, 1)
        amort_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()
        pct = float(raw_pct.strip())
        if pct <= 0:
            raise ValueError(f"línea {line}: porcentaje de amortización no positivo en '{chunk}'")
        if amort_date > maturity:
            raise ValueError(f"línea {line}: amortización {amort_date} posterior al vencimiento {maturity}")
        entries.append((amort_date, pct))

    total = sum(pct for _, pct in entries)
    if abs(total - 100.0) > _AMORTIZATION_SUM_TOLERANCE:
        raise ValueError(f"línea {line}: las amortizaciones suman {total:.2f}%, deberían sumar 100%")
    return tuple(sorted(entries))


def _parse_bool(raw: str) -> bool:
    return (raw or "").strip().lower() in {"si", "sí", "s", "true", "1", "yes", "y"}


def _parse_row(row: dict[str, str], line: int) -> BondTerms:
    """Convierte una fila del CSV en BondTerms, validando cada campo."""
    ticker = (row.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError(f"línea {line}: falta el ticker")

    coupon_rate = float((row.get("cupon_anual") or "").strip())
    if coupon_rate < 0:
        raise ValueError(f"línea {line}: cupón anual negativo ({coupon_rate})")

    frequency = int((row.get("pagos_por_anio") or "").strip())
    if frequency not in VALID_FREQUENCIES:
        raise ValueError(f"línea {line}: pagos_por_anio={frequency} no soportado (esperado {VALID_FREQUENCIES})")

    issue_date = datetime.strptime((row.get("fecha_emision") or "").strip(), "%Y-%m-%d").date()
    maturity = datetime.strptime((row.get("vencimiento") or "").strip(), "%Y-%m-%d").date()
    if maturity <= issue_date:
        raise ValueError(f"línea {line}: vencimiento {maturity} anterior o igual a la emisión {issue_date}")

    law = (row.get("ley") or "").strip().upper()
    if law not in VALID_LAWS:
        raise ValueError(f"línea {line}: ley '{law}' no reconocida (esperado {VALID_LAWS})")

    raw_denomination = (row.get("lamina_minima") or "").strip()
    min_denomination = float(raw_denomination) if raw_denomination else None

    return BondTerms(
        ticker=ticker,
        issuer=(row.get("emisor") or "").strip() or ticker,
        sector=(row.get("sector") or "").strip() or "Sin clasificar",
        currency=(row.get("moneda") or "USD").strip().upper(),
        law=law,
        coupon_rate=coupon_rate,
        frequency=frequency,
        issue_date=issue_date,
        maturity=maturity,
        amortizations=_parse_amortizations(row.get("amortizaciones", ""), maturity, line),
        min_denomination=min_denomination,
        rating=(row.get("calificacion") or "").strip() or "s/c",
        verified=_parse_bool(row.get("verificado", "")),
        notes=(row.get("notas") or "").strip(),
    )


def load_catalog(path: Path | str | None = None) -> tuple[dict[str, BondTerms], list[str]]:
    """
    Carga el catálogo de ONs desde CSV.

    Devuelve `(terms_por_ticker, errores)`. Los errores son mensajes legibles y
    ya referidos a la línea del archivo: se muestran en la interfaz para que
    una fila mal cargada sea evidente y corregible, en vez de manifestarse como
    un bono que misteriosamente no aparece en el panel.

    Las líneas que empiezan con `#` se ignoran, lo que permite documentar el
    archivo desde adentro (un CSV sin contexto invita a editarlo mal).
    """
    catalog_path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    errors: list[str] = []

    if not catalog_path.exists():
        return {}, [f"No se encontró el catálogo de ONs en {catalog_path}"]

    try:
        raw_text = catalog_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("No se pudo leer el catálogo de ONs en %s", catalog_path)
        return {}, [f"No se pudo leer {catalog_path}: {exc}"]

    data_lines = [line for line in raw_text.splitlines() if not line.lstrip().startswith("#")]
    reader = csv.DictReader(data_lines)

    if reader.fieldnames is None:
        return {}, [f"{catalog_path} está vacío o no tiene encabezado"]

    missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        return {}, [f"{catalog_path}: faltan columnas obligatorias: {', '.join(missing)}"]

    terms: dict[str, BondTerms] = {}
    # El encabezado ocupa la primera línea de datos, por eso el offset de 2.
    for line_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        try:
            bond = _parse_row(row, line_number)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc) if "línea" in str(exc) else f"línea {line_number}: {exc}")
            continue
        if bond.ticker in terms:
            errors.append(f"línea {line_number}: ticker duplicado '{bond.ticker}', se conserva la primera aparición")
            continue
        terms[bond.ticker] = bond

    return terms, errors
