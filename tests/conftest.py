"""Fixtures compartidas.

Las pruebas corren **siempre** contra el proveedor stub y el embedder hashing:
son deterministas, no tocan la red y no gastan un centavo. La ruta con Claude se
ejercita aparte, con `pytest -m llm` y una API key presente.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Debe fijarse antes de que `insuragent.config` lea el entorno.
os.environ.setdefault("INSURAGENT_LLM_PROVIDER", "stub")
os.environ.setdefault("INSURAGENT_EMBEDDING_BACKEND", "hash")

from insuragent.config import Settings, get_settings  # noqa: E402
from insuragent.data.synthetic import generate_customers  # noqa: E402
from insuragent.db.repository import Repository  # noqa: E402
from insuragent.rag.index import ClauseIndex  # noqa: E402
from insuragent.schemas.auth import Customer  # noqa: E402
from insuragent.schemas.policy import CoverageType  # noqa: E402
from insuragent.session import InsurAgentSession  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Configuración aislada: cada prueba tiene su propio disco."""
    get_settings.cache_clear()
    instance = Settings(
        llm_provider="stub",
        embedding_backend="hash",
        data_dir=tmp_path,
        corpus_dir=tmp_path / "raw",
        index_dir=tmp_path / "index",
        uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.db",
        trace_file=tmp_path / "traces.jsonl",
    )
    instance.ensure_dirs()
    return instance


@pytest.fixture
def repository(settings: Settings) -> Repository:
    repo = Repository(settings.db_path)
    repo.reset()
    for customer in generate_customers(settings.synthetic_customers, settings.synthetic_seed):
        repo.upsert_customer(customer)
    return repo


@pytest.fixture
def clause_index(settings: Settings) -> ClauseIndex:
    return ClauseIndex.build(settings=settings)


@pytest.fixture
def session(
    settings: Settings, repository: Repository, clause_index: ClauseIndex
) -> InsurAgentSession:
    from insuragent.llm import get_provider

    return InsurAgentSession(
        provider=get_provider(settings),
        index=clause_index,
        repository=repository,
        settings=settings,
    )


def _first_with_coverage(repository: Repository, coverage: CoverageType) -> Customer:
    return next(c for c in repository.list_customers() if c.coverage_type == coverage.value)


@pytest.fixture
def amplia_customer(repository: Repository) -> Customer:
    return _first_with_coverage(repository, CoverageType.AMPLIA)


@pytest.fixture
def basica_customer(repository: Repository) -> Customer:
    return _first_with_coverage(repository, CoverageType.BASICA)


@pytest.fixture
def rc_customer(repository: Repository) -> Customer:
    return _first_with_coverage(repository, CoverageType.RC)


@pytest.fixture
def png_bytes() -> bytes:
    """PNG 1×1 válido, para la carga de evidencia."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
        "0000000049454e44ae426082"
    )
