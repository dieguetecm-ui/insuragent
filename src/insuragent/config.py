"""Configuración central de la aplicación.

Todo el estado configurable vive aquí; ningún módulo lee `os.environ`
directamente. Las rutas se resuelven contra la raíz del repositorio para que la
app funcione igual desde `make`, desde Streamlit o desde un test.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

LLMProviderName = Literal["anthropic", "ollama", "stub"]
EmbeddingBackend = Literal["sentence-transformers", "hash"]
EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    """Parámetros de ejecución, poblados desde `.env` o el entorno."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="INSURAGENT_",
        extra="ignore",
    )

    # --- LLM ---------------------------------------------------------------
    llm_provider: LLMProviderName = "anthropic"
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="ANTHROPIC_API_KEY",
        description=(
            "SecretStr, no str: pydantic la enmascara al representar el objeto. Sin eso, "
            "cualquier traza de error, log de depuración o fallo de prueba que imprima la "
            "configuración publica la llave en claro."
        ),
    )
    anthropic_workspace_id: str = Field(
        default="",
        validation_alias="ANTHROPIC_WORKSPACE_ID",
        description=(
            "Obligatorio cuando la API key está ligada a una identidad: la API "
            "responde 400 sin la cabecera `anthropic-workspace-id`. Vacío para "
            "llaves de organización, que no la requieren."
        ),
    )
    anthropic_model: str = "claude-opus-5"
    max_tokens: int = Field(default=2048, ge=256, le=64_000)
    effort: EffortLevel = "low"
    max_retries: int = Field(
        default=5,
        ge=0,
        le=10,
        description=(
            "Reintentos del SDK ante 429, 5xx y el 529 'overloaded' de Anthropic. "
            "El valor por omisión del SDK es 2, insuficiente para una corrida de evaluación "
            "de decenas de peticiones seguidas: basta un pico de carga para perderla entera."
        ),
    )

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    # --- RAG ---------------------------------------------------------------
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_backend: EmbeddingBackend = "sentence-transformers"
    rag_top_k: int = Field(default=4, ge=1, le=20)

    # --- Rutas -------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    corpus_dir: Path = PROJECT_ROOT / "data" / "raw"
    index_dir: Path = PROJECT_ROOT / "data" / "index"
    uploads_dir: Path = PROJECT_ROOT / "data" / "uploads"
    db_path: Path = PROJECT_ROOT / "data" / "insuragent.db"

    # --- Despliegue --------------------------------------------------------
    public_url: str = Field(
        default="",
        description=(
            "URL del servicio desplegado. Cuando está definida, el reporte PDF la publica "
            "junto con las credenciales de prueba para que el lector entre sin instalar nada. "
            "Vacía, el reporte explica cómo levantarlo en local."
        ),
    )

    # --- Observabilidad ----------------------------------------------------
    log_level: str = "INFO"
    trace_file: Path = PROJECT_ROOT / "data" / "traces.jsonl"

    # --- Datos sintéticos --------------------------------------------------
    synthetic_seed: int = 20260902
    synthetic_customers: int = Field(default=12, ge=1, le=500)

    @field_validator("data_dir", "corpus_dir", "index_dir", "uploads_dir", mode="after")
    @classmethod
    def _absolutize(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value)

    def ensure_dirs(self) -> None:
        """Crea los directorios de trabajo si aún no existen.

        El de evidencia se restringe al propietario: guarda fotografías de los
        vehículos de personas concretas. Los demás sólo contienen el corpus
        sintético y el índice, que no son datos personales.
        """
        from insuragent.fs import restringir

        for directory in (self.data_dir, self.corpus_dir, self.index_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)
        restringir(self.uploads_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instancia única de configuración (cacheada por proceso)."""
    return Settings()
