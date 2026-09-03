"""Prueba de la interfaz Streamlit con `AppTest`.

Levantar el servidor y pedir `/` sólo demuestra que arranca: el script de la app
no se ejecuta hasta que un navegador abre el websocket. `AppTest` corre el
script de verdad, así que un error en el cableado de la UI se detecta aquí y no
en la demo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from insuragent.config import get_settings
from insuragent.data.synthetic import generate_customers
from insuragent.db.repository import Repository

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "insuragent" / "ui" / "app.py"
STARTUP_TIMEOUT_S = 120


@pytest.fixture
def app(tmp_path: Path, monkeypatch) -> AppTest:
    """App apuntando a un disco temporal, con la base ya poblada.

    Las variables de entorno tienen prioridad sobre `.env` en pydantic-settings,
    así que basta con fijarlas para aislar la corrida del proyecto real.
    """
    import streamlit as st

    for key, value in {
        "INSURAGENT_LLM_PROVIDER": "stub",
        "INSURAGENT_EMBEDDING_BACKEND": "hash",
        "INSURAGENT_DATA_DIR": str(tmp_path),
        "INSURAGENT_CORPUS_DIR": str(tmp_path / "raw"),
        "INSURAGENT_INDEX_DIR": str(tmp_path / "index"),
        "INSURAGENT_UPLOADS_DIR": str(tmp_path / "uploads"),
        "INSURAGENT_DB_PATH": str(tmp_path / "ui.db"),
        "INSURAGENT_TRACE_FILE": str(tmp_path / "traces.jsonl"),
    }.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    st.cache_resource.clear()

    settings = get_settings()
    settings.ensure_dirs()
    repository = Repository(settings.db_path)
    repository.reset()
    for customer in generate_customers(6, settings.synthetic_seed):
        repository.upsert_customer(customer)

    return AppTest.from_file(str(APP_PATH), default_timeout=STARTUP_TIMEOUT_S)


def _customer(coverage: str = "amplia"):
    return next(
        c
        for c in generate_customers(6, get_settings().synthetic_seed)
        if c.coverage_type == coverage
    )


def test_la_app_arranca_sin_excepciones(app: AppTest):
    app.run()
    assert not app.exception
    assert "InsurAgent" in app.title[0].value


def test_pantalla_inicial_pide_autenticacion(app: AppTest):
    app.run()
    assert len(app.sidebar.text_input) == 4  # póliza, RFC, CURP, celular


def test_credenciales_malformadas_muestran_error_de_validacion(app: AppTest):
    """Pydantic detiene el dato antes de tocar la base (PRD §4.3)."""
    app.run()
    app.sidebar.text_input[0].set_value("POLIZA-MALA")
    app.sidebar.text_input[1].set_value("XXXJ860330FYB")
    app.sidebar.text_input[2].set_value("XXXX860330MNEYSTB7")
    app.sidebar.text_input[3].set_value("769")
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert app.sidebar.error


def test_identificador_no_sintetico_es_rechazado(app: AppTest):
    """Un RFC con formato válido pero sin el marcador XXX no debe entrar."""
    customer = _customer()
    app.run()
    app.sidebar.text_input[0].set_value(customer.policy_number)
    app.sidebar.text_input[1].set_value("MAGJ860330FYB")
    app.sidebar.text_input[2].set_value(customer.curp)
    app.sidebar.text_input[3].set_value(customer.phone_last3)
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert any("sintético" in error.value for error in app.sidebar.error)


def test_login_valido_abre_la_conversacion(app: AppTest):
    customer = _customer()
    app.run()
    app.sidebar.text_input[0].set_value(customer.policy_number)
    app.sidebar.text_input[1].set_value(customer.rfc)
    app.sidebar.text_input[2].set_value(customer.curp)
    app.sidebar.text_input[3].set_value(customer.phone_last3)
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert any(customer.full_name in success.value for success in app.sidebar.success)
    assert app.chat_input
