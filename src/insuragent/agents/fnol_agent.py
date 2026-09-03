"""Agente FNOL — recolección y registro del siniestro (PRD §3, §6.5).

El agente nunca escribe en la base directamente desde texto del modelo. El ciclo
es: extraer con salida estructurada → fusionar sobre el borrador acumulado →
validar con Pydantic → sólo entonces persistir. Un dato que el modelo no logre
extraer se queda en `None` y se vuelve a preguntar, que es lo correcto en un
proceso de siniestros.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from insuragent.agents.prompts import FNOL_EXTRACTION_SYSTEM, FNOL_SYSTEM
from insuragent.agents.tools import INCIDENT_TO_COVERAGE, quote_deductible
from insuragent.db.repository import Repository
from insuragent.llm import LLMError, LLMProvider, Usage
from insuragent.llm.stub_provider import extract_incident as rule_based_extract
from insuragent.schemas.auth import Customer
from insuragent.schemas.fnol import ClaimReport, EvidenceFile, IncidentDraft
from insuragent.schemas.policy import CoverageType

_LOGGER = logging.getLogger(__name__)

FIELD_LABELS = {
    "incident_type": "tipo de siniestro",
    "incident_date": "fecha del siniestro",
    "location": "lugar donde ocurrió",
    "description": "descripción de lo sucedido",
}

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_EVIDENCE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@dataclass(slots=True)
class FNOLTurn:
    """Resultado de un turno del agente FNOL."""

    text: str
    draft: IncidentDraft
    complete: bool
    usage: Usage = field(default_factory=Usage)
    missing: list[str] = field(default_factory=list)


class FNOLAgent:
    """Conduce la conversación de reporte y persiste el expediente."""

    def __init__(self, provider: LLMProvider, repository: Repository, uploads_dir: Path) -> None:
        self._provider = provider
        self._repository = repository
        self._uploads_dir = uploads_dir

    # -- extracción ---------------------------------------------------------

    def extract(self, user_input: str) -> tuple[IncidentDraft, Usage]:
        """Extrae campos del mensaje. Cae a heurísticas si el proveedor falla."""
        prompt = f"FECHA DE HOY: {date.today().isoformat()}\n\nMensaje del asegurado:\n{user_input}"
        try:
            draft, usage = self._provider.structured(
                system=FNOL_EXTRACTION_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                schema=IncidentDraft,
            )
            return draft, usage
        except LLMError as exc:
            _LOGGER.warning("Extracción FNOL por LLM falló (%s); se usan heurísticas.", exc)
            return rule_based_extract(user_input), Usage()

    # -- conversación -------------------------------------------------------

    def collect(self, user_input: str, draft: IncidentDraft, customer: Customer) -> FNOLTurn:
        """Procesa un turno: fusiona lo nuevo y pide lo que siga faltando."""
        extracted, extraction_usage = self.extract(user_input)
        merged = draft.merge(extracted)
        missing = merged.missing_fields()

        if not missing:
            return FNOLTurn(
                text=(
                    "Ya tengo todos los datos de tu reporte. Para completar el expediente, "
                    "¿podrías adjuntar una fotografía del daño? Quedará vinculada a tu siniestro."
                ),
                draft=merged,
                complete=True,
                usage=extraction_usage,
                missing=[],
            )

        pending = ", ".join(FIELD_LABELS[name] for name in missing)
        captured = {k: v for k, v in merged.model_dump(mode="json").items() if v is not None}
        response = self._provider.complete(
            system=FNOL_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Asegurado: {customer.full_name} | Póliza {customer.policy_number}.\n"
                        f"DATOS YA CAPTURADOS: {captured or 'ninguno'}\n"
                        f"DATOS FALTANTES: {pending}\n\n"
                        f"Último mensaje del asegurado: {user_input}"
                    ),
                }
            ],
        )
        text = response.text or f"Para continuar con tu reporte necesito: {pending}."
        return FNOLTurn(
            text=text,
            draft=merged,
            complete=False,
            usage=extraction_usage + response.usage,
            missing=missing,
        )

    # -- evidencia y persistencia ------------------------------------------

    def store_evidence(
        self, claim_id: str, filename: str, content: bytes, content_type: str
    ) -> EvidenceFile:
        """Guarda el archivo en disco y devuelve su metadata validada (PRD §6.5).

        La validación de tipo y tamaño ocurre aquí, antes de tocar el disco: es
        la única frontera por la que entra un binario al sistema.
        """
        if content_type not in ALLOWED_EVIDENCE_TYPES:
            raise ValueError(f"Tipo de archivo no permitido: {content_type}")
        if not content:
            raise ValueError("El archivo de evidencia está vacío")
        if len(content) > MAX_EVIDENCE_BYTES:
            raise ValueError(
                f"El archivo excede el máximo de {MAX_EVIDENCE_BYTES // (1024 * 1024)} MB"
            )

        target_dir = self._uploads_dir / claim_id
        target_dir.mkdir(parents=True, exist_ok=True)
        # Se conserva sólo el nombre base: un `filename` con rutas relativas no
        # debe poder escribir fuera del directorio de evidencia.
        safe_name = Path(filename).name or "evidencia"
        stored_path = target_dir / f"{datetime.now():%Y%m%d%H%M%S}_{safe_name}"
        stored_path.write_bytes(content)

        return EvidenceFile(
            filename=safe_name,
            stored_path=stored_path,
            content_type=content_type,
            size_bytes=len(content),
            uploaded_at=datetime.now(),
        )

    def finalize(
        self,
        draft: IncidentDraft,
        customer: Customer,
        evidence: tuple[EvidenceFile, ...] = (),
        claim_id: str | None = None,
    ) -> ClaimReport:
        """Promueve el borrador a expediente y lo persiste.

        Lanza `ValueError` si el borrador está incompleto: es la última barrera
        antes de la base transaccional.
        """
        claim_id = claim_id or self._repository.next_claim_id()
        deductible = None
        if draft.incident_type is not None:
            coverage_key = INCIDENT_TO_COVERAGE.get(draft.incident_type)
            if coverage_key:
                quote = quote_deductible(CoverageType(customer.coverage_type), coverage_key)
                deductible = quote.deductible_mxn

        claim = ClaimReport.from_draft(
            draft,
            claim_id=claim_id,
            customer_id=customer.customer_id,
            policy_number=customer.policy_number,
            deductible_quoted_mxn=deductible,
            evidence=evidence,
        )
        self._repository.save_claim(claim)
        _LOGGER.info("Siniestro %s registrado para %s", claim.claim_id, customer.customer_id)
        return claim
