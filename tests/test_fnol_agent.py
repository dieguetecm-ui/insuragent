"""Agente FNOL: extracción, evidencia y persistencia (PRD §6.5)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from insuragent.agents.fnol_agent import FNOLAgent
from insuragent.llm.stub_provider import StubProvider
from insuragent.schemas.fnol import IncidentDraft, IncidentType


@pytest.fixture
def agent(repository, settings) -> FNOLAgent:
    return FNOLAgent(StubProvider(), repository, settings.uploads_dir)


def test_extraccion_identifica_tipo_y_fecha_relativa(agent: FNOLAgent):
    draft, _ = agent.extract("Ayer se rompió el parabrisas de mi auto")
    assert draft.incident_type is IncidentType.CRISTALES
    assert draft.incident_date == date.today() - timedelta(days=1)


def test_extraccion_deja_en_none_lo_no_dicho(agent: FNOLAgent):
    """Un campo no expresado nunca se inventa: se vuelve a preguntar."""
    draft, _ = agent.extract("Tuve un problema con el coche")
    assert draft.incident_type is None
    assert draft.incident_date is None


def test_recoleccion_pide_lo_que_falta(agent: FNOLAgent, amplia_customer):
    turn = agent.collect("Choqué el auto", IncidentDraft(), amplia_customer)
    assert not turn.complete
    assert "location" in turn.missing


def test_evidencia_valida_se_guarda_en_disco(agent: FNOLAgent, png_bytes, settings):
    evidence = agent.store_evidence("SIN-TEST", "dano.png", png_bytes, "image/png")
    assert evidence.stored_path.exists()
    assert evidence.stored_path.read_bytes() == png_bytes
    assert evidence.size_bytes == len(png_bytes)
    assert settings.uploads_dir in evidence.stored_path.parents


def test_nombre_con_ruta_no_escapa_del_directorio(agent: FNOLAgent, png_bytes, settings):
    """`../../etc/passwd` debe quedarse dentro de `uploads/`."""
    evidence = agent.store_evidence("SIN-TEST", "../../escape.png", png_bytes, "image/png")
    assert evidence.filename == "escape.png"
    assert settings.uploads_dir in evidence.stored_path.parents


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "match"),
    [
        ("virus.exe", b"MZ", "application/x-msdownload", "no permitido"),
        ("vacio.png", b"", "image/png", "vacío"),
    ],
)
def test_evidencia_invalida_es_rechazada(agent: FNOLAgent, filename, content, content_type, match):
    with pytest.raises(ValueError, match=match):
        agent.store_evidence("SIN-TEST", filename, content, content_type)


def test_archivo_demasiado_grande_es_rechazado(agent: FNOLAgent):
    with pytest.raises(ValueError, match="excede"):
        agent.store_evidence("SIN-TEST", "grande.png", b"\x00" * (11 * 1024 * 1024), "image/png")


def test_finalize_calcula_el_deducible_de_la_cobertura(agent: FNOLAgent, amplia_customer):
    draft = IncidentDraft(
        incident_type=IncidentType.CRISTALES,
        incident_date=date.today(),
        location="Roma Norte",
        description="Se rompió el parabrisas por una piedra.",
    )
    claim = agent.finalize(draft, amplia_customer)
    assert claim.deductible_quoted_mxn == pytest.approx(2_400.0)


def test_finalize_rechaza_borrador_incompleto(agent: FNOLAgent, amplia_customer):
    with pytest.raises(ValueError, match="incompleto"):
        agent.finalize(IncidentDraft(incident_type=IncidentType.COLISION), amplia_customer)
