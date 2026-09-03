"""Contratos de datos (PRD §4.3).

Toda información que cruza una frontera del sistema — entrada del usuario,
salida estructurada del LLM, escritura a SQLite — pasa por uno de estos modelos.
"""

from insuragent.schemas.auth import Customer, LoginRequest, Vehicle
from insuragent.schemas.fnol import ClaimReport, EvidenceFile, IncidentDraft
from insuragent.schemas.policy import Clause, Coverage, Policy, RetrievedClause
from insuragent.schemas.routing import Route, RouteDecision

__all__ = [
    "Clause",
    "ClaimReport",
    "Coverage",
    "Customer",
    "EvidenceFile",
    "IncidentDraft",
    "LoginRequest",
    "Policy",
    "RetrievedClause",
    "Route",
    "RouteDecision",
    "Vehicle",
]
