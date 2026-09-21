"""
Tests del reparto de etiquetas del gráfico (`components/crypto_chart`).

Es lógica pura de layout —entra una lista de precios, sale un
desplazamiento por cada uno— y se testea sola, sin dibujar nada.
"""

import pytest

from components.crypto_chart import repartir_etiquetas


def alturas_finales(precios, piso, techo, alto_px, separacion_px):
    """Dónde queda cada etiqueta, en píxeles, después del reparto."""
    escala = alto_px / (techo - piso)
    corrimientos = repartir_etiquetas(precios, piso, techo, alto_px, separacion_px)
    return [(p - piso) * escala + c for p, c in zip(precios, corrimientos, strict=True)]


class TestRepartoDeEtiquetas:
    def test_no_mueve_lo_que_ya_esta_separado(self):
        # Tres niveles bien espaciados no necesitan corrección.
        assert repartir_etiquetas([100.0, 200.0, 300.0], 0, 400, 400, 30) == [0.0, 0.0, 0.0]

    def test_separa_las_etiquetas_que_se_pisan(self):
        # Tres niveles a 2 px de distancia: sin reparto, un solo borrón.
        precios = [100.0, 102.0, 104.0]
        finales = alturas_finales(precios, 0, 400, 400, separacion_px=30)
        distancias = [abs(a - b) for a, b in zip(finales, finales[1:], strict=False)]
        assert all(d >= 29.9 for d in distancias)

    def test_la_etiqueta_mas_alta_se_queda_en_su_lugar(self):
        # El reparto empuja hacia abajo: la de arriba es la referencia y no
        # se mueve, así que el bloque nunca se va del cuadro por arriba.
        corrimientos = repartir_etiquetas([100.0, 101.0, 102.0], 0, 400, 400, 30)
        assert corrimientos[2] == 0.0

    def test_solo_empuja_hacia_abajo(self):
        corrimientos = repartir_etiquetas([100.0, 101.0, 102.0], 0, 400, 400, 30)
        assert all(c <= 0 for c in corrimientos)

    def test_devuelve_un_corrimiento_por_precio_y_en_el_mismo_orden(self):
        # El orden importa: el llamador los aparea con su nivel.
        precios = [300.0, 100.0, 200.0]
        corrimientos = repartir_etiquetas(precios, 0, 400, 400, 30)
        assert len(corrimientos) == 3
        assert corrimientos[0] == 0.0  # el más alto no se mueve

    @pytest.mark.parametrize(
        "piso,techo,alto",
        [(0, 0, 400), (100, 50, 400), (0, 400, 0)],
    )
    def test_un_rango_degenerado_no_rompe(self, piso, techo, alto):
        assert repartir_etiquetas([100.0, 101.0], piso, techo, alto, 30) == [0.0, 0.0]

    def test_sin_etiquetas_no_devuelve_nada(self):
        assert repartir_etiquetas([], 0, 400, 400, 30) == []
