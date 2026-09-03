"""Fachada de sesión: une autenticación, grafo y memoria.

Es el único objeto que la interfaz (Streamlit) y la evaluación necesitan
conocer. Encapsular el cableado aquí evita que la UI construya agentes a mano y
mantiene un solo lugar donde cambiar el orden de inicialización.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from insuragent.agents.fnol_agent import FNOLAgent
from insuragent.agents.network_agent import NetworkAgent
from insuragent.agents.orchestrator import Orchestrator
from insuragent.agents.policy_agent import PolicyAgent
from insuragent.config import Settings, get_settings
from insuragent.db.repository import Repository
from insuragent.graph.build import build_graph
from insuragent.graph.state import ConversationState, Stage, initial_state
from insuragent.llm import LLMProvider, Usage, get_provider
from insuragent.observability import new_run_id
from insuragent.rag.index import ClauseIndex
from insuragent.schemas.auth import Customer, LoginRequest
from insuragent.schemas.fnol import ClaimReport, EvidenceFile

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TurnResult:
    """Lo que devuelve un turno de conversación, listo para pintar y para medir."""

    answer: str
    route: str
    route_reasoning: str
    route_confidence: float
    stage: str
    run_id: str
    latency_ms: float
    citations: list[str] = field(default_factory=list)
    retrieval: list[dict] = field(default_factory=list)
    history_used: int = 0
    workshop_ids: list[str] = field(default_factory=list)
    deductible_mxn: float | None = None
    claim_id: str | None = None
    usage: Usage = field(default_factory=Usage)


class InsurAgentSession:
    """Sesión conversacional de un asegurado autenticado."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        index: ClauseIndex,
        repository: Repository,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.index = index
        self.repository = repository

        self._fnol_agent = FNOLAgent(provider, repository, settings.uploads_dir)
        self._graph = build_graph(
            orchestrator=Orchestrator(provider),
            policy_agent=PolicyAgent(provider, index, top_k=settings.rag_top_k),
            fnol_agent=self._fnol_agent,
            network_agent=NetworkAgent(provider),
        )

        self.customer: Customer | None = None
        self.state: ConversationState | None = None
        self.total_usage = Usage()

    # -- construcción -------------------------------------------------------

    @classmethod
    def create(cls, settings: Settings | None = None) -> InsurAgentSession:
        """Instancia una sesión con todas las dependencias resueltas."""
        settings = settings or get_settings()
        settings.ensure_dirs()
        repository = Repository(settings.db_path)
        repository.initialize()
        return cls(
            provider=get_provider(settings),
            index=ClauseIndex.load(settings=settings),
            repository=repository,
            settings=settings,
        )

    # -- autenticación (PRD §6.1) ------------------------------------------

    def login(self, credentials: LoginRequest) -> Customer | None:
        """Valida credenciales y abre el estado conversacional."""
        customer = self.repository.authenticate(credentials)
        if customer is None:
            _LOGGER.info("Intento de acceso fallido para %s", credentials.policy_number)
            return None
        self.customer = customer
        self.state = initial_state(customer, self.repository.list_claims(customer.customer_id))
        return customer

    def logout(self) -> None:
        self.customer = None
        self.state = None

    @property
    def authenticated(self) -> bool:
        return self.customer is not None and self.state is not None

    # -- conversación -------------------------------------------------------

    def send(self, user_input: str) -> TurnResult:
        """Procesa un turno completo a través del grafo."""
        if not self.authenticated:
            raise RuntimeError("La sesión no está autenticada; llama a login() primero.")
        assert self.state is not None and self.customer is not None

        run_id = new_run_id()
        started = time.perf_counter()

        # Las salidas del turno anterior se limpian antes de entrar al grafo. Sin
        # esto, un turno del agente FNOL —que no recupera nada— arrastraría las
        # cláusulas citadas por el turno anterior del agente de pólizas, y la
        # traza haría creer que las citó él.
        incoming: ConversationState = {
            **self.state,
            "user_input": user_input,
            "run_id": run_id,
            "answer": "",
            "citations": [],
            "retrieval": [],
            "history_used": 0,
            "deductible_mxn": None,
            "workshop_ids": [],
        }
        self.state = self._graph.invoke(incoming)  # type: ignore[assignment]
        latency_ms = (time.perf_counter() - started) * 1000

        turn_usage = self.state.get("usage", Usage())
        self.total_usage = turn_usage  # el estado acumula el consumo de la sesión

        route = self.state.get("route", "")
        answer = self.state.get("answer", "")
        self.repository.append_turn(self.customer.customer_id, run_id, "user", user_input, route)
        self.repository.append_turn(self.customer.customer_id, run_id, "assistant", answer, route)

        return TurnResult(
            answer=answer,
            route=route,
            route_reasoning=self.state.get("route_reasoning", ""),
            route_confidence=self.state.get("route_confidence", 0.0),
            stage=self.state.get("stage", Stage.IDLE.value),
            run_id=run_id,
            latency_ms=latency_ms,
            citations=list(self.state.get("citations", [])),
            retrieval=list(self.state.get("retrieval", [])),
            history_used=int(self.state.get("history_used", 0)),
            workshop_ids=list(self.state.get("workshop_ids", [])),
            deductible_mxn=self.state.get("deductible_mxn"),
            claim_id=self.state.get("claim_id"),
            usage=turn_usage,
        )

    # -- evidencia (PRD §6.5) ----------------------------------------------

    def attach_evidence(self, filename: str, content: bytes, content_type: str) -> ClaimReport:
        """Guarda la evidencia, cierra el expediente y lo persiste.

        Sólo es válido en la etapa `awaiting_evidence`: llamarlo antes
        significaría registrar un siniestro con datos incompletos.
        """
        if not self.authenticated:
            raise RuntimeError("La sesión no está autenticada.")
        assert self.state is not None and self.customer is not None

        stage = self.state.get("stage")
        if stage != Stage.AWAITING_EVIDENCE.value:
            raise RuntimeError(
                f"No se puede adjuntar evidencia en la etapa '{stage}'; "
                f"se requiere '{Stage.AWAITING_EVIDENCE.value}'."
            )

        claim_id = self.repository.next_claim_id()
        evidence: EvidenceFile = self._fnol_agent.store_evidence(
            claim_id, filename, content, content_type
        )
        claim = self._fnol_agent.finalize(
            self.state["draft"], self.customer, evidence=(evidence,), claim_id=claim_id
        )
        self.state = {
            **self.state,
            "stage": Stage.DONE.value,
            "claim_id": claim.claim_id,
            "answer": f"Tu reporte quedó registrado con el folio {claim.claim_id}.",
            # El expediente recién creado pasa a ser memoria de largo plazo de
            # inmediato: si el asegurado pregunta después, el asistente ya lo sabe.
            "claim_history": self.repository.list_claims(self.customer.customer_id),
        }
        return claim

    # -- utilidades ---------------------------------------------------------

    def reset_conversation(self) -> None:
        """Vuelve al estado inicial conservando la autenticación y la memoria larga."""
        if self.customer is not None:
            self.state = initial_state(
                self.customer, self.repository.list_claims(self.customer.customer_id)
            )

    def history(self, limit: int = 20) -> list[dict]:
        if self.customer is None:
            return []
        return self.repository.recent_turns(self.customer.customer_id, limit)

    def past_claims(self) -> list[dict]:
        if self.customer is None:
            return []
        return self.repository.list_claims(self.customer.customer_id)

    @property
    def uploads_dir(self) -> Path:
        return self.settings.uploads_dir
