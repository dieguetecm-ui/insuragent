"""Memoria de largo plazo: historial de siniestros (PRD §3.2)."""

from __future__ import annotations

from datetime import date

import pytest

from insuragent.agents.policy_agent import PolicyAgent
from insuragent.data.synthetic import generate_claim_history, generate_customers
from insuragent.schemas.policy import CoverageType
from insuragent.session import InsurAgentSession


@pytest.fixture
def historial():
    customers = generate_customers(12, seed=20260902)
    return customers, generate_claim_history(customers, seed=20260902)


def test_el_historial_es_reproducible():
    customers = generate_customers(9, seed=7)
    assert generate_claim_history(customers, seed=7) == generate_claim_history(customers, seed=7)


def test_solo_una_parte_de_la_cartera_tiene_historial(historial):
    """La demo necesita mostrar ambos casos: con y sin siniestros previos."""
    customers, claims = historial
    con_historial = {c.customer_id for c in claims}
    assert 0 < len(con_historial) < len(customers)


def test_los_siniestros_son_coherentes_con_el_paquete(historial):
    """Un asegurado con sólo RC no puede tener un expediente de cristales."""
    customers, claims = historial
    paquete = {c.customer_id: c.coverage_type for c in customers}
    for claim in claims:
        if paquete[claim.customer_id] == "rc":
            assert claim.incident_type.value == "danos_terceros"


def test_las_fechas_son_pasadas(historial):
    _, claims = historial
    assert all(c.incident_date < date.today() for c in claims)


def test_el_deducible_del_historial_usa_la_tabla_de_coberturas(historial):
    """No son números inventados: salen de la misma función que usa el agente FNOL."""
    customers, claims = historial
    paquete = {c.customer_id: c.coverage_type for c in customers}
    cristales = [c for c in claims if c.incident_type.value == "cristales"]
    assert cristales, "el fixture debería incluir al menos un siniestro de cristales"
    for claim in cristales:
        assert paquete[claim.customer_id] == "amplia"
        assert claim.deductible_quoted_mxn == pytest.approx(2_400.0)


def test_el_seed_persiste_el_historial(repository):
    """`make seed` deja la base lista para demostrar memoria de largo plazo."""
    customers = repository.list_customers()
    for claim in generate_claim_history(customers, seed=20260902):
        repository.save_claim(claim)
    con_historial = [c for c in customers if repository.list_claims(c.customer_id)]
    assert con_historial


def test_el_agente_de_polizas_recibe_el_historial(session: InsurAgentSession, amplia_customer):
    """Sin inyectarlo en el contexto, el modelo no puede recordar nada."""
    for claim in generate_claim_history([amplia_customer], seed=20260902):
        session.repository.save_claim(claim)

    session.customer = amplia_customer
    session.reset_conversation()
    turno = session.send("¿Cuál es mi deducible por rotura de cristales?")
    assert turno.history_used > 0


def test_sin_historial_no_se_inyecta_nada(session: InsurAgentSession, rc_customer):
    session.customer = rc_customer
    session.reset_conversation()
    turno = session.send("¿Qué cubre mi póliza?")
    assert turno.history_used == 0


def test_el_resumen_de_historial_se_limita_a_tres_expedientes():
    """El historial completo desplazaría a las cláusulas recuperadas del contexto."""
    muchos = [
        {
            "claim_id": f"SIN-2026-{i:05d}",
            "incident_type": "cristales",
            "incident_date": "2026-01-01",
            "location": "Roma Norte",
            "deductible_quoted_mxn": 2400.0,
        }
        for i in range(10)
    ]
    resumen = PolicyAgent._format_history(muchos)
    assert resumen.count("SIN-2026-") == 3


def test_sin_historial_el_resumen_lo_dice_explicitamente():
    assert "sin siniestros previos" in PolicyAgent._format_history([]).lower()


def test_un_siniestro_nuevo_entra_de_inmediato_a_la_memoria_larga(
    session: InsurAgentSession, amplia_customer, png_bytes
):
    session.customer = amplia_customer
    session.reset_conversation()
    assert session.state is not None and session.state["claim_history"] == []

    session.send("Ayer se rompió el cristal de mi auto")
    session.send("Sí, quiero reportarlo")
    session.send("Fue ayer en Avenida Insurgentes. Una piedra rompió el parabrisas.")
    session.attach_evidence("dano.png", png_bytes, "image/png")

    assert len(session.state["claim_history"]) == 1


def test_el_paquete_del_historial_cubre_las_tres_variantes():
    """Cada variante necesita siniestros plausibles o la demo queda coja."""
    from insuragent.data.synthetic import HISTORIAL_POR_PAQUETE

    assert set(HISTORIAL_POR_PAQUETE) == {ct.value for ct in CoverageType}
