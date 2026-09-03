"""Generación de datos sintéticos (PRD §4.3)."""

from __future__ import annotations

from insuragent.data.synthetic import generate_customers
from insuragent.schemas.auth import CURP_PATTERN, RFC_PATTERN, LoginRequest


def test_generacion_es_reproducible():
    assert generate_customers(8, seed=42) == generate_customers(8, seed=42)


def test_semillas_distintas_producen_datos_distintos():
    assert generate_customers(8, seed=42) != generate_customers(8, seed=43)


def test_identificadores_respetan_formato_oficial_y_marcador():
    for customer in generate_customers(24, seed=7):
        assert RFC_PATTERN.match(customer.rfc), customer.rfc
        assert CURP_PATTERN.match(customer.curp), customer.curp
        assert customer.rfc.startswith("XXX")
        assert customer.curp.startswith("XXXX")


def test_las_tres_variantes_estan_representadas():
    coverages = {c.coverage_type for c in generate_customers(6, seed=1)}
    assert coverages == {"amplia", "basica", "rc"}


def test_credenciales_generadas_validan_contra_el_contrato_de_login():
    customer = generate_customers(1, seed=99)[0]
    credentials = LoginRequest(
        policy_number=customer.policy_number,
        rfc=customer.rfc,
        curp=customer.curp,
        phone_last3=customer.phone_last3,
    )
    assert customer.matches(credentials)
