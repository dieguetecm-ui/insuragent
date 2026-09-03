"""Contratos del dominio de pólizas y del recuperador RAG."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CoverageType(StrEnum):
    """Las tres variantes de condiciones generales indexadas (PRD §4.2)."""

    BASICA = "basica"
    AMPLIA = "amplia"
    RC = "rc"


class Coverage(BaseModel):
    """Una cobertura concreta dentro de una variante de condiciones generales."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(description="Identificador estable, ej. `cristales`")
    label: str
    covered: bool
    deductible_pct: Decimal | None = Field(
        default=None, description="Deducible como % de la suma asegurada"
    )
    deductible_min_mxn: Decimal | None = None
    sum_insured_mxn: Decimal | None = None
    notes: str = ""


class Clause(BaseModel):
    """Fragmento indexable de las condiciones generales."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(description="Ej. `AMPLIA-4.2`")
    coverage_type: CoverageType
    title: str
    text: str
    coverage_key: str | None = None


class RetrievedClause(BaseModel):
    """Cláusula devuelta por FAISS junto con su score de similitud."""

    clause: Clause
    score: float = Field(description="Similitud coseno en [-1, 1]; mayor es más cercano")


class Policy(BaseModel):
    """Póliza contratada por un asegurado."""

    model_config = ConfigDict(frozen=True)

    policy_number: str
    coverage_type: CoverageType
    coverages: tuple[Coverage, ...]

    def coverage(self, key: str) -> Coverage | None:
        return next((c for c in self.coverages if c.key == key), None)
