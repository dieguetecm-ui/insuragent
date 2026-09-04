"""Construcción del grafo de agentes con LangGraph (PRD §3, Fase 3).

Topología:

    START → orquestador → {policy | fnol | network | smalltalk} → END

El nodo condicional es el orquestador. Dos matices que el PRD deja implícitos y
aquí se hacen explícitos:

* Cuando la conversación ya está dentro del flujo FNOL (etapas `collecting` o
  `awaiting_evidence`), el orquestador **no** vuelve a clasificar: el flujo
  tiene continuidad y reclasificar cada turno rompería la recolección a la
  mitad. Se documenta como regla de la máquina de estados, no como accidente.
* La confirmación de "¿deseas reportarlo?" (PRD §6.4) se resuelve con reglas
  deterministas, no con el LLM. Un sí/no no justifica una llamada al modelo,
  ni su latencia, ni su costo, ni su varianza.

Cada nodo se envuelve en `trace_node`, de modo que la traza JSONL permite
reconstruir después por qué se tomó cada decisión (PRD §4.1).
"""

from __future__ import annotations

import logging
import unicodedata

from langgraph.graph import END, START, StateGraph

from insuragent.agents.fnol_agent import FNOLAgent
from insuragent.agents.network_agent import NetworkAgent
from insuragent.agents.orchestrator import Orchestrator
from insuragent.agents.policy_agent import PolicyAgent
from insuragent.graph.state import ConversationState, Stage
from insuragent.llm import Usage
from insuragent.observability import redactar, trace_node
from insuragent.schemas.fnol import IncidentDraft
from insuragent.schemas.routing import Route

_LOGGER = logging.getLogger(__name__)

AFFIRMATIVE = (
    "si",
    "sí",
    "claro",
    "por favor",
    "adelante",
    "ok",
    "va",
    "correcto",
    "afirmativo",
    "quiero reportar",
    "reportalo",
    "repórtalo",
    "dale",
)
NEGATIVE = (
    "no",
    "todavia no",
    "todavía no",
    "ahorita no",
    "despues",
    "después",
    "mejor no",
    "aun no",
    "aún no",
    "gracias no",
)
SKIP_EVIDENCE = (
    "sin foto",
    "no tengo foto",
    "no tengo fotografia",
    "no tengo fotografía",
    "omitir",
    "sin evidencia",
    "despues la subo",
    "después la subo",
    "luego la subo",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def interpret_confirmation(text: str) -> bool | None:
    """Interpreta un sí/no. Devuelve `None` si el mensaje no es ninguno.

    Se comparan tokens completos, no subcadenas: `"no"` dentro de `"nosotros"`
    no debe leerse como negativa.
    """
    normalized = _normalize(text)
    tokens = set(normalized.replace(",", " ").replace(".", " ").split())

    def matches(options: tuple[str, ...]) -> bool:
        return any(
            (opt in tokens) if " " not in opt else (_normalize(opt) in normalized)
            for opt in options
        )

    if matches(NEGATIVE):
        return False
    if matches(AFFIRMATIVE):
        return True
    return None


def wants_to_skip_evidence(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(option) in normalized for option in SKIP_EVIDENCE)


def build_graph(
    orchestrator: Orchestrator,
    policy_agent: PolicyAgent,
    fnol_agent: FNOLAgent,
    network_agent: NetworkAgent,
):
    """Compila el grafo de estados con los agentes ya inyectados."""

    # -- nodos --------------------------------------------------------------

    def orchestrator_node(state: ConversationState) -> ConversationState:
        stage = state.get("stage", Stage.IDLE.value)
        user_input = state.get("user_input", "")

        # El mensaje se registra saneado: es texto que escribe una persona y
        # puede contener identificadores regulados o datos de contacto.
        with trace_node("orchestrator", stage=stage, user_input=redactar(user_input)) as span:
            # Continuidad del flujo FNOL: no se reclasifica a media recolección.
            if stage in {Stage.COLLECTING.value, Stage.AWAITING_EVIDENCE.value}:
                span |= {"route": Route.FNOL.value, "decided_by": "state_machine"}
                return {
                    "route": Route.FNOL.value,
                    "route_confidence": 1.0,
                    "route_reasoning": f"Continuidad del flujo FNOL (etapa {stage}).",
                }

            # Respuesta a "¿deseas reportar el siniestro?" (PRD §6.4).
            if stage == Stage.CONFIRM_FNOL.value:
                answer = interpret_confirmation(user_input)
                if answer is True:
                    span |= {"route": Route.FNOL.value, "decided_by": "confirmation"}
                    return {
                        "route": Route.FNOL.value,
                        "route_confidence": 1.0,
                        "route_reasoning": "El asegurado confirmó que desea reportar el siniestro.",
                        "stage": Stage.COLLECTING.value,
                    }
                if answer is False:
                    span |= {"route": Route.SMALLTALK.value, "decided_by": "confirmation"}
                    return {
                        "route": Route.SMALLTALK.value,
                        "route_confidence": 1.0,
                        "route_reasoning": "El asegurado declinó reportar el siniestro.",
                        "stage": Stage.IDLE.value,
                        "pending_incident": None,
                    }
                # Ni sí ni no: se clasifica normalmente y se sale de la espera.

            decision, usage = orchestrator.route(user_input)
            span |= {
                "route": decision.route.value,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
                "decided_by": "llm",
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": usage.cost_usd,
            }
            next_stage = (
                Stage.COLLECTING.value if decision.route is Route.FNOL else Stage.IDLE.value
            )
            return {
                "route": decision.route.value,
                "route_confidence": decision.confidence,
                "route_reasoning": decision.reasoning,
                "stage": next_stage,
                "usage": state.get("usage", Usage()) + usage,
            }

    def policy_node(state: ConversationState) -> ConversationState:
        customer = state["customer"]
        question = state.get("user_input", "")

        historial = state.get("claim_history", [])
        with trace_node("policy_agent", policy=customer.policy_number) as span:
            result = policy_agent.answer(question, customer, claim_history=historial)
            span |= {
                "history_used": result.history_used,
                "citations": result.citations,
                "retrieval_scores": [round(r.score, 4) for r in result.retrieved],
                "detected_incident": result.detected_incident.value
                if result.detected_incident
                else None,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost_usd": result.usage.cost_usd,
            }

        text = result.text
        update: ConversationState = {
            "answer": text,
            "citations": result.citations,
            "history_used": result.history_used,
            "retrieval": [
                {
                    "clause_id": item.clause.clause_id,
                    "title": item.clause.title,
                    "coverage_type": item.clause.coverage_type.value,
                    "score": round(item.score, 4),
                }
                for item in result.retrieved
            ],
            "deductible_mxn": result.quote.deductible_mxn if result.quote else None,
            "usage": state.get("usage", Usage()) + result.usage,
        }

        # Si narró un siniestro amparado, se ofrece levantar el reporte (PRD §6.4).
        if result.detected_incident and result.quote and result.quote.covered:
            update["answer"] = f"{text}\n\n¿Deseas que levantemos el reporte del siniestro ahora?"
            update["stage"] = Stage.CONFIRM_FNOL.value
            update["pending_incident"] = result.detected_incident
        return update

    def fnol_node(state: ConversationState) -> ConversationState:
        customer = state["customer"]
        user_input = state.get("user_input", "")
        draft: IncidentDraft = state.get("draft") or IncidentDraft()
        stage = state.get("stage", Stage.COLLECTING.value)

        # Arrastra el tipo de siniestro que el agente de pólizas ya identificó.
        pending = state.get("pending_incident")
        if pending is not None and draft.incident_type is None:
            draft = draft.model_copy(update={"incident_type": pending})

        with trace_node("fnol_agent", stage=stage) as span:
            # Etapa final: sólo falta la evidencia.
            if stage == Stage.AWAITING_EVIDENCE.value:
                if wants_to_skip_evidence(user_input):
                    claim = fnol_agent.finalize(draft, customer)
                    span |= {"claim_id": claim.claim_id, "evidence": 0}
                    return {
                        "answer": (
                            f"Listo, tu reporte quedó registrado con el folio **{claim.claim_id}** "
                            "sin evidencia fotográfica. Puedes adjuntarla después desde tu expediente."
                        ),
                        "stage": Stage.DONE.value,
                        "claim_id": claim.claim_id,
                        "draft": draft,
                    }
                span |= {"awaiting": "evidence"}
                return {
                    "answer": (
                        "Sigo esperando la fotografía del daño. Puedes adjuntarla con el botón de carga, "
                        "o escribir «sin foto» si prefieres continuar sin ella."
                    ),
                    "stage": Stage.AWAITING_EVIDENCE.value,
                    "draft": draft,
                }

            turn = fnol_agent.collect(user_input, draft, customer)
            span |= {
                "missing_fields": turn.missing,
                "complete": turn.complete,
                "input_tokens": turn.usage.input_tokens,
                "output_tokens": turn.usage.output_tokens,
                "cost_usd": turn.usage.cost_usd,
            }

        return {
            "answer": turn.text,
            "draft": turn.draft,
            "stage": Stage.AWAITING_EVIDENCE.value if turn.complete else Stage.COLLECTING.value,
            "usage": state.get("usage", Usage()) + turn.usage,
        }

    def network_node(state: ConversationState) -> ConversationState:
        customer = state["customer"]
        with trace_node("network_agent") as span:
            result = network_agent.answer(state.get("user_input", ""), customer)
            span |= {
                "location": result.location,
                "workshops": [w.workshop_id for w in result.workshops],
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost_usd": result.usage.cost_usd,
            }
        return {
            "answer": result.text,
            "workshop_ids": [w.workshop_id for w in result.workshops],
            "usage": state.get("usage", Usage()) + result.usage,
        }

    def smalltalk_node(state: ConversationState) -> ConversationState:
        """Cierre cortés. No consume LLM: el guion es fijo y auditable."""
        declined = state.get("route_reasoning", "").startswith("El asegurado declinó")
        with trace_node("smalltalk", declined=declined):
            if declined:
                text = (
                    "De acuerdo, no levantaremos el reporte por ahora. "
                    "Si cambias de opinión puedes pedírmelo en cualquier momento. "
                    "¿Hay algo más en lo que pueda ayudarte con tu póliza?"
                )
            else:
                text = (
                    "Con gusto te ayudo. Puedo consultar las coberturas y deducibles de tu póliza de auto, "
                    "levantar el reporte de un siniestro o localizarte talleres en convenio. ¿Qué necesitas?"
                )
        return {"answer": text}

    # -- topología ----------------------------------------------------------

    graph = StateGraph(ConversationState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("policy", policy_node)
    graph.add_node("fnol", fnol_node)
    graph.add_node("network", network_node)
    graph.add_node("smalltalk", smalltalk_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        lambda state: state.get("route", Route.POLICY.value),
        {
            Route.POLICY.value: "policy",
            Route.FNOL.value: "fnol",
            Route.NETWORK.value: "network",
            Route.SMALLTALK.value: "smalltalk",
        },
    )
    for node in ("policy", "fnol", "network", "smalltalk"):
        graph.add_edge(node, END)

    return graph.compile()
