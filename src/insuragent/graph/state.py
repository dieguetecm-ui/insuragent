"""Estado del grafo conversacional (PRD §3.2 — memoria de corto plazo).

`ConversationState` es la memoria de sesión: lo que el sistema sabe *ahora mismo*
del turno en curso. La memoria de largo plazo (historial, siniestros previos)
vive en SQLite y se consulta a través del `Repository`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from insuragent.llm import Usage
from insuragent.schemas.auth import Customer
from insuragent.schemas.fnol import IncidentDraft, IncidentType
from insuragent.schemas.routing import Route


class Stage(StrEnum):
    """Fase del flujo del PRD §6 en la que se encuentra la conversación."""

    IDLE = "idle"
    """Conversación libre: cada turno se enruta desde cero."""

    CONFIRM_FNOL = "confirm_fnol"
    """Se evaluó la póliza y se preguntó si desea reportar (PRD §6.4)."""

    COLLECTING = "collecting"
    """El agente FNOL está recolectando los datos del siniestro."""

    AWAITING_EVIDENCE = "awaiting_evidence"
    """Datos completos; falta la fotografía del daño."""

    DONE = "done"
    """Expediente registrado."""


class ConversationState(TypedDict, total=False):
    """Estado que circula entre los nodos del grafo."""

    # Entrada del turno
    user_input: str
    customer: Customer
    run_id: str

    # Memoria de largo plazo cargada al iniciar sesión (PRD §3.2)
    claim_history: list[dict]

    # Máquina de estados del flujo FNOL
    stage: str
    draft: IncidentDraft
    pending_incident: IncidentType | None
    claim_id: str | None

    # Resultado del enrutamiento
    route: str
    route_confidence: float
    route_reasoning: str

    # Salida del turno
    answer: str
    citations: list[str]
    retrieval: list[dict]
    """Cláusulas recuperadas con su score, para poder auditar la respuesta."""
    history_used: int
    deductible_mxn: float | None
    workshop_ids: list[str]
    usage: Usage


def initial_state(customer: Customer, claim_history: list[dict] | None = None) -> ConversationState:
    """Estado limpio al iniciar sesión un asegurado.

    El historial se carga una sola vez al abrir la sesión, no en cada turno: es
    memoria de largo plazo y no cambia a mitad de una conversación, salvo cuando
    el propio asegurado registra un siniestro nuevo.
    """
    return ConversationState(
        customer=customer,
        claim_history=list(claim_history or []),
        stage=Stage.IDLE.value,
        draft=IncidentDraft(),
        pending_incident=None,
        claim_id=None,
        citations=[],
        retrieval=[],
        history_used=0,
        workshop_ids=[],
        usage=Usage(),
    )


def route_of(state: ConversationState) -> Route:
    return Route(state.get("route", Route.POLICY.value))
