"""Captura de conversaciones de ejemplo para el reporte (PRD §2)."""

from __future__ import annotations

import json

import pytest

from insuragent.evaluation.transcripts import GUIONES, capturar, capture_transcripts
from insuragent.graph.state import Stage
from insuragent.session import InsurAgentSession


@pytest.fixture
def transcripciones(settings, repository, clause_index):
    return capture_transcripts(settings)


def test_se_captura_un_transcript_por_guion(transcripciones):
    assert len(transcripciones) == len(GUIONES)


def test_cada_turno_registra_su_decision_de_enrutamiento(transcripciones):
    """Sin la justificación, la transcripción no sirve para auditar."""
    for t in transcripciones:
        for turno in t.turnos:
            assert turno.ruta
            assert turno.razonamiento


def test_las_citas_no_se_arrastran_entre_turnos(transcripciones):
    """Un turno del agente FNOL no recupera cláusulas: no debe reportar citas.

    Es el defecto que la propia captura destapó: el estado conservaba las citas
    del turno anterior y la traza hacía creer que las había citado el FNOL.
    """
    conv = next(t for t in transcripciones if t.transcript_id == "conv-01")
    turnos_fnol = [x for x in conv.turnos if x.ruta == "fnol"]
    assert turnos_fnol
    assert all(not x.citas for x in turnos_fnol)


def test_el_primer_turno_de_polizas_si_cita(transcripciones):
    conv = next(t for t in transcripciones if t.transcript_id == "conv-01")
    primero = conv.turnos[0]
    assert primero.ruta == "policy"
    assert primero.citas
    assert primero.recuperacion
    assert all(0.0 <= item["score"] <= 1.0 for item in primero.recuperacion)


def test_la_conversacion_de_memoria_larga_tiene_historial(transcripciones):
    """El guion pierde su sentido si el asegurado no tiene siniestros previos."""
    conv = next(t for t in transcripciones if t.transcript_id == "conv-01")
    assert conv.asegurado["siniestros_previos"]
    assert conv.turnos[0].historial_usado > 0


def test_el_flujo_fnol_termina_con_expediente_y_evidencia(transcripciones):
    conv = next(t for t in transcripciones if t.transcript_id == "conv-01")
    assert conv.evidencia is not None
    assert conv.turnos[-1].etapa == Stage.DONE.value


def test_la_discriminacion_entre_paquetes_queda_visible(transcripciones):
    """conv-02 debe citar cláusulas de Básica, nunca de Amplia."""
    conv = next(t for t in transcripciones if t.transcript_id == "conv-02")
    assert conv.asegurado["paquete"] == "basica"
    citadas = conv.turnos[0].recuperacion
    assert citadas
    assert all(item["coverage_type"] == "basica" for item in citadas)


def test_la_consulta_de_taller_no_recupera_clausulas(transcripciones):
    conv = next(t for t in transcripciones if t.transcript_id == "conv-03")
    assert conv.turnos[0].ruta == "network"
    assert conv.turnos[0].talleres
    assert not conv.turnos[0].citas


def test_los_guiones_apuntan_a_casos_dorados_existentes():
    """Si un id no existe, el lector del reporte no puede rastrear la referencia."""
    from insuragent.evaluation.golden import RAG_CASES, ROUTING_CASES

    conocidos = {c.case_id for c in RAG_CASES} | {c.case_id for c in ROUTING_CASES}
    for guion in GUIONES:
        assert set(guion.casos_dorados) <= conocidos, guion.transcript_id


def test_las_transcripciones_se_guardan_en_json(settings, repository, clause_index):
    capture_transcripts(settings)
    destino = settings.data_dir / "transcripts.json"
    payload = json.loads(destino.read_text(encoding="utf-8"))
    assert payload["proveedor"]
    assert len(payload["conversaciones"]) == len(GUIONES)


def test_la_captura_usa_una_base_propia(settings, repository, clause_index):
    """No debe contaminarse con los expedientes que crea la evaluación."""
    capture_transcripts(settings)
    assert (settings.data_dir / "transcripts.db").exists()


def test_un_guion_sin_asegurado_del_paquete_falla_con_mensaje_claro(
    settings, clause_index, repository
):
    from insuragent.evaluation.transcripts import _elegir_asegurado
    from insuragent.schemas.policy import CoverageType

    class _VaciaAmplia:
        def list_customers(self):
            return []

        def list_claims(self, _customer_id):
            return []

    with pytest.raises(RuntimeError, match="make seed"):
        _elegir_asegurado(_VaciaAmplia(), CoverageType.AMPLIA, con_historial=False)


def test_los_turnos_se_numeran_en_orden(settings, repository, clause_index):
    from insuragent.evaluation.transcripts import _base_limpia

    session = InsurAgentSession.create(_base_limpia(settings))
    conv = capturar(GUIONES[0], session)
    assert [t.numero for t in conv.turnos] == list(range(1, len(conv.turnos) + 1))
