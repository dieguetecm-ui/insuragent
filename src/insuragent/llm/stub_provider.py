"""Proveedor determinista sin red ni costo.

No pretende ser un modelo: es un doble de pruebas. Permite ejercitar el grafo
completo, la persistencia y la interfaz en CI o sin API key, y sirve de línea
base contra la cual comparar el enrutamiento del LLM real en la evaluación
(PRD §5) — si el modelo no supera a estas reglas, no está aportando.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from insuragent.llm.base import LLMProvider, LLMResponse, Message, T, Usage
from insuragent.prompt_markers import USER_MESSAGE_MARKERS
from insuragent.schemas.fnol import IncidentDraft, IncidentType
from insuragent.schemas.routing import Route, RouteDecision

FNOL_KEYWORDS = (
    "reportar",
    "reporte",
    "levantar",
    "denunciar",
    "abrir un siniestro",
    "dar aviso",
    "quiero declarar",
)
NETWORK_KEYWORDS = (
    "taller",
    "talleres",
    "grua",
    "grúa",
    "cerca de",
    "ubicacion",
    "ubicación",
    "sucursal",
    "convenio",
)
POLICY_KEYWORDS = (
    "cubre",
    "cobertura",
    "deducible",
    "poliza",
    "póliza",
    "clausula",
    "cláusula",
    "ampara",
    "suma asegurada",
    "limite",
    "límite",
    "excluye",
    "exclusion",
    "exclusión",
)
SMALLTALK_KEYWORDS = ("hola", "buenos dias", "buenas tardes", "gracias", "adios", "adiós")

INCIDENT_KEYWORDS: dict[IncidentType, tuple[str, ...]] = {
    IncidentType.CRISTALES: (
        "cristal",
        "parabrisas",
        "medallon",
        "medallón",
        "vidrio",
        "quemacocos",
    ),
    IncidentType.ROBO_TOTAL: (
        "robo total",
        "se robaron el auto",
        "me robaron el coche",
        "robaron mi auto",
    ),
    IncidentType.ROBO_PARCIAL: ("robo parcial", "espejo", "autoestereo", "llantas"),
    IncidentType.COLISION: (
        "choque",
        "choqué",
        "colision",
        "colisión",
        "golpe",
        "volcadura",
        "impacto",
    ),
    IncidentType.DANOS_TERCEROS: (
        "tercero",
        "le pegue a",
        "le pegué a",
        "dañe el auto de",
        "dañé el auto de",
    ),
}


def isolate_user_message(prompt: str) -> str:
    """Recorta el andamiaje del prompt y devuelve el mensaje literal del asegurado.

    Sin esto, las heurísticas del stub leerían las instrucciones y los datos de
    contexto que los agentes anteponen (por ejemplo «FECHA DE HOY: 2026-09-02»)
    como si fueran parte de lo que dijo la persona.
    """
    for marker in USER_MESSAGE_MARKERS:
        if marker in prompt:
            return prompt.rsplit(marker, 1)[1].strip()
    return prompt.strip()


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def classify(text: str) -> RouteDecision:
    """Clasificación por palabras clave, con la precedencia de la tabla PRD §3.1."""
    normalized = _normalize(text)

    def hits(keywords: tuple[str, ...]) -> list[str]:
        return [k for k in keywords if _normalize(k) in normalized]

    if found := hits(NETWORK_KEYWORDS):
        return RouteDecision(
            route=Route.NETWORK,
            confidence=0.8,
            reasoning=f"Menciona la red de servicio: {', '.join(found)}.",
        )
    if found := hits(FNOL_KEYWORDS):
        return RouteDecision(
            route=Route.FNOL,
            confidence=0.85,
            reasoning=f"Intención explícita de reportar: {', '.join(found)}.",
        )
    if found := hits(POLICY_KEYWORDS):
        return RouteDecision(
            route=Route.POLICY,
            confidence=0.8,
            reasoning=f"Pregunta sobre condiciones de la póliza: {', '.join(found)}.",
        )
    # Un siniestro narrado sin intención explícita se evalúa primero contra la
    # póliza y sólo después se ofrece el reporte (PRD §6.3–6.4).
    if any(hits(words) for words in INCIDENT_KEYWORDS.values()):
        return RouteDecision(
            route=Route.POLICY,
            confidence=0.6,
            reasoning="Narra un siniestro sin pedir el reporte; se evalúa la cobertura primero.",
        )
    if hits(SMALLTALK_KEYWORDS):
        return RouteDecision(route=Route.SMALLTALK, confidence=0.7, reasoning="Saludo o cortesía.")
    return RouteDecision(
        route=Route.POLICY,
        confidence=0.4,
        reasoning="Sin señales claras; por defecto se consulta la póliza.",
    )


def extract_incident(text: str) -> IncidentDraft:
    """Extracción heurística de los campos del siniestro."""
    normalized = _normalize(text)
    draft = IncidentDraft()

    for incident_type, keywords in INCIDENT_KEYWORDS.items():
        if any(_normalize(k) in normalized for k in keywords):
            draft.incident_type = incident_type
            break

    if "ayer" in normalized:
        draft.incident_date = date.today() - timedelta(days=1)
    elif "hoy" in normalized:
        draft.incident_date = date.today()
    elif match := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
        draft.incident_date = date.fromisoformat(match.group(0))

    if match := re.search(r"\ben ([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40})", text):
        draft.location = match.group(1).strip()

    if len(text.strip()) >= 10:
        draft.description = text.strip()

    if any(word in normalized for word in ("tercero", "otro auto", "otra persona")):
        draft.third_parties_involved = True

    return draft


class StubProvider(LLMProvider):
    """Implementación de `LLMProvider` sin dependencias externas."""

    name = "stub"
    model = "stub-deterministic"

    def complete(
        self, *, system: str, messages: list[Message], max_tokens: int | None = None
    ) -> LLMResponse:
        """Devuelve el contexto recuperado, sin parafrasear.

        Es intencional: el stub no redacta, sólo demuestra que el contexto
        correcto llegó al agente. Así, un fallo en la evaluación RAG apunta al
        recuperador y no a la redacción del modelo.
        """
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        context = re.search(r"<contexto>(.*?)</contexto>", last_user, re.DOTALL)
        body = (
            context.group(1).strip()
            if context
            else "No hay contexto recuperado para esta consulta."
        )
        return LLMResponse(text=body, usage=Usage())

    def structured(
        self, *, system: str, messages: list[Message], schema: type[T]
    ) -> tuple[T, Usage]:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        user_message = isolate_user_message(last_user)
        if schema is RouteDecision:
            return classify(user_message), Usage()  # type: ignore[return-value]
        if schema is IncidentDraft:
            return extract_incident(user_message), Usage()  # type: ignore[return-value]
        return schema(), Usage()  # type: ignore[call-arg]
