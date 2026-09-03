"""Agente Orquestador — clasificación de intención (PRD §3.1).

La clasificación se resuelve con *structured output* sobre el LLM: el modelo
devuelve un JSON que valida contra `RouteDecision`. Si el proveedor falla o
devuelve algo inválido, se cae a las reglas deterministas del stub en lugar de
romper la conversación; la traza registra que hubo degradación.
"""

from __future__ import annotations

import logging

from insuragent.agents.prompts import ORCHESTRATOR_SYSTEM
from insuragent.llm import LLMError, LLMProvider, Usage
from insuragent.llm.stub_provider import classify as rule_based_classify
from insuragent.schemas.routing import RouteDecision

_LOGGER = logging.getLogger(__name__)


class Orchestrator:
    """Enruta la consulta del asegurado al agente adecuado."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def route(self, user_input: str, *, history: str = "") -> tuple[RouteDecision, Usage]:
        """Devuelve la decisión de ruta y el consumo de la llamada."""
        content = (
            user_input
            if not history
            else f"Contexto previo:\n{history}\n\nMensaje actual:\n{user_input}"
        )
        try:
            decision, usage = self._provider.structured(
                system=ORCHESTRATOR_SYSTEM,
                messages=[{"role": "user", "content": content}],
                schema=RouteDecision,
            )
            return decision, usage
        except LLMError as exc:
            _LOGGER.warning("Enrutamiento por LLM falló (%s); se usan reglas deterministas.", exc)
            fallback = rule_based_classify(user_input)
            fallback.reasoning = (
                f"[fallback determinista tras error del proveedor] {fallback.reasoning}"
            )
            return fallback, Usage()
