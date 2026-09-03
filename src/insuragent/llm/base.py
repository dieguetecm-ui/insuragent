"""Contrato común de los proveedores de LLM.

Los agentes dependen de esta interfaz, no de un SDK concreto. Eso permite las
tres rutas que contempla el PRD (§4.2 y §8): Claude API como ruta principal,
Ollama como alternativa local de costo cero, y un stub determinista para correr
la suite de pruebas sin red ni gasto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

Message = dict[str, str]

# Precio por millón de tokens (USD). Usado para la métrica de costo del PRD §5.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


@dataclass(slots=True)
class Usage:
    """Consumo de una llamada al modelo."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )

    @classmethod
    def priced(cls, model: str, input_tokens: int, output_tokens: int) -> Usage:
        """Calcula el costo con la tarifa del modelo; 0.0 si no está tarifado."""
        rate_in, rate_out = PRICING_USD_PER_MTOK.get(model, (0.0, 0.0))
        cost = (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000
        return cls(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)


@dataclass(slots=True)
class LLMResponse:
    """Respuesta en texto libre de un proveedor."""

    text: str
    usage: Usage = field(default_factory=Usage)


class LLMError(RuntimeError):
    """Fallo recuperable al hablar con el proveedor."""


class LLMProvider(ABC):
    """Interfaz mínima que necesitan los agentes de InsurAgent."""

    name: str
    model: str

    def healthcheck(self) -> None:  # noqa: B027 — el no-op por defecto es deliberado
        """Verifica que el proveedor sea utilizable; lanza `LLMError` si no.

        No es abstracto a propósito: un proveedor sin dependencias externas —el
        stub— siempre está sano, y obligarlo a implementar un método vacío no
        aporta nada.

        Existe porque el SDK de Anthropic construye el cliente sin validar
        credenciales: el fallo aparece hasta la primera petición, ya en mitad de
        una conversación. Comprobarlo al arrancar permite degradar de forma
        ordenada en vez de reventar en el primer turno del asegurado.
        """

    @abstractmethod
    def complete(
        self, *, system: str, messages: list[Message], max_tokens: int | None = None
    ) -> LLMResponse:
        """Genera una respuesta en lenguaje natural."""

    @abstractmethod
    def structured(
        self, *, system: str, messages: list[Message], schema: type[T]
    ) -> tuple[T, Usage]:
        """Genera una salida que valida contra `schema`.

        Es el mecanismo con el que el Orquestador clasifica intenciones y el
        agente FNOL extrae campos del siniestro, sin clasificador adicional
        (PRD §3.1).
        """
