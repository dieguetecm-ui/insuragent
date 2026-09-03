"""Herramientas deterministas de los agentes.

El cálculo del deducible se hace **en Python**, no en el LLM, y su resultado se
inyecta en el prompt como hecho ya calculado. Un modelo de lenguaje es un mal
lugar para hacer aritmética sobre dinero: el PRD §4.3 exige contratos estrictos
justamente para que un número inventado no llegue al asegurado ni a la base.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from insuragent.data.corpus import coverages_for
from insuragent.data.network import Workshop, find_workshops
from insuragent.schemas.fnol import IncidentType
from insuragent.schemas.policy import CoverageType

# Qué cobertura aplica a cada tipo de siniestro.
INCIDENT_TO_COVERAGE: dict[IncidentType, str] = {
    IncidentType.CRISTALES: "cristales",
    IncidentType.COLISION: "danos_materiales",
    IncidentType.ROBO_TOTAL: "robo_total",
    IncidentType.ROBO_PARCIAL: "robo_total",
    IncidentType.DANOS_TERCEROS: "responsabilidad_civil",
    IncidentType.OTRO: "danos_materiales",
}


class DeductibleQuote(BaseModel):
    """Resultado del cálculo de deducible para una cobertura concreta."""

    model_config = ConfigDict(frozen=True)

    coverage_key: str
    coverage_label: str
    covered: bool
    deductible_pct: float | None = None
    deductible_mxn: float | None = Field(default=None, description="Importe estimado en pesos")
    sum_insured_mxn: float | None = None
    explanation: str

    def as_prompt_fact(self) -> str:
        """Línea que se inyecta en el prompt del agente de pólizas."""
        if not self.covered:
            return f"HECHO CALCULADO: la cobertura '{self.coverage_label}' NO está amparada en este paquete."
        if self.deductible_mxn is None:
            return f"HECHO CALCULADO: '{self.coverage_label}' está amparada y opera sin deducible."
        return (
            f"HECHO CALCULADO: '{self.coverage_label}' está amparada. Deducible aplicable: "
            f"{self.deductible_pct:.0f}% ≈ ${self.deductible_mxn:,.2f} MXN. {self.explanation}"
        )


def quote_deductible(
    coverage_type: CoverageType,
    coverage_key: str,
    *,
    repair_cost_mxn: Decimal | None = None,
) -> DeductibleQuote:
    """Calcula el deducible de una cobertura para un paquete dado.

    Para coberturas cuyo deducible se calcula sobre la suma asegurada (daños
    materiales, robo total) se usa el valor comercial de la carátula. Para
    cristales, el deducible es un porcentaje del costo de reposición con un
    mínimo contractual, así que `repair_cost_mxn` cambia el resultado.
    """
    coverage = next((c for c in coverages_for(coverage_type) if c.key == coverage_key), None)
    if coverage is None:
        return DeductibleQuote(
            coverage_key=coverage_key,
            coverage_label=coverage_key.replace("_", " "),
            covered=False,
            explanation="La cobertura no existe en este paquete.",
        )

    if not coverage.covered:
        return DeductibleQuote(
            coverage_key=coverage.key,
            coverage_label=coverage.label,
            covered=False,
            explanation=f"El paquete {coverage_type.value} no ampara esta cobertura.",
        )

    if coverage.deductible_pct is None:
        return DeductibleQuote(
            coverage_key=coverage.key,
            coverage_label=coverage.label,
            covered=True,
            sum_insured_mxn=float(coverage.sum_insured_mxn) if coverage.sum_insured_mxn else None,
            explanation=coverage.notes or "Opera sin deducible.",
        )

    base = repair_cost_mxn if repair_cost_mxn is not None else coverage.sum_insured_mxn
    if base is None:
        return DeductibleQuote(
            coverage_key=coverage.key,
            coverage_label=coverage.label,
            covered=True,
            deductible_pct=float(coverage.deductible_pct),
            explanation="Se requiere el costo de reposición para estimar el importe.",
        )

    amount = base * coverage.deductible_pct / Decimal("100")
    explanation = coverage.notes or ""
    if coverage.deductible_min_mxn is not None and amount < coverage.deductible_min_mxn:
        amount = coverage.deductible_min_mxn
        explanation = (
            f"Aplica el deducible mínimo contractual de ${coverage.deductible_min_mxn:,.2f} MXN."
        )

    return DeductibleQuote(
        coverage_key=coverage.key,
        coverage_label=coverage.label,
        covered=True,
        deductible_pct=float(coverage.deductible_pct),
        deductible_mxn=float(amount),
        sum_insured_mxn=float(coverage.sum_insured_mxn) if coverage.sum_insured_mxn else None,
        explanation=explanation,
    )


def lookup_workshops(location: str, specialty: str | None = None, limit: int = 3) -> list[Workshop]:
    """Consulta la red de talleres en convenio (Agente de Red, PRD §3)."""
    return find_workshops(location, specialty=specialty, limit=limit)
