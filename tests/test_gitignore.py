"""El `.gitignore` es un control de seguridad, así que se prueba como tal.

Un secreto sólo se filtra una vez: después de un `git push` está en el historial
público para siempre, aunque se borre en el commit siguiente. Estas pruebas
crean un repositorio desechable con el `.gitignore` real y le preguntan a git
—no a una expresión regular propia— qué subiría.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GITIGNORE = PROJECT_ROOT / ".gitignore"

# Rutas que jamás deben llegar a un repositorio público.
RUTAS_PROHIBIDAS = [
    ".env",
    ".env.local",
    ".env.production",
    "produccion.env",
    "service-account.json",
    "credentials.json",
    "client_secret_123.json",
    "id_rsa",
    "servidor.pem",
    "app.key",
    ".streamlit/secrets.toml",
    "data/transcripts.db",
    "data/transcripts.json",
    "data/insuragent.db",
    "data/traces.jsonl",
    "data/evaluation_report.json",
    "data/uploads/SIN-202609-00001/foto.png",
    "data/index/clauses.faiss",
    "infra/terraform/terraform.tfstate",
    "infra/terraform/terraform.tfstate.backup",
    "infra/terraform/terraform.tfvars",
    "infra/terraform/.terraform/plugin.bin",
    "docs/report.html",
    "streamlit.log",
]

# Archivos que sí forman parte del proyecto y no deben perderse por exceso de celo.
RUTAS_REQUERIDAS = [
    ".env.example",
    "infra/terraform/terraform.tfvars.example",
    "infra/terraform/main.tf",
    "data/raw/condiciones_generales_amplia.md",
    "src/insuragent/config.py",
    "requirements.txt",
    "README.md",
    # El PDF es el entregable 2 del PRD §2: debe leerse desde GitHub sin clonar.
    "docs/report.pdf",
    # El despliegue en Streamlit Cloud lee estos del repositorio.
    "streamlit_app.py",
    ".streamlit/config.toml",
    ".streamlit/secrets.toml.example",
    "requirements-embeddings.txt",
]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git no está instalado")


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    """Repositorio desechable con el `.gitignore` real y las rutas de prueba."""
    root = tmp_path_factory.mktemp("gitignore")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    shutil.copy(GITIGNORE, root / ".gitignore")

    for relative in RUTAS_PROHIBIDAS + RUTAS_REQUERIDAS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    return root


def _ignorada(repo: Path, relative: str) -> bool:
    return (
        subprocess.run(["git", "check-ignore", "-q", relative], cwd=repo, check=False).returncode
        == 0
    )


@pytest.mark.parametrize("relative", RUTAS_PROHIBIDAS)
def test_ruta_sensible_esta_ignorada(repo: Path, relative: str):
    assert _ignorada(repo, relative), f"{relative} se subiría al repositorio"


@pytest.mark.parametrize("relative", RUTAS_REQUERIDAS)
def test_archivo_del_proyecto_no_esta_ignorado(repo: Path, relative: str):
    assert not _ignorada(repo, relative), f"{relative} quedaría fuera del repositorio"


def test_ningun_archivo_versionable_contiene_una_llave():
    """Escaneo del árbol real: ningún archivo que se versionaría lleva un secreto."""
    import re

    patrones = re.compile(
        r"sk-ant-[A-Za-z0-9_-]{20,}"  # Anthropic
        r"|AIza[0-9A-Za-z_-]{30,}"  # Google
        r"|AKIA[0-9A-Z]{16}"  # AWS
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"  # llaves privadas
    )
    excluidos = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "data", ".venv"}
    hallazgos = []

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.name == ".env" or path.name == Path(__file__).name:
            continue
        if excluidos & set(path.relative_to(PROJECT_ROOT).parts):
            continue
        try:
            contenido = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if patrones.search(contenido):
            hallazgos.append(str(path.relative_to(PROJECT_ROOT)))

    assert not hallazgos, f"Posibles secretos en: {', '.join(hallazgos)}"
