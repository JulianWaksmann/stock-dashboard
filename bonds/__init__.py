"""
bonds - Módulo de análisis de renta fija corporativa argentina (Obligaciones
Negociables).

Se separa del motor de acciones (`indicators.py` / `data_loader.py`) porque la
lógica es de otra naturaleza: un bono no se evalúa con osciladores de precio
sino con el valor presente de su flujo de fondos contractual (cupones +
amortizaciones). Comparten el dashboard, no el modelo de datos.

Submódulos:
  - `bond_math`: matemática financiera pura (flujo de fondos, TIR, duration,
    paridad). Sin dependencias de red ni de Streamlit, para poder testearse.
  - `catalog`: lectura y validación del catálogo de condiciones de emisión
    (`data/ons_catalog.csv`), que es el único lugar donde viven cupón,
    vencimiento y cronograma de amortización de cada ON.
  - `scoring`: traducción de las métricas a una etiqueta de atractivo
    ("semáforo"), análoga al sistema de grados del panel de acciones.
  - `data_loader`: descarga de precios en vivo y consolidación del panel.
"""
