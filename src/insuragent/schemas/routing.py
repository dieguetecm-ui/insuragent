"""Salida estructurada del Agente Orquestador (PRD §3.1).

El enrutamiento se resuelve con *structured outputs* sobre el LLM: el modelo
devuelve un JSON que valida contra `RouteDecision`, sin clasificador adicional.
El campo `reasoning` es lo que se guarda en la traza para poder auditar después
por qué una consulta terminó en cierto agente.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Route(StrEnum):
    """Destinos posibles del orquestador."""

    POLICY = "policy"
    FNOL = "fnol"
    NETWORK = "network"
    SMALLTALK = "smalltalk"


ROUTE_DESCRIPTIONS: dict[Route, str] = {
    Route.POLICY: "Preguntas sobre coberturas, cláusulas, deducibles o alcance de la póliza.",
    Route.FNOL: "El usuario quiere reportar o registrar formalmente un siniestro.",
    Route.NETWORK: "El usuario busca talleres, grúas o ubicaciones de la red con convenio.",
    Route.SMALLTALK: "Saludos, agradecimientos o consultas fuera del alcance del ramo de autos.",
}


class RouteDecision(BaseModel):
    """Decisión de enrutamiento emitida por el orquestador."""

    route: Route = Field(description="Agente al que debe dirigirse la consulta")
    confidence: float = Field(ge=0.0, le=1.0, description="Confianza de la clasificación")
    reasoning: str = Field(
        max_length=400,
        description="Justificación breve; se persiste en la traza para auditoría",
    )
