"""Contratos de datos — la primera línea de defensa (PRD §4.3)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from insuragent.schemas.auth import LoginRequest
from insuragent.schemas.fnol import ClaimReport, IncidentDraft, IncidentType

VALID = {
    "policy_number": "AUT-2026-100000",
    "rfc": "XXXJ860330FYB",
    "curp": "XXXX860330MNEYSTB7",
    "phone_last3": "769",
}


def test_login_acepta_credenciales_validas():
    credentials = LoginRequest(**VALID)
    assert credentials.is_synthetic()


def test_login_normaliza_a_mayusculas():
    credentials = LoginRequest(**{**VALID, "rfc": "xxxj860330fyb"})
    assert credentials.rfc == "XXXJ860330FYB"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_number", "POL-2026-100000"),  # prefijo equivocado
        ("policy_number", "AUT-26-100000"),  # año de dos dígitos
        ("rfc", "XXXJ86033"),  # demasiado corto
        ("curp", "XXXX860330XNEYSTB7"),  # sexo inválido
        ("phone_last3", "76"),  # dos dígitos
        ("phone_last3", "abc"),  # no numérico
    ],
)
def test_login_rechaza_datos_malformados(field, value):
    with pytest.raises(ValidationError):
        LoginRequest(**{**VALID, field: value})


def test_identificador_sin_marcador_no_es_sintetico():
    """Un RFC con formato válido pero sin prefijo reservado no pasa el filtro."""
    credentials = LoginRequest(**{**VALID, "rfc": "MAGJ860330FYB"})
    assert not credentials.is_synthetic()


def test_borrador_reporta_campos_faltantes():
    draft = IncidentDraft(incident_type=IncidentType.CRISTALES)
    assert set(draft.missing_fields()) == {"incident_date", "location", "description"}
    assert not draft.is_complete()


def test_merge_no_borra_lo_ya_capturado():
    base = IncidentDraft(incident_type=IncidentType.CRISTALES, location="Roma Norte")
    merged = base.merge(IncidentDraft(description="Una piedra rompió el parabrisas."))
    assert merged.location == "Roma Norte"
    assert merged.incident_type is IncidentType.CRISTALES
    assert merged.description


def test_fecha_futura_es_rechazada():
    with pytest.raises(ValidationError):
        IncidentDraft(incident_date=date.today() + timedelta(days=1))


def test_borrador_incompleto_no_puede_promoverse():
    """Última barrera antes de la base transaccional."""
    draft = IncidentDraft(incident_type=IncidentType.COLISION)
    with pytest.raises(ValueError, match="incompleto"):
        ClaimReport.from_draft(
            draft, claim_id="SIN-1", customer_id="CLI-0001", policy_number="AUT-2026-100000"
        )
