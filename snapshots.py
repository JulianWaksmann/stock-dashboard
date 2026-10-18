"""
snapshots.py - Registro diario de cada panel, para poder decir qué cambió.

El tablero es una foto: muestra el estado de hoy y no sabe nada de ayer. Pero
la pregunta que uno se hace al abrirlo no es "qué dice el semáforo", es **qué
cambió desde la última vez que mir**é. Sin memoria, eso hay que recordarlo de
cabeza.

Cómo funciona, y por qué así:

  * **Un archivo por día y por motor**, en `data/snapshots/<motor>/<fecha>.csv`.
    CSV y no parquet porque son unos pocos kilobytes por día y así se puede
    abrir con cualquier cosa, incluida una terminal.
  * **Se escribe una vez por día.** El primero que mira el panel ese día lo
    graba; los que miran después no lo reescriben. Es lo que vuelve
    comparables dos días: si cada recarga sobreescribiera el archivo, el
    "cambio desde ayer" dependería de a qué hora miró cada uno. La
    consecuencia es que la foto del día es la de la primera consulta, no la del
    cierre, y está declarado en pantalla.
  * **La comparación es contra el último archivo anterior**, no contra "ayer":
    si el tablero no se abrió el viernes, el lunes se compara contra el jueves,
    y se informa contra qué fecha se está comparando.

El comparador es puro y no toca el disco. La escritura y la lectura son I/O de
archivos, sin red y sin Streamlit, así que los scripts pueden grabar el
registro desde la terminal (por ejemplo, desde una tarea programada) y la
interfaz solo lo lee.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("data") / "snapshots"

# Columnas que se guardan si están en el panel. Es a propósito un puñado: el
# registro sirve para comparar estado, no para reconstruir el cuadro entero, y
# un CSV de treinta columnas por día deja de ser legible.
DEFAULT_COLUMNS = (
    "Ticker",
    "Semáforo",
    "Atractivo",
    "Empresa",
    "Cripto",
    "Precio Actual",
    "PRECIO_VAL",
    "Precio",
    "RSI_VAL",
    "DIFF_SMA_200_VAL",
    "Flujo Institucional",
    "TIR (%)",
)

COL_TICKER = "Ticker"


@dataclass(frozen=True)
class PanelChanges:
    """
    Qué cambió entre dos fotos del mismo panel.

    `señales` es lo que importa: los activos cuyo semáforo pasó de un estado a
    otro. `nuevos` y `salidos` son los que aparecieron o desaparecieron del
    panel, que casi siempre es un problema de datos y no una novedad del
    mercado, así que conviene verlos separados de los cambios de señal.
    """

    fecha_anterior: date | None = None
    señales: pd.DataFrame = field(default_factory=pd.DataFrame)
    movimientos: pd.DataFrame = field(default_factory=pd.DataFrame)
    nuevos: tuple[str, ...] = ()
    salidos: tuple[str, ...] = ()

    @property
    def hay_cambios(self) -> bool:
        return bool(len(self.señales) or len(self.nuevos) or len(self.salidos))


def _directorio(motor: str, directorio: Path | str = SNAPSHOT_DIR) -> Path:
    return Path(directorio) / motor


def _columnas_a_guardar(df: pd.DataFrame, columnas: tuple[str, ...]) -> list[str]:
    return [c for c in columnas if c in df.columns]


def save_snapshot(
    df: pd.DataFrame,
    motor: str,
    fecha: date | None = None,
    columnas: tuple[str, ...] = DEFAULT_COLUMNS,
    directorio: Path | str = SNAPSHOT_DIR,
) -> Path | None:
    """
    Graba la foto del día, si todavía no está grabada.

    Devuelve la ruta cuando efectivamente escribió, y `None` cuando no había
    nada que escribir o el archivo del día ya existía. Nunca sobreescribe: la
    foto del día es la de la primera consulta (ver el docstring del módulo).

    Un error de escritura se registra y se traga: el tablero tiene que seguir
    funcionando en un directorio sin permisos, porque el registro es una
    comodidad, no el producto.
    """
    if df is None or df.empty or COL_TICKER not in df.columns:
        return None

    fecha = fecha or date.today()
    destino = _directorio(motor, directorio) / f"{fecha:%Y-%m-%d}.csv"
    if destino.exists():
        return None

    guardables = _columnas_a_guardar(df, columnas)
    if COL_TICKER not in guardables:
        return None

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        df[guardables].to_csv(destino, index=False)
    except OSError:
        logger.warning("No se pudo guardar el registro diario en %s", destino, exc_info=True)
        return None

    return destino


def available_snapshots(motor: str, directorio: Path | str = SNAPSHOT_DIR) -> list[date]:
    """Fechas con foto guardada, de la más vieja a la más nueva."""
    carpeta = _directorio(motor, directorio)
    if not carpeta.is_dir():
        return []

    fechas = []
    for archivo in carpeta.glob("*.csv"):
        try:
            fechas.append(date.fromisoformat(archivo.stem))
        except ValueError:
            continue
    return sorted(fechas)


def load_snapshot(
    motor: str,
    fecha: date,
    directorio: Path | str = SNAPSHOT_DIR,
) -> pd.DataFrame:
    """Lee una foto puntual; devuelve un DataFrame vacío si no se puede leer."""
    archivo = _directorio(motor, directorio) / f"{fecha:%Y-%m-%d}.csv"
    try:
        return pd.read_csv(archivo)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        logger.warning("No se pudo leer el registro %s", archivo, exc_info=True)
        return pd.DataFrame()


def previous_snapshot(
    motor: str,
    fecha: date | None = None,
    directorio: Path | str = SNAPSHOT_DIR,
) -> tuple[date, pd.DataFrame] | None:
    """
    La última foto anterior a `fecha`, con su fecha.

    "Anterior" y no "de ayer": si el tablero no se abrió el viernes, el lunes
    se compara contra el jueves. Devolver la fecha es parte del resultado,
    porque un cambio "desde ayer" que en realidad es desde la semana pasada se
    lee distinto.
    """
    fecha = fecha or date.today()
    anteriores = [f for f in available_snapshots(motor, directorio) if f < fecha]
    if not anteriores:
        return None

    ultima = anteriores[-1]
    return ultima, load_snapshot(motor, ultima, directorio)


def compare_snapshots(
    anterior: pd.DataFrame,
    actual: pd.DataFrame,
    columna_senal: str = "Semáforo",
    columna_precio: str = "Precio Actual",
    fecha_anterior: date | None = None,
) -> PanelChanges:
    """
    Compara dos fotos del mismo panel. Puro: no toca el disco.

    `columna_senal` y `columna_precio` se parametrizan porque los tres motores
    nombran distinto lo mismo: acciones y cripto tienen `"Semáforo"`, el panel
    de ONs tiene `"Atractivo"`. El algoritmo es uno.
    """
    if actual is None or actual.empty or COL_TICKER not in actual.columns:
        return PanelChanges(fecha_anterior=fecha_anterior)
    if anterior is None or anterior.empty or COL_TICKER not in anterior.columns:
        return PanelChanges(fecha_anterior=fecha_anterior)

    antes = anterior.drop_duplicates(COL_TICKER).set_index(COL_TICKER)
    ahora = actual.drop_duplicates(COL_TICKER).set_index(COL_TICKER)

    comunes = ahora.index.intersection(antes.index)
    nuevos = tuple(sorted(str(t) for t in ahora.index.difference(antes.index)))
    salidos = tuple(sorted(str(t) for t in antes.index.difference(ahora.index)))

    señales = pd.DataFrame(columns=[COL_TICKER, "Antes", "Ahora"])
    if columna_senal in antes.columns and columna_senal in ahora.columns:
        viejas = antes.loc[comunes, columna_senal].astype(str)
        nuevas = ahora.loc[comunes, columna_senal].astype(str)
        cambiaron = comunes[(viejas != nuevas).to_numpy()]
        señales = pd.DataFrame({
            COL_TICKER: [str(t) for t in cambiaron],
            "Antes": viejas.loc[cambiaron].to_numpy(),
            "Ahora": nuevas.loc[cambiaron].to_numpy(),
        })

    movimientos = pd.DataFrame(columns=[COL_TICKER, "Antes", "Ahora", "Var. (%)"])
    if columna_precio in antes.columns and columna_precio in ahora.columns:
        precio_antes = pd.to_numeric(antes.loc[comunes, columna_precio], errors="coerce")
        precio_ahora = pd.to_numeric(ahora.loc[comunes, columna_precio], errors="coerce")
        variacion = (precio_ahora / precio_antes.replace(0, np.nan) - 1.0) * 100.0
        movimientos = (
            pd.DataFrame({
                COL_TICKER: [str(t) for t in comunes],
                "Antes": precio_antes.to_numpy(),
                "Ahora": precio_ahora.to_numpy(),
                "Var. (%)": variacion.to_numpy(),
            })
            .dropna(subset=["Var. (%)"])
            .sort_values("Var. (%)", key=abs, ascending=False)
            .reset_index(drop=True)
        )

    return PanelChanges(
        fecha_anterior=fecha_anterior,
        señales=señales,
        movimientos=movimientos,
        nuevos=nuevos,
        salidos=salidos,
    )


def record_and_compare(
    df: pd.DataFrame,
    motor: str,
    columna_senal: str = "Semáforo",
    columna_precio: str = "Precio Actual",
    fecha: date | None = None,
    directorio: Path | str = SNAPSHOT_DIR,
) -> PanelChanges:
    """
    Graba la foto del día (si falta) y devuelve qué cambió contra la anterior.

    El orden importa: primero se busca la foto anterior y después se graba la
    de hoy. Al revés, el primer día el panel se compararía consigo mismo.
    """
    previa = previous_snapshot(motor, fecha=fecha, directorio=directorio)
    save_snapshot(df, motor, fecha=fecha, directorio=directorio)

    if previa is None:
        return PanelChanges()

    fecha_anterior, anterior = previa
    return compare_snapshots(
        anterior,
        df,
        columna_senal=columna_senal,
        columna_precio=columna_precio,
        fecha_anterior=fecha_anterior,
    )
