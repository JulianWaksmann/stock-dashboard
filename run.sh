#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: no se encontró python3. Instalá Python 3 antes de continuar." >&2
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual Python..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Verificando dependencias..."
pip install -r requirements.txt

echo "Iniciando Tablero Streamlit..."
streamlit run app.py
