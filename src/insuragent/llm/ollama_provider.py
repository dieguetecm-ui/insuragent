"""Proveedor local vía Ollama (PRD §8 — alternativa de costo cero).

Se habla HTTP con la librería estándar a propósito: el runtime de Ollama es
opcional y no debe arrastrar dependencias al proyecto. El endpoint `/api/chat`
acepta `format` con un JSON Schema, que es lo que usamos para las salidas
estructuradas — el equivalente local de `output_config.format`.

Advertencia documentada en el PRD: la fiabilidad del tool-calling / structured
output en modelos de 3B es menor que en la ruta principal. Por eso ésta es la
ruta de respaldo, no la de desarrollo.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from insuragent.config import Settings, get_settings
from insuragent.llm.base import LLMError, LLMProvider, LLMResponse, Message, T, Usage

_LOGGER = logging.getLogger(__name__)
_TIMEOUT_SECONDS = 180


class OllamaProvider(LLMProvider):
    """Cliente mínimo del endpoint `/api/chat` de Ollama."""

    name = "ollama"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.model = self._settings.ollama_model
        self._host = self._settings.ollama_host.rstrip("/")

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self._host}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(
                f"Ollama respondió {exc.code}: {exc.read().decode('utf-8', 'replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMError(
                f"No se pudo contactar Ollama en {self._host}. ¿Está corriendo `ollama serve`?"
            ) from exc

    @staticmethod
    def _usage(payload: dict) -> Usage:
        # Ollama corre en local: los tokens se contabilizan, el costo es cero.
        return Usage(
            input_tokens=payload.get("prompt_eval_count", 0),
            output_tokens=payload.get("eval_count", 0),
            cost_usd=0.0,
        )

    def healthcheck(self) -> None:
        """Confirma que `ollama serve` responde y que el modelo está descargado."""
        request = urllib.request.Request(f"{self._host}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError(
                f"No se pudo contactar Ollama en {self._host}. ¿Está corriendo `ollama serve`?"
            ) from exc

        available = {model.get("name", "") for model in payload.get("models", [])}
        if self.model not in available:
            raise LLMError(
                f"El modelo '{self.model}' no está descargado en Ollama. "
                f"Ejecuta `ollama pull {self.model}`. Disponibles: {', '.join(sorted(available)) or 'ninguno'}."
            )

    def complete(
        self, *, system: str, messages: list[Message], max_tokens: int | None = None
    ) -> LLMResponse:
        payload = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": max_tokens or self._settings.max_tokens,
                },
            },
        )
        return LLMResponse(
            text=payload.get("message", {}).get("content", "").strip(),
            usage=self._usage(payload),
        )

    def structured(
        self, *, system: str, messages: list[Message], schema: type[T]
    ) -> tuple[T, Usage]:
        payload = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": False,
                "format": schema.model_json_schema(),
                "options": {"temperature": 0},
            },
        )
        raw = payload.get("message", {}).get("content", "")
        try:
            return schema.model_validate_json(raw), self._usage(payload)
        except ValueError as exc:
            raise LLMError(
                f"Ollama devolvió JSON que no valida contra {schema.__name__}: {raw[:200]}"
            ) from exc
