"""Cálculo de deducibles y consulta de red — la aritmética fuera del LLM."""

from __future__ import annotations

from decimal import Decimal

import pytest

from insuragent.agents.tools import lookup_workshops, quote_deductible
from insuragent.schemas.policy import CoverageType


def test_robo_total_amplia_es_10_por_ciento():
    quote = quote_deductible(CoverageType.AMPLIA, "robo_total")
    assert quote.covered
    assert quote.deductible_mxn == pytest.approx(32_000.0)


def test_danos_materiales_amplia_es_5_por_ciento():
    assert quote_deductible(
        CoverageType.AMPLIA, "danos_materiales"
    ).deductible_mxn == pytest.approx(16_000.0)


def test_responsabilidad_civil_no_tiene_deducible():
    quote = quote_deductible(CoverageType.RC, "responsabilidad_civil")
    assert quote.covered
    assert quote.deductible_mxn is None


def test_cobertura_no_contratada_se_reporta_como_no_amparada():
    quote = quote_deductible(CoverageType.BASICA, "cristales")
    assert not quote.covered
    assert (
        "no ampara" in quote.as_prompt_fact().lower()
        or "NO está amparada" in quote.as_prompt_fact()
    )


def test_cristales_aplica_el_deducible_minimo_contractual():
    """20% de $5,000 son $1,000, por debajo del mínimo de $1,500."""
    quote = quote_deductible(CoverageType.AMPLIA, "cristales", repair_cost_mxn=Decimal("5000"))
    assert quote.deductible_mxn == pytest.approx(1_500.0)
    assert "mínimo" in quote.explanation


def test_cristales_usa_el_porcentaje_cuando_supera_el_minimo():
    quote = quote_deductible(CoverageType.AMPLIA, "cristales", repair_cost_mxn=Decimal("20000"))
    assert quote.deductible_mxn == pytest.approx(4_000.0)


def test_cobertura_inexistente_no_revienta():
    assert not quote_deductible(CoverageType.AMPLIA, "cobertura_fantasma").covered


def test_busqueda_de_talleres_prioriza_la_colonia():
    workshops = lookup_workshops("cerca de Polanco")
    assert workshops[0].neighborhood == "Polanco"


def test_busqueda_de_talleres_ignora_acentos():
    assert lookup_workshops("satelite")[0].workshop_id == "TAL-005"


def test_filtro_por_especialidad():
    workshops = lookup_workshops("Ciudad de México", specialty="cristales")
    assert all("cristales" in w.specialties for w in workshops)


def test_ubicacion_desconocida_devuelve_alternativas():
    """Nunca se responde con una lista vacía sin ofrecer opciones."""
    assert lookup_workshops("Ushuaia")
