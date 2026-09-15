#!/usr/bin/env python3
"""
scripts/actualizar_calificaciones.py - Completa el archivo de calificaciones
con las notas vigentes que publica FIX SCR.

Se corre a mano cuando uno quiere, no desde el tablero. Así el tablero no
depende de un sitio de terceros para dibujar, cada cambio de nota queda en el
historial del repositorio —se puede ver quién bajó a quién y cuándo— y no se
consulta a la calificadora en cada carga de pantalla.

Uso:
    python3 scripts/actualizar_calificaciones.py            # muestra qué haría
    python3 scripts/actualizar_calificaciones.py --escribir # aplica los cambios

Lo que NO hace: tocar las entradas cargadas a mano. Si una entrada ya tiene
calificación y su origen no es este listado, se respeta y se informa. Alguien
la puso ahí leyendo un prospecto, y eso le gana a una tabla web.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Streamlit avisa que no hay runtime en cada función cacheada que se
# llama desde afuera de la app. Acá es esperado y no le dice nada a nadie.
logging.getLogger('streamlit').setLevel(logging.ERROR)

try:
    from bonds.fixscr_source import (  # noqa: E402
        FIXSCR_RATINGS_URL,
        FIXSCR_SOURCE_NAME,
        fetch_issuer_ratings,
    )
    from bonds.ratings import DEFAULT_RATINGS_PATH, normalize_issuer, rating_rank  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover
    print(f"Faltan dependencias del proyecto: {exc}")
    print("Instalalas con: pip install -r requirements.txt")
    raise SystemExit(1) from exc

# Marca de dónde vino cada nota. Sirve para distinguir lo cargado a mano de lo
# traído del listado, y para no pisar lo primero con lo segundo.
ORIGEN_LISTADO = "fixscr-listado"


def emisores_del_panel() -> list[str]:
    """
    Emisores que hoy aparecen en el cuadro de ONs.

    Se consulta el panel en vivo porque el archivo no se mantiene solo: cuando
    cambia qué bonos se muestran —se amplía un filtro, empieza a operar una ON
    nueva— aparecen emisores que el archivo no tiene, y el script no tendría
    forma de agregarlos. Pasó con CGC y Compañía Mega: FIX los califica, y no
    se cargaban porque no existía la entrada donde ponerlos.
    """
    from datetime import date

    from bonds.data_loader import load_bonds_data

    panel, _ = load_bonds_data(settlement=date.today(), price_is_dirty=True)
    if panel.empty:
        return []
    con_tir = panel[panel["TIR (%)"].notna()]
    return sorted({
        str(e).strip() for e in con_tir["Emisor"]
        if isinstance(e, str) and e.strip() and not e.startswith("—")
    })


def candidatos(emisor: str, disponibles: dict) -> list[str]:
    """
    Nombres del listado que podrían ser el mismo emisor.

    Existe porque la normalización no alcanza y no puede alcanzar: FIX escribe
    "Loma Negra C.I.A.S.A." donde BYMA dice "LOMA NEGRA COMPAÑIA INDUSTRIAL
    ARGENTINA SOCIEDAD ANONIMA". Ninguna regla convierte una en otra sin
    arriesgarse a unir emisores distintos, así que el script sugiere y la
    decisión de agregar el alias la toma una persona.

    El criterio es compartir la primera palabra significativa, que es la marca.
    """
    palabras = [p for p in normalize_issuer(emisor).split() if len(p) > 2]
    if not palabras:
        return []
    marca = palabras[0]
    return sorted(
        {r.issuer for clave, r in disponibles.items() if clave.split()[:1] == [marca]}
    )


def claves_de(entrada: dict) -> list[str]:
    """Todas las formas en que las fuentes de precios nombran a este emisor."""
    nombres = [entrada.get("emisor", ""), *(entrada.get("alias") or [])]
    return [k for k in (normalize_issuer(n) for n in nombres) if k]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--escribir", action="store_true",
                        help="Aplica los cambios; sin esto solo muestra qué haría")
    parser.add_argument("--archivo", default=None, help="Ruta del archivo de calificaciones")
    parser.add_argument("--sin-panel", action="store_true",
                        help="No consulta el panel para incorporar emisores nuevos")
    argumentos = parser.parse_args()

    destino = Path(argumentos.archivo) if argumentos.archivo else DEFAULT_RATINGS_PATH
    documento = json.loads(destino.read_text(encoding="utf-8"))
    entradas = documento.get("emisores", [])

    if not argumentos.sin_panel:
        print("⏳ Consultando el panel para ver si hay emisores nuevos…")
        try:
            del_panel = emisores_del_panel()
        except Exception as exc:  # noqa: BLE001 - el script sigue sin esto
            print(f"   ⚠️  No se pudo consultar el panel: {exc}")
            del_panel = []
        conocidos = {normalize_issuer(n) for e in entradas for n in claves_de(e)}
        agregados = 0
        for emisor in del_panel:
            if normalize_issuer(emisor) in conocidos:
                continue
            entradas.append({
                "emisor": emisor, "alias": [], "calificacion": "", "agencia": "",
                "escala": "", "fecha": "", "fuente": "", "verificado": False,
            })
            conocidos.add(normalize_issuer(emisor))
            agregados += 1
        if agregados:
            print(f"   {agregados} emisor(es) nuevo(s) incorporado(s) al archivo")

    print("⏳ Consultando el listado de FIX SCR…")
    vigentes, avisos = fetch_issuer_ratings()
    for aviso in avisos:
        print(f"   ⚠️  {aviso}")
    if not vigentes:
        return 1
    print(f"   {len(vigentes)} emisores con calificación vigente\n")

    por_clave = {normalize_issuer(r.issuer): r for r in vigentes.values()}

    nuevas, actualizadas, sin_cambio, respetadas, sin_cubrir = [], [], [], [], []
    for entrada in entradas:
        encontrada = next((por_clave[k] for k in claves_de(entrada) if k in por_clave), None)
        if encontrada is None:
            sin_cubrir.append(entrada["emisor"])
            continue

        tenia = (entrada.get("calificacion") or "").strip()
        origen = entrada.get("origen", "")
        if tenia and origen != ORIGEN_LISTADO:
            # Carga manual: gana sobre el listado.
            respetadas.append((entrada["emisor"], tenia, encontrada.rating))
            continue
        if tenia == encontrada.rating and entrada.get("fecha") == encontrada.as_of:
            sin_cambio.append(entrada["emisor"])
            continue

        (actualizadas if tenia else nuevas).append(
            (entrada["emisor"], tenia or "—", encontrada.rating, encontrada.as_of)
        )
        entrada.update(
            calificacion=encontrada.rating,
            agencia=FIXSCR_SOURCE_NAME,
            escala="nacional",
            fecha=encontrada.as_of,
            fuente=FIXSCR_RATINGS_URL,
            origen=ORIGEN_LISTADO,
            verificado=True,
        )

    print(f"✅ Nuevas ............ {len(nuevas)}")
    for emisor, _, nota, fecha in nuevas:
        print(f"     {emisor[:44]:46s} {nota:12s} {fecha}  (nivel {rating_rank(nota)})")
    if actualizadas:
        print(f"\n🔄 Actualizadas ...... {len(actualizadas)}")
        for emisor, antes, ahora, fecha in actualizadas:
            flecha = "↑" if (rating_rank(ahora) or 0) > (rating_rank(antes) or 0) else "↓"
            print(f"     {emisor[:40]:42s} {antes} {flecha} {ahora}  {fecha}")
    if sin_cambio:
        print(f"\n➖ Sin cambios ....... {len(sin_cambio)}")
    if respetadas:
        print(f"\n🔒 Cargadas a mano, no se tocan ... {len(respetadas)}")
        for emisor, manual, listado in respetadas:
            if manual != listado:
                print(f"     {emisor[:40]:42s} a mano {manual} · el listado dice {listado}")
    if sin_cubrir:
        con_candidato = [(e, candidatos(e, por_clave)) for e in sin_cubrir]
        sugeridos = [(e, c) for e, c in con_candidato if c]
        sin_nada = [e for e, c in con_candidato if not c]

        if sugeridos:
            print(f"\n🔎 Probablemente sean estos, con otro nombre ... {len(sugeridos)}")
            print("     Agregá el nombre del listado al campo 'alias' de la entrada y")
            print("     volvé a correr:")
            for emisor, cands in sugeridos:
                print(f"       {emisor[:44]:46s} -> {' | '.join(cands[:2])}")
        if sin_nada:
            print(f"\n❔ Sin calificación en este listado ... {len(sin_nada)}")
            print("     FIX SCR no los califica. Quedan para cargar a mano desde el")
            print("     informe de su calificadora:")
            for emisor in sin_nada:
                print(f"       {emisor}")

    cambios = len(nuevas) + len(actualizadas) + (
        len(entradas) - len(documento.get("emisores", []))
    )
    documento["emisores"] = entradas
    if not argumentos.escribir:
        print(f"\n(prueba: no se escribió nada. Con --escribir se aplican {cambios} cambios)")
        return 0
    if not cambios:
        print("\nNada para escribir.")
        return 0

    with destino.open("w", encoding="utf-8") as archivo:
        json.dump(documento, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
    print(f"\n💾 {destino.name} actualizado con {cambios} cambio(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
