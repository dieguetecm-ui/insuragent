"""Memoria transaccional (PRD §3.2, §4.2)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from insuragent.db.repository import Repository
from insuragent.schemas.auth import LoginRequest
from insuragent.schemas.fnol import ClaimReport, IncidentType


def _credentials(customer) -> LoginRequest:
    return LoginRequest(
        policy_number=customer.policy_number,
        rfc=customer.rfc,
        curp=customer.curp,
        phone_last3=customer.phone_last3,
    )


def test_autenticacion_exitosa(repository: Repository, amplia_customer):
    found = repository.authenticate(_credentials(amplia_customer))
    assert found is not None and found.customer_id == amplia_customer.customer_id


def test_autenticacion_falla_si_un_factor_no_coincide(repository: Repository, amplia_customer):
    """Los cuatro factores del PRD §6.1 son obligatorios, no tres."""
    credentials = _credentials(amplia_customer)
    tampered = credentials.model_copy(
        update={"phone_last3": f"{(int(credentials.phone_last3) + 1) % 1000:03d}"}
    )
    assert repository.authenticate(tampered) is None


def test_autenticacion_falla_con_poliza_inexistente(repository: Repository, amplia_customer):
    credentials = _credentials(amplia_customer).model_copy(
        update={"policy_number": "AUT-2026-999999"}
    )
    assert repository.authenticate(credentials) is None


def test_upsert_es_idempotente(repository: Repository, amplia_customer):
    before = len(repository.list_customers())
    repository.upsert_customer(amplia_customer)
    assert len(repository.list_customers()) == before


def test_vehiculo_se_recupera_con_el_cliente(repository: Repository, amplia_customer):
    fetched = repository.get_customer(amplia_customer.customer_id)
    assert fetched is not None
    assert fetched.vehicle == amplia_customer.vehicle


def test_persistencia_y_lectura_de_siniestro(repository: Repository, amplia_customer):
    claim = ClaimReport(
        claim_id=repository.next_claim_id(),
        customer_id=amplia_customer.customer_id,
        policy_number=amplia_customer.policy_number,
        incident_type=IncidentType.CRISTALES,
        incident_date=date.today(),
        location="Avenida Insurgentes",
        description="Una piedra rompió el parabrisas.",
        created_at=datetime.now(),
    )
    repository.save_claim(claim)
    stored = repository.list_claims(amplia_customer.customer_id)
    assert len(stored) == 1 and stored[0]["claim_id"] == claim.claim_id


def test_siniestro_de_cliente_inexistente_es_rechazado(repository: Repository):
    """La integridad referencial está activa: FOREIGN KEY debe fallar."""
    import sqlite3

    claim = ClaimReport(
        claim_id="SIN-X",
        customer_id="CLI-9999",
        policy_number="AUT-2026-000000",
        incident_type=IncidentType.OTRO,
        incident_date=date.today(),
        location="Ninguno",
        description="Cliente inexistente.",
        created_at=datetime.now(),
    )
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_claim(claim)


def test_memoria_conversacional_conserva_el_orden(repository: Repository, amplia_customer):
    for index in range(3):
        repository.append_turn(
            amplia_customer.customer_id, "run-1", "user", f"mensaje {index}", "policy"
        )
    turns = repository.recent_turns(amplia_customer.customer_id, limit=3)
    assert [t["content"] for t in turns] == ["mensaje 0", "mensaje 1", "mensaje 2"]
