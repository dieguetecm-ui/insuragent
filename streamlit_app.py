"""Punto de entrada para hosting gestionado.

Streamlit Community Cloud y Hugging Face Spaces ejecutan el archivo que
encuentran en la raíz del repositorio. Este módulo hace las tres cosas que en
local hacen `make bootstrap` y el `.env`:

1. Pone `src/` en el path, porque el paquete no se instala en esos entornos.
2. Vuelca los secretos de la plataforma a variables de entorno **antes** de que
   se lea la configuración —`get_settings()` está cacheada, así que después
   sería tarde—.
3. Siembra la base y construye el índice si el disco viene vacío.

Autor: Diego Carrillo Mondragón
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st  # noqa: E402

# --- secretos de la plataforma → entorno -----------------------------------
# En Streamlit Cloud y HF Spaces la API key se configura en el panel de
# secretos, no en un archivo .env (que además nunca debe versionarse).
try:
    for clave, valor in st.secrets.items():
        if isinstance(valor, str):
            os.environ.setdefault(clave, valor)
except Exception:  # noqa: BLE001 — sin secretos configurados, se sigue igual
    pass

# En un hosting gratuito no cabe PyTorch (2.1 GB de RSS frente a 214 MB), así
# que allí el backend es el léxico con el diccionario del dominio, medido en
# 15/15 sobre el set dorado — la misma precisión que el modelo denso.
#
# La condición es la ausencia de la librería, no el entorno: si alguien corre
# este mismo archivo en local con `sentence-transformers` instalado, manda lo
# que diga su `.env`. Un `setdefault` incondicional lo ignoraría, porque
# pydantic-settings lee el `.env` como archivo y no lo vuelca al entorno.
if importlib.util.find_spec("sentence_transformers") is None:
    os.environ.setdefault("INSURAGENT_EMBEDDING_BACKEND", "hash")

from insuragent.bootstrap import ensure_ready  # noqa: E402
from insuragent.observability import configure_logging  # noqa: E402

configure_logging()


@st.cache_resource(show_spinner="Preparando datos sintéticos e índice vectorial…")
def _preparar() -> dict[str, str]:
    return ensure_ready()


_preparar()

from insuragent.ui.app import main  # noqa: E402

# Se invoca la función explícitamente, no se confía en el efecto secundario del
# import: Python sólo ejecuta un módulo la primera vez que se importa, mientras
# que Streamlit vuelve a correr este script en cada interacción del usuario. Con
# `import` a secas, la interfaz se quedaba congelada tras el primer render.
main()
