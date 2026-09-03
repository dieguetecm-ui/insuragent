"""Contratos del reporte de siniestro (First Notice of Loss, PRD §6.5).

El agente FNOL construye un `IncidentDraft` de forma incremental a lo largo de
la conversación; sólo cuando todos los campos obligatorios están presentes se
promueve a `ClaimReport`, que es lo único que se persiste. Esa separación es lo
que impide que una alucinación del LLM llegue a la base transaccional.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentType(StrEnum):
    CRISTALES = "cristales"
    COLISION = "colision"
    ROBO_TOTAL = "robo_total"
    ROBO_PARCIAL = "robo_parcial"
    DANOS_TERCEROS = "danos_terceros"
    OTRO = "otro"


REQUIRED_DRAFT_FIELDS = ("incident_type", "incident_date", "location", "description")


class IncidentDraft(BaseModel):
    """Borrador acumulado durante la conversación FNOL. Todo es opcional."""

    model_config = ConfigDict(str_strip_whitespace=True)

    incident_type: IncidentType | None = None
    incident_date: date | None = None
    location: str | None = Field(default=None, description="Dónde ocurrió el siniestro")
    description: str | None = Field(default=None, min_length=10)
    third_parties_involved: bool | None = None

    @field_validator("incident_date")
    @classmethod
    def _not_future(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("La fecha del siniestro no puede ser futura")
        return value

    def missing_fields(self) -> list[str]:
        """Campos obligatorios que aún faltan por recolectar."""
        return [name for name in REQUIRED_DRAFT_FIELDS if getattr(self, name) is None]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def merge(self, other: IncidentDraft) -> IncidentDraft:
        """Combina un borrador nuevo sobre el actual sin borrar lo ya capturado."""
        merged = self.model_dump()
        for key, value in other.model_dump().items():
            if value is not None:
                merged[key] = value
        return IncidentDraft.model_validate(merged)


class EvidenceFile(BaseModel):
    """Metadata del archivo de evidencia guardado en disco (PRD §6.5)."""

    model_config = ConfigDict(frozen=True)

    filename: str
    stored_path: Path
    content_type: str
    size_bytes: int = Field(gt=0)
    uploaded_at: datetime


class ClaimReport(BaseModel):
    """Siniestro validado y listo para persistir."""

    model_config = ConfigDict(str_strip_whitespace=True)

    claim_id: str
    customer_id: str
    policy_number: str
    incident_type: IncidentType
    incident_date: date
    location: str
    description: str = Field(min_length=10)
    third_parties_involved: bool = False
    deductible_quoted_mxn: float | None = None
    evidence: tuple[EvidenceFile, ...] = ()
    created_at: datetime

    @classmethod
    def from_draft(
        cls,
        draft: IncidentDraft,
        *,
        claim_id: str,
        customer_id: str,
        policy_number: str,
        deductible_quoted_mxn: float | None = None,
        evidence: tuple[EvidenceFile, ...] = (),
    ) -> ClaimReport:
        """Promueve un borrador completo. Lanza si falta algún campo obligatorio."""
        if missing := draft.missing_fields():
            raise ValueError(f"El borrador está incompleto; faltan: {', '.join(missing)}")
        return cls(
            claim_id=claim_id,
            customer_id=customer_id,
            policy_number=policy_number,
            incident_type=draft.incident_type,  # type: ignore[arg-type]
            incident_date=draft.incident_date,  # type: ignore[arg-type]
            location=draft.location,  # type: ignore[arg-type]
            description=draft.description,  # type: ignore[arg-type]
            third_parties_involved=bool(draft.third_parties_involved),
            deductible_quoted_mxn=deductible_quoted_mxn,
            evidence=evidence,
            created_at=datetime.now(),
        )
