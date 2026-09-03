"""Agente de Pólizas — RAG sobre las condiciones generales (PRD §3, §6.3).

El agente hace tres cosas, en este orden:

1. Recupera cláusulas de FAISS, **restringidas al paquete que el asegurado
   contrató** — nunca se le cita un producto que no compró.
2. Calcula el deducible en Python cuando la consulta apunta a una cobertura
   concreta, y lo inyecta como hecho.
3. Redacta la respuesta con el LLM, obligado a citar los identificadores de
   cláusula.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from insuragent.agents.prompts import POLICY_SYSTEM
from insuragent.agents.tools import INCIDENT_TO_COVERAGE, DeductibleQuote, quote_deductible
from insuragent.llm import LLMProvider, Usage
from insuragent.rag.embeddings import normalize_text
from insuragent.rag.index import ClauseIndex, format_context
from insuragent.schemas.auth import Customer
from insuragent.schemas.fnol import IncidentType
from insuragent.schemas.policy import CoverageType, RetrievedClause

# Señales léxicas → cobertura. Se usan sólo para decidir qué deducible calcular;
# la respuesta sustantiva sigue viniendo del contexto recuperado.
COVERAGE_HINTS: dict[str, tuple[str, ...]] = {
    "cristales": ("cristal", "parabrisas", "medallon", "vidrio", "quemacocos"),
    "robo_total": ("robo total", "robaron", "roban", "robar", "hurto", "robo"),
    "danos_materiales": (
        "choque",
        "colision",
        "golpe",
        "volcadura",
        "danos materiales",
        "incendio",
    ),
    "responsabilidad_civil": ("responsabilidad civil", " rc ", "tercero", "danos a terceros"),
    "gastos_medicos": ("gastos medicos", "lesion", "ambulancia", "hospital"),
    "asistencia_vial": ("grua", "asistencia vial", "paso de corriente", "cerrajeria"),
}


@dataclass(slots=True)
class PolicyAnswer:
    """Respuesta del agente junto con lo necesario para auditarla."""

    text: str
    retrieved: list[RetrievedClause] = field(default_factory=list)
    quote: DeductibleQuote | None = None
    detected_incident: IncidentType | None = None
    usage: Usage = field(default_factory=Usage)
    history_used: int = 0
    """Cuántos expedientes previos se inyectaron; queda en la traza."""

    @property
    def citations(self) -> list[str]:
        return [item.clause.clause_id for item in self.retrieved]


def detect_coverage_key(text: str) -> str | None:
    """Cobertura aludida por la consulta, si alguna es identificable."""
    normalized = f" {normalize_text(text)} "
    for coverage_key, hints in COVERAGE_HINTS.items():
        if any(normalize_text(hint) in normalized for hint in hints):
            return coverage_key
    return None


def detect_incident_type(text: str) -> IncidentType | None:
    """Tipo de siniestro narrado, para poder ofrecer el reporte FNOL después."""
    coverage_key = detect_coverage_key(text)
    if coverage_key is None:
        return None
    for incident, mapped in INCIDENT_TO_COVERAGE.items():
        if mapped == coverage_key and incident is not IncidentType.OTRO:
            return incident
    return None


class PolicyAgent:
    """Responde consultas sobre coberturas, cláusulas y deducibles."""

    def __init__(self, provider: LLMProvider, index: ClauseIndex, top_k: int = 4) -> None:
        self._provider = provider
        self._index = index
        self._top_k = top_k

    @staticmethod
    def _format_history(claim_history: list[dict] | None) -> str:
        """Resume el historial de siniestros para el prompt (PRD §3.2).

        Se resume en vez de volcarlo entero: el historial completo crecería sin
        límite y desplazaría a las cláusulas recuperadas, que son lo que el
        agente necesita para responder. Tres expedientes bastan para que el
        asistente reconozca una recurrencia.
        """
        if not claim_history:
            return "HISTORIAL DEL ASEGURADO: sin siniestros previos registrados."
        lineas = [
            f"- {c['claim_id']} · {c['incident_type']} · {c['incident_date']} · {c['location']}"
            + (
                f" · deducible aplicado ${c['deductible_quoted_mxn']:,.2f} MXN"
                if c.get("deductible_quoted_mxn")
                else ""
            )
            for c in claim_history[:3]
        ]
        return "HISTORIAL DEL ASEGURADO (siniestros previos):\n" + "\n".join(lineas)

    def answer(
        self,
        question: str,
        customer: Customer,
        claim_history: list[dict] | None = None,
    ) -> PolicyAnswer:
        coverage_type = CoverageType(customer.coverage_type)
        retrieved = self._index.search(question, top_k=self._top_k, coverage_types=(coverage_type,))

        coverage_key = detect_coverage_key(question)
        quote = quote_deductible(coverage_type, coverage_key) if coverage_key else None

        facts = (
            quote.as_prompt_fact()
            if quote
            else "HECHO CALCULADO: no aplica un deducible específico a esta consulta."
        )
        vehicle = customer.vehicle
        user_content = (
            f"Asegurado: {customer.full_name} | Póliza {customer.policy_number} | "
            f"Paquete contratado: {coverage_type.value} | "
            f"Vehículo: {vehicle.brand} {vehicle.model} {vehicle.year}.\n\n"
            f"{facts}\n\n"
            f"{self._format_history(claim_history)}\n\n"
            f"<contexto>\n{format_context(retrieved)}\n</contexto>\n\n"
            f"Pregunta del asegurado: {question}"
        )

        response = self._provider.complete(
            system=POLICY_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        return PolicyAnswer(
            text=response.text,
            retrieved=retrieved,
            quote=quote,
            detected_incident=detect_incident_type(question),
            usage=response.usage,
            history_used=min(len(claim_history or []), 3),
        )
