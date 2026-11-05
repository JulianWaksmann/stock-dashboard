"""
cartera/lectura.py - Reconoce cada archivo subido y arma una sola cartera.

Puro: recibe nombres y bytes (y la serie del MEP, que baja otro), sin red ni
Streamlit.

El formato se decide por el **contenido**, no por el nombre del archivo: un
.xlsx se intenta leer como el reporte de Balanz y un texto que empieza con
"nroTicket;" es el export de movimientos de Cocos.

Dos reglas al juntar:

  * Los CSV de Cocos se leen **juntos** (uno por año): los lotes de una venta
    de enero pueden estar en el archivo del año anterior.
  * El reporte de Balanz es acumulado: trae toda la historia hasta la fecha
    en que se bajó. Dos reportes de Balanz contarían dos veces lo mismo, así
    que se usa el más reciente y se avisa.

Un archivo que no se puede leer no frena a los demás: se avisa y se sigue.
"""

from __future__ import annotations

import pandas as pd

from cartera.balanz import es_excel, leer_balanz
from cartera.cocos import es_cocos, leer_cocos
from cartera.modelo import Cartera, ExportInvalido, combinar


def leer_archivos(archivos: list[tuple[str, bytes]], serie_mep: pd.Series | None) -> tuple[Cartera, list[str]]:
    """`[(nombre, bytes), ...]` → cartera combinada y avisos para mostrar."""
    avisos: list[str] = []
    balanz: list[tuple[str, Cartera]] = []
    cocos: list[tuple[str, bytes]] = []

    for nombre, contenido in archivos:
        if es_cocos(contenido):
            cocos.append((nombre, contenido))
        elif es_excel(contenido):
            try:
                balanz.append((nombre, leer_balanz(contenido)))
            except ExportInvalido as exc:
                avisos.append(f"{nombre}: {exc}")
            except Exception:  # noqa: BLE001 - un archivo roto no tumba a los demás
                # Sin el detalle del error: puede traer valores del archivo.
                avisos.append(f"{nombre}: no pudimos leerlo. Descargalo de nuevo desde Balanz.")
        else:
            avisos.append(f"{nombre}: no es un export de Balanz ni de Cocos que sepamos leer.")

    carteras: list[Cartera] = []
    if balanz:
        balanz.sort(key=lambda x: x[1].fecha_corte)
        if len(balanz) > 1:
            avisos.append(
                f"Subiste {len(balanz)} reportes de Balanz. Cada uno trae toda la historia de su cuenta, así que "
                f"usamos solo el más reciente ({balanz[-1][0]}) para no contar dos veces lo mismo. Si son de cuentas "
                "distintas, mirá cada una por separado."
            )
        carteras.append(balanz[-1][1])
    if cocos:
        try:
            carteras.append(leer_cocos([c for _, c in cocos], serie_mep))
        except ExportInvalido as exc:
            avisos.append(f"Cocos: {exc}")
        except Exception:  # noqa: BLE001 - ver arriba
            avisos.append("Cocos: no pudimos leer los archivos. Descargalos de nuevo desde Cocos.")

    if not carteras:
        raise ExportInvalido(" ".join(avisos) or "No subiste ningún archivo que sepamos leer.")
    return combinar(carteras), avisos
