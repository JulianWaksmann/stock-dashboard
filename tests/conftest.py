"""
Fixtures compartidas para la suite de tests de indicators.py.

Todas las series/DataFrames sintéticos usan una semilla fija para que la
suite sea determinista entre corridas.
"""

import numpy as np
import pandas as pd
import pytest

SEED = 20240101


@pytest.fixture
def rng():
    """Generador aleatorio con semilla fija para reproducibilidad."""
    return np.random.default_rng(SEED)


@pytest.fixture
def rising_series():
    """Serie estrictamente creciente (usada para el caso RSI = 100)."""
    return pd.Series(np.arange(1, 60, dtype=float))


@pytest.fixture
def falling_series():
    """Serie estrictamente decreciente."""
    return pd.Series(np.arange(60, 1, -1, dtype=float))


@pytest.fixture
def flat_series():
    """Serie perfectamente plana (sin variación día a día)."""
    return pd.Series([100.0] * 60)


@pytest.fixture
def random_walk_series(rng):
    """Serie de precios tipo random walk, 300 barras, siempre positiva."""
    steps = rng.normal(loc=0.0, scale=1.0, size=300)
    prices = 100.0 + np.cumsum(steps)
    # Evitamos precios negativos o nulos para que los indicadores basados
    # en porcentajes tengan sentido económico.
    prices = np.clip(prices, 1.0, None)
    return pd.Series(prices)


@pytest.fixture
def random_ohlcv_df(rng, random_walk_series):
    """DataFrame OHLCV sintético construido a partir de random_walk_series."""
    close = random_walk_series
    high = close + rng.uniform(0.0, 1.5, size=len(close))
    low = close - rng.uniform(0.0, 1.5, size=len(close))
    volume = rng.integers(1000, 100_000, size=len(close)).astype(float)
    return pd.DataFrame({
        'Open': close.shift(1).fillna(close.iloc[0]),
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    })


@pytest.fixture
def series_100_bars():
    """Serie de 100 barras (más corta que un período de 200)."""
    return pd.Series(np.linspace(50.0, 150.0, 100))


@pytest.fixture
def series_250_bars():
    """Serie de 250 barras (más larga que un período de 200)."""
    return pd.Series(np.linspace(50.0, 300.0, 250))
