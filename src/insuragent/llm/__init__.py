"""Capa de proveedores de LLM (PRD §4.2)."""

from __future__ import annotations

import logging

from insuragent.config import Settings, get_settings
from insuragent.llm.base import (
    PRICING_USD_PER_MTOK,
    LLMError,
    LLMProvider,
    LLMResponse,
    Message,
    Usage,
)
from insuragent.llm.stub_provider import StubProvider

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "PRICING_USD_PER_MTOK",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "StubProvider",
    "Usage",
    "get_provider",
]


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Instancia el proveedor configurado, verificándolo antes de devolverlo.

    Si el proveedor elegido no está utilizable (sin credenciales, sin red, sin
    el modelo descargado), se degrada al stub determinista con una advertencia
    en lugar de reventar: la demo debe poder levantarse igual. La degradación es
    **visible** — el nombre del proveedor efectivo aparece en la interfaz y en
    el reporte de evaluación, para que nadie confunda una corrida con el stub
    con una medición del modelo real.
    """
    settings = settings or get_settings()

    if settings.llm_provider == "stub":
        return StubProvider()

    try:
        if settings.llm_provider == "ollama":
            from insuragent.llm.ollama_provider import OllamaProvider

            provider: LLMProvider = OllamaProvider(settings)
        else:
            from insuragent.llm.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(settings)

        provider.healthcheck()
        return provider
    except Exception as exc:  # noqa: BLE001 — degradación deliberada
        _LOGGER.warning(
            "El proveedor '%s' no está disponible (%s). Se usará el stub determinista; "
            "las respuestas serán deterministas y NO representan al modelo real.",
            settings.llm_provider,
            exc,
        )
        return StubProvider()
