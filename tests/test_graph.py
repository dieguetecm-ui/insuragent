"""Grafo conversacional y flujo end-to-end (PRD §3, §6)."""

from __future__ import annotations

import pytest

from insuragent.graph.build import interpret_confirmation, wants_to_skip_evidence
from insuragent.graph.state import Stage
from insuragent.schemas.routing import Route
from insuragent.session import InsurAgentSession


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sí, quiero reportarlo", True),
        ("Claro", True),
        ("adelante por favor", True),
        ("No, todavía no", False),
        ("mejor no", False),
        ("¿Cuál es mi deducible?", None),
    ],
)
def test_interpretacion_de_confirmacion(text, expected):
    assert interpret_confirmation(text) is expected


def test_no_dentro_de_otra_palabra_no_cuenta_como_negativa():
    """`nosotros` contiene `no`; comparar subcadenas rompería el flujo."""
    assert interpret_confirmation("nosotros ya lo revisamos") is None


def test_deteccion_de_omision_de_evidencia():
    assert wants_to_skip_evidence("no tengo foto del daño")
    assert not wants_to_skip_evidence("aquí va la foto")


def _login(session: InsurAgentSession, customer) -> None:
    session.customer = customer
    session.reset_conversation()


def test_consulta_de_poliza_cita_clausulas(session: InsurAgentSession, amplia_customer):
    _login(session, amplia_customer)
    turn = session.send("¿Cuál es mi deducible por robo total?")
    assert turn.route == Route.POLICY.value
    assert "AMP-3.1" in turn.citations
    assert turn.deductible_mxn == pytest.approx(32_000.0)


def test_pregunta_de_taller_va_a_la_red(session: InsurAgentSession, amplia_customer):
    _login(session, amplia_customer)
    turn = session.send("¿Dónde hay un taller cerca de Polanco?")
    assert turn.route == Route.NETWORK.value
    assert "TAL-001" in turn.workshop_ids


def test_siniestro_narrado_pasa_primero_por_poliza(session: InsurAgentSession, amplia_customer):
    """PRD §6.3–6.4: se evalúa la cobertura y sólo después se ofrece reportar."""
    _login(session, amplia_customer)
    turn = session.send("Ayer se rompió el cristal de mi auto")
    assert turn.route == Route.POLICY.value
    assert turn.stage == Stage.CONFIRM_FNOL.value
    assert "reporte" in turn.answer.lower()


def test_negativa_cierra_sin_abrir_expediente(session: InsurAgentSession, amplia_customer):
    """PRD §6.4: si es negativo, cierra ofreciendo más ayuda."""
    _login(session, amplia_customer)
    session.send("Ayer se rompió el cristal de mi auto")
    turn = session.send("No, todavía no")
    assert turn.stage == Stage.IDLE.value
    assert turn.claim_id is None
    assert session.past_claims() == []


def test_flujo_fnol_completo_persiste_expediente_y_evidencia(
    session: InsurAgentSession, amplia_customer, png_bytes
):
    _login(session, amplia_customer)
    session.send("Ayer se rompió el cristal de mi auto")
    session.send("Sí, quiero reportarlo")
    turn = session.send(
        "Fue ayer en Avenida Insurgentes. Una piedra levantada por un camión rompió el parabrisas."
    )
    assert turn.stage == Stage.AWAITING_EVIDENCE.value

    claim = session.attach_evidence("dano.png", png_bytes, "image/png")
    assert claim.claim_id.startswith("SIN-")
    assert claim.evidence[0].stored_path.exists()
    assert claim.deductible_quoted_mxn == pytest.approx(2_400.0)
    assert len(session.past_claims()) == 1


def test_evidencia_fuera_de_etapa_es_rechazada(
    session: InsurAgentSession, amplia_customer, png_bytes
):
    """Adjuntar antes de tiempo registraría un siniestro con datos incompletos."""
    _login(session, amplia_customer)
    session.send("¿Qué cubre mi póliza?")
    with pytest.raises(RuntimeError, match="etapa"):
        session.attach_evidence("dano.png", png_bytes, "image/png")


def test_flujo_fnol_no_reclasifica_a_media_recoleccion(session: InsurAgentSession, amplia_customer):
    """Una vez dentro de FNOL, un mensaje ambiguo no debe sacar al usuario del flujo."""
    _login(session, amplia_customer)
    session.send("Quiero reportar un choque")
    turn = session.send("¿Dónde hay un taller cerca de Polanco?")
    assert turn.route == Route.FNOL.value
    assert turn.route_reasoning.startswith("Continuidad")


def test_sesion_sin_autenticar_no_acepta_turnos(session: InsurAgentSession):
    with pytest.raises(RuntimeError, match="autenticada"):
        session.send("Hola")


def test_login_a_traves_de_la_sesion(session: InsurAgentSession, amplia_customer):
    from insuragent.schemas.auth import LoginRequest

    customer = session.login(
        LoginRequest(
            policy_number=amplia_customer.policy_number,
            rfc=amplia_customer.rfc,
            curp=amplia_customer.curp,
            phone_last3=amplia_customer.phone_last3,
        )
    )
    assert customer is not None and session.authenticated
