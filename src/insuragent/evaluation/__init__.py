"""Evaluación de la PoC contra los criterios de aceptación (PRD §5)."""

from insuragent.evaluation.golden import FNOL_SCENARIOS, RAG_CASES, ROUTING_CASES
from insuragent.evaluation.runner import EvaluationReport, run_evaluation
from insuragent.evaluation.transcripts import GUIONES, Transcript, capture_transcripts

__all__ = [
    "FNOL_SCENARIOS",
    "GUIONES",
    "RAG_CASES",
    "ROUTING_CASES",
    "EvaluationReport",
    "Transcript",
    "capture_transcripts",
    "run_evaluation",
]
