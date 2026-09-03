"""Agente de Red — talleres con convenio (PRD §3)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from insuragent.agents.prompts import NETWORK_SYSTEM
from insuragent.agents.tools import lookup_workshops
from insuragent.data.network import Workshop
from insuragent.llm import LLMProvider, Usage
from insuragent.schemas.auth import Customer

# "cerca de Polanco", "en Guadalajara", "por Del Valle"
_LOCATION_RE = re.compile(
    r"(?:cerca de|cerca del|por|en|zona de|colonia)\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ]*(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]*){0,3})"
)


@dataclass(slots=True)
class NetworkAnswer:
    text: str
    workshops: list[Workshop] = field(default_factory=list)
    location: str = ""
    usage: Usage = field(default_factory=Usage)


def extract_location(text: str, fallback: str) -> str:
    """Ubicación mencionada; si no hay ninguna, la ciudad registrada del asegurado."""
    match = _LOCATION_RE.search(text)
    return match.group(1).strip() if match else fallback


class NetworkAgent:
    """Consulta la red de servicio según la ubicación del incidente."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def answer(
        self, question: str, customer: Customer, specialty: str | None = None
    ) -> NetworkAnswer:
        location = extract_location(question, customer.city)
        workshops = lookup_workshops(location, specialty=specialty)
        context = "\n".join(f"- {w.describe()}" for w in workshops) or "Sin talleres disponibles."

        response = self._provider.complete(
            system=NETWORK_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Ubicación solicitada: {location}. "
                        f"Ciudad registrada del asegurado: {customer.city}.\n\n"
                        f"<contexto>\n{context}\n</contexto>\n\n"
                        f"Pregunta del asegurado: {question}"
                    ),
                }
            ],
        )
        return NetworkAnswer(
            text=response.text,
            workshops=workshops,
            location=location,
            usage=response.usage,
        )
