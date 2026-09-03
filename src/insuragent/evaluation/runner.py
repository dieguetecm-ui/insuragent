"""Ejecución del set dorado y cálculo de las métricas del PRD §5.

Cinco métricas, una por criterio de aceptación:

1. Precisión de recuperación RAG — cláusula correcta citada.
2. Precisión del deducible — importe correcto (sub-métrica de la anterior).
3. Precisión de enrutamiento — agente correcto para cada consulta.
4. Latencia promedio por turno.
5. Costo real medido por sesión completa, y tasa de éxito end-to-end del FNOL.

Todas las corridas escriben un JSON con el detalle por caso: una métrica
agregada sin el desglose no permite depurar qué caso se rompió.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from insuragent.agents.orchestrator import Orchestrator
from insuragent.agents.policy_agent import PolicyAgent
from insuragent.config import Settings, get_settings
from insuragent.db.repository import Repository
from insuragent.evaluation.golden import (
    FNOL_SCENARIOS,
    RAG_CASES,
    ROUTING_CASES,
    FNOLScenario,
    RagCase,
    RoutingCase,
)
from insuragent.graph.state import Stage
from insuragent.llm import LLMError, Usage, get_provider
from insuragent.rag.index import ClauseIndex
from insuragent.schemas.auth import Customer
from insuragent.schemas.policy import CoverageType
from insuragent.session import InsurAgentSession

_LOGGER = logging.getLogger(__name__)

DEDUCTIBLE_TOLERANCE_MXN = 1.0


@dataclass(slots=True)
class CaseResult:
    """Resultado de un caso individual."""

    case_id: str
    passed: bool
    expected: str
    observed: str
    latency_ms: float = 0.0
    detail: str = ""


@dataclass(slots=True)
class MetricBlock:
    """Una métrica agregada con su desglose."""

    name: str
    passed: int
    total: int
    results: list[CaseResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        return f"{self.name}: {self.passed}/{self.total} = {self.accuracy:.1%}"


@dataclass(slots=True)
class EvaluationReport:
    """Reporte completo de una corrida de evaluación."""

    provider: str
    """Proveedor efectivamente usado, que puede no ser el configurado."""

    configured_provider: str
    model: str
    embedder: str
    started_at: str
    rag: MetricBlock
    deductible: MetricBlock
    routing: MetricBlock
    fnol: MetricBlock
    latencies_ms: list[float] = field(default_factory=list)
    session_cost_usd: float = 0.0
    session_usage: Usage = field(default_factory=Usage)

    @property
    def avg_latency_ms(self) -> float:
        return statistics.fmean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        return ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured_provider": self.configured_provider,
            "degraded": self.degraded,
            "model": self.model,
            "embedder": self.embedder,
            "started_at": self.started_at,
            "metrics": {
                "rag_precision": self.rag.accuracy,
                "deductible_precision": self.deductible.accuracy,
                "routing_accuracy": self.routing.accuracy,
                "fnol_end_to_end": self.fnol.accuracy,
                "avg_latency_ms": self.avg_latency_ms,
                "p95_latency_ms": self.p95_latency_ms,
                "session_cost_usd": self.session_cost_usd,
                "total_input_tokens": self.session_usage.input_tokens,
                "total_output_tokens": self.session_usage.output_tokens,
            },
            "blocks": {
                block.name: {
                    "passed": block.passed,
                    "total": block.total,
                    "accuracy": block.accuracy,
                    "cases": [asdict(case) for case in block.results],
                }
                for block in (self.rag, self.deductible, self.routing, self.fnol)
            },
        }

    @property
    def degraded(self) -> bool:
        """True si se midió con un proveedor distinto del configurado."""
        return self.provider != self.configured_provider

    def render_text(self) -> str:
        lines = [
            "=" * 68,
            "  InsurAgent — Evaluación (PRD §5)",
            "=" * 68,
            f"  Proveedor      : {self.provider} ({self.model})",
            f"  Embeddings     : {self.embedder}",
            f"  Ejecutado      : {self.started_at}",
        ]
        if self.degraded:
            lines += [
                "-" * 68,
                f"  !! ADVERTENCIA: se configuró '{self.configured_provider}' pero se midió con",
                f"     '{self.provider}'. Estas cifras NO representan al modelo real.",
            ]
        lines += [
            "-" * 68,
            f"  {self.rag.summary()}",
            f"  {self.deductible.summary()}",
            f"  {self.routing.summary()}",
            f"  {self.fnol.summary()}",
            f"  Latencia promedio por turno : {self.avg_latency_ms:.0f} ms",
            f"  Latencia p95                : {self.p95_latency_ms:.0f} ms",
            f"  Costo de sesión completa    : ${self.session_cost_usd:.6f} USD",
            f"  Tokens (entrada/salida)     : {self.session_usage.input_tokens} / {self.session_usage.output_tokens}",
            "-" * 68,
        ]
        for block in (self.rag, self.deductible, self.routing, self.fnol):
            failures = [c for c in block.results if not c.passed]
            if failures:
                lines.append(f"  Fallos en {block.name}:")
                lines += [
                    f"    · {c.case_id}: esperado={c.expected} | observado={c.observed}"
                    for c in failures
                ]
        lines.append("=" * 68)
        return "\n".join(lines)


def _customer_by_coverage(repository: Repository, coverage: CoverageType) -> Customer:
    """Primer asegurado sintético con el paquete pedido."""
    for customer in repository.list_customers():
        if customer.coverage_type == coverage.value:
            return customer
    raise RuntimeError(
        f"No hay clientes con paquete '{coverage.value}' en la base. Corre `make seed` primero."
    )


# ---------------------------------------------------------------------------
# Bloques de evaluación
# ---------------------------------------------------------------------------


def evaluate_rag(
    cases: tuple[RagCase, ...],
    index: ClauseIndex,
    provider,
    repository: Repository,
    top_k: int,
) -> tuple[MetricBlock, MetricBlock, list[float], Usage]:
    """Mide recuperación y cotización de deducible."""
    agent = PolicyAgent(provider, index, top_k=top_k)
    rag_results: list[CaseResult] = []
    deductible_results: list[CaseResult] = []
    latencies: list[float] = []
    usage = Usage()

    for case in cases:
        customer = _customer_by_coverage(repository, case.coverage_type)
        started = time.perf_counter()
        answer = agent.answer(case.question, customer)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        usage = usage + answer.usage

        hit = any(clause_id in answer.citations for clause_id in case.expected_clauses)
        rag_results.append(
            CaseResult(
                case_id=case.case_id,
                passed=hit,
                expected=" | ".join(case.expected_clauses),
                observed=", ".join(answer.citations) or "(sin citas)",
                latency_ms=elapsed,
                detail=case.note,
            )
        )

        observed_deductible = answer.quote.deductible_mxn if answer.quote else None
        if case.expected_deductible_mxn is None:
            correct = observed_deductible is None
        else:
            correct = (
                observed_deductible is not None
                and abs(observed_deductible - case.expected_deductible_mxn)
                <= DEDUCTIBLE_TOLERANCE_MXN
            )
        deductible_results.append(
            CaseResult(
                case_id=case.case_id,
                passed=correct,
                expected=str(case.expected_deductible_mxn),
                observed=str(observed_deductible),
                latency_ms=elapsed,
                detail=case.note,
            )
        )

    return (
        MetricBlock(
            "precisión_rag", sum(r.passed for r in rag_results), len(rag_results), rag_results
        ),
        MetricBlock(
            "precisión_deducible",
            sum(r.passed for r in deductible_results),
            len(deductible_results),
            deductible_results,
        ),
        latencies,
        usage,
    )


def evaluate_routing(
    cases: tuple[RoutingCase, ...], provider
) -> tuple[MetricBlock, list[float], Usage]:
    """Mide la precisión del orquestador contra la tabla del PRD §3.1."""
    orchestrator = Orchestrator(provider)
    results: list[CaseResult] = []
    latencies: list[float] = []
    usage = Usage()

    for case in cases:
        started = time.perf_counter()
        decision, case_usage = orchestrator.route(case.question)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        usage = usage + case_usage

        results.append(
            CaseResult(
                case_id=case.case_id,
                passed=decision.route is case.expected_route,
                expected=case.expected_route.value,
                observed=decision.route.value,
                latency_ms=elapsed,
                detail=decision.reasoning,
            )
        )
    return (
        MetricBlock(
            "precisión_enrutamiento", sum(r.passed for r in results), len(results), results
        ),
        latencies,
        usage,
    )


def evaluate_fnol(
    scenarios: tuple[FNOLScenario, ...], settings: Settings
) -> tuple[MetricBlock, list[float], Usage]:
    """Recorre los guiones completos y verifica que el expediente se cree (o no).

    La sesión se construye **una sola vez** y se reutiliza reasignando el
    asegurado: instanciarla por escenario recargaría el modelo de embeddings y
    repetiría el healthcheck del proveedor en cada iteración.
    """
    results: list[CaseResult] = []
    latencies: list[float] = []
    usage = Usage()
    session = InsurAgentSession.create(settings)

    for scenario in scenarios:
        customer = _customer_by_coverage(session.repository, scenario.coverage_type)
        session.customer = customer
        session.reset_conversation()

        claim_id: str | None = None
        error = ""
        try:
            for message in scenario.turns:
                turn = session.send(message)
                latencies.append(turn.latency_ms)
                claim_id = turn.claim_id or claim_id

            state_stage = (session.state or {}).get("stage")
            if scenario.evidence and state_stage == Stage.AWAITING_EVIDENCE.value:
                claim = session.attach_evidence("dano.png", _fake_png(), "image/png")
                claim_id = claim.claim_id
            # `total_usage` es el acumulado del estado, que `reset_conversation`
            # pone a cero al inicio de cada escenario: es ya el consumo del guion.
            usage = usage + session.total_usage
        except Exception as exc:  # noqa: BLE001 — el fallo es el resultado del caso
            error = f"{type(exc).__name__}: {exc}"
            _LOGGER.exception("Escenario FNOL %s falló", scenario.scenario_id)

        created = claim_id is not None
        passed = (created == scenario.expect_claim) and not error
        results.append(
            CaseResult(
                case_id=scenario.scenario_id,
                passed=passed,
                expected=f"expediente={'sí' if scenario.expect_claim else 'no'}",
                observed=f"expediente={'sí' if created else 'no'} ({claim_id or '—'})",
                detail=error or scenario.note,
            )
        )

    return (
        MetricBlock("fnol_end_to_end", sum(r.passed for r in results), len(results), results),
        latencies,
        usage,
    )


def _preflight(provider) -> None:
    """Verifica que el proveedor pueda generar, antes de lanzar el set completo.

    El healthcheck del proveedor valida credenciales con una petición gratuita,
    pero no puede saber si la cuenta tiene saldo. Una petición mínima —un token
    de salida— lo confirma por un costo despreciable y evita descubrir el
    problema a mitad de una corrida de decenas de casos.
    """
    try:
        provider.complete(
            system="Responde con una sola palabra.",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
        )
    except LLMError as exc:
        raise RuntimeError(
            f"El proveedor '{provider.name}' no puede generar respuestas: {exc}"
        ) from exc


def _fake_png() -> bytes:
    """PNG mínimo válido (1×1 transparente) para ejercitar la carga de evidencia."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
        "0000000049454e44ae426082"
    )


# ---------------------------------------------------------------------------
# Orquestación de la corrida
# ---------------------------------------------------------------------------


def run_evaluation(
    settings: Settings | None = None, output: Path | None = None
) -> EvaluationReport:
    """Corre las tres familias de casos y devuelve el reporte."""
    settings = settings or get_settings()
    settings.ensure_dirs()

    provider = get_provider(settings)
    index = ClauseIndex.load(settings=settings)
    repository = Repository(settings.db_path)
    repository.initialize()

    if not repository.list_customers():
        raise RuntimeError("La base no tiene clientes. Corre `make seed` antes de evaluar.")

    _preflight(provider)

    rag_block, deductible_block, rag_latencies, rag_usage = evaluate_rag(
        RAG_CASES, index, provider, repository, settings.rag_top_k
    )
    routing_block, routing_latencies, routing_usage = evaluate_routing(ROUTING_CASES, provider)
    fnol_block, fnol_latencies, fnol_usage = evaluate_fnol(FNOL_SCENARIOS, settings)

    total_usage = rag_usage + routing_usage + fnol_usage
    # "Costo por sesión completa" del PRD §5: el guion FNOL end-to-end es
    # exactamente eso — autenticación, consulta de póliza y reporte.
    session_cost = fnol_usage.cost_usd / max(len(FNOL_SCENARIOS), 1)

    report = EvaluationReport(
        provider=provider.name,
        configured_provider=settings.llm_provider,
        model=provider.model,
        embedder=index.embedder_name,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        rag=rag_block,
        deductible=deductible_block,
        routing=routing_block,
        fnol=fnol_block,
        latencies_ms=rag_latencies + routing_latencies + fnol_latencies,
        session_cost_usd=session_cost,
        session_usage=total_usage,
    )

    output = output or (settings.data_dir / "evaluation_report.json")
    output.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if report.degraded:
        _LOGGER.warning(
            "La evaluación corrió con '%s' en lugar de '%s'; las métricas no reflejan al modelo real.",
            report.provider,
            report.configured_provider,
        )
    _LOGGER.info("Reporte de evaluación escrito en %s", output)
    return report
