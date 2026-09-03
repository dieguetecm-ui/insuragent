"""Cada módulo debe poder importarse en frío.

Un ciclo de imports sólo se manifiesta según cuál módulo entre primero, así que
la suite normal puede ocultarlo: si `conftest` ya importó media aplicación, el
ciclo no se dispara. Estas pruebas arrancan un intérprete limpio por módulo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

MODULES = [
    "insuragent.agents",
    "insuragent.agents.prompts",
    "insuragent.cli",
    "insuragent.config",
    "insuragent.data.corpus",
    "insuragent.db.repository",
    "insuragent.evaluation",
    "insuragent.graph",
    "insuragent.llm",
    "insuragent.llm.stub_provider",
    "insuragent.observability",
    "insuragent.rag",
    "insuragent.schemas",
    "insuragent.session",
]


@pytest.mark.parametrize("module", MODULES)
def test_modulo_importa_en_interprete_limpio(module: str):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=SRC,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
