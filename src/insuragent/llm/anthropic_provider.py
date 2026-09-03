"""Proveedor principal: Claude API (PRD §4.2).

Notas de la API que condicionan este código:

* Los modelos Opus 5 / Sonnet 5 **rechazan** parámetros de sampling
  (`temperature`, `top_p`, `top_k`) con HTTP 400. El determinismo se consigue
  con *structured outputs*, no bajando la temperatura.
* El presupuesto de razonamiento se controla con ``output_config.effort``;
  ``budget_tokens`` fue removido y devuelve 400.
* ``messages.parse`` valida la respuesta contra un modelo Pydantic y expone
  ``parsed_output`` ya tipado.
"""

from __future__ import annotations

import logging
from typing import Any

from insuragent.config import Settings, get_settings
from insuragent.llm.base import LLMError, LLMProvider, LLMResponse, Message, T, Usage

_LOGGER = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Cliente sobre el SDK oficial `anthropic`."""

    name = "anthropic"

    def __init__(self, settings: Settings | None = None) -> None:
        import anthropic  # import diferido: el stub no debe requerir el SDK

        self._settings = settings or get_settings()
        self.model = self._settings.anthropic_model
        self._errors = anthropic
        # Sin api_key explícito el SDK resuelve ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN
        # o un perfil de `ant auth login`; sólo lo inyectamos si vino del `.env`.
        kwargs: dict[str, Any] = {}
        if self._settings.anthropic_api_key:
            kwargs["api_key"] = self._settings.anthropic_api_key
        # Las API keys ligadas a una identidad exigen declarar el workspace en
        # el que actúa la petición; sin la cabecera la API responde 400.
        if self._settings.anthropic_workspace_id:
            kwargs["default_headers"] = {
                "anthropic-workspace-id": self._settings.anthropic_workspace_id
            }
        self._client = anthropic.Anthropic(max_retries=self._settings.max_retries, **kwargs)

    # -- helpers ------------------------------------------------------------

    def _usage(self, response: Any) -> Usage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return Usage()
        return Usage.priced(
            self.model,
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )

    def _translate(self, exc: Exception) -> LLMError:
        """Convierte los errores del SDK en un mensaje accionable."""
        a = self._errors
        # El SDK lanza un TypeError plano cuando no encuentra ninguna credencial
        # (ni api_key, ni auth_token, ni un perfil de `ant auth login`).
        if isinstance(exc, TypeError) and "authentication method" in str(exc):
            return LLMError(
                "No hay credenciales de Anthropic resolubles. Exporta ANTHROPIC_API_KEY, "
                "colócala en el archivo .env, o inicia sesión con `ant auth login`."
            )
        if isinstance(exc, a.AuthenticationError):
            return LLMError("Credenciales de Anthropic inválidas o ausentes (ANTHROPIC_API_KEY).")
        if isinstance(exc, a.RateLimitError):
            retry = exc.response.headers.get("retry-after", "60")
            return LLMError(f"Límite de tasa alcanzado; reintentar en {retry}s.")
        if isinstance(exc, a.NotFoundError):
            return LLMError(f"Modelo desconocido para esta cuenta: {self.model}.")
        if isinstance(exc, a.BadRequestError):
            if "credit balance" in str(exc):
                return LLMError(
                    "La cuenta de Anthropic no tiene saldo suficiente. Agrega créditos en "
                    "console.anthropic.com → Plans & Billing. Mientras tanto puedes evaluar con "
                    "INSURAGENT_LLM_PROVIDER=stub (línea base determinista) o =ollama (modelo local)."
                )
            if "workspace-id" in str(exc):
                return LLMError(
                    "La API key está ligada a una identidad y requiere declarar el workspace. "
                    "Añade ANTHROPIC_WORKSPACE_ID=wrkspc_... a tu archivo .env "
                    "(lo encuentras en la consola de Anthropic, en Settings → Workspaces)."
                )
            return LLMError(f"Solicitud inválida a la API: {exc}")
        if isinstance(exc, a.APIStatusError):
            if exc.status_code == 529:
                return LLMError(
                    "La API de Anthropic está sobrecargada (529) y los reintentos se agotaron. "
                    "Es transitorio: vuelve a intentarlo en unos minutos o sube "
                    "INSURAGENT_MAX_RETRIES."
                )
            return LLMError(f"Error {exc.status_code} de la API de Anthropic: {exc}")
        if isinstance(exc, a.APIConnectionError):
            return LLMError("No se pudo conectar con la API de Anthropic; revisa la red.")
        return LLMError(f"Fallo inesperado del proveedor: {exc}")

    # -- interfaz -----------------------------------------------------------

    def healthcheck(self) -> None:
        """Valida credenciales con `GET /v1/models`.

        Es una petición sin tokens y por tanto sin costo, a diferencia de mandar
        un mensaje de prueba. Confirma que hay credenciales resolubles, que el
        workspace es correcto y que el modelo existe para esta cuenta.

        Lo que **no** puede confirmar es que la cuenta tenga saldo: eso sólo se
        sabe al intentar generar. Deliberadamente no se gasta dinero para
        averiguar si se puede gastar dinero; la evaluación hace esa comprobación
        aparte, con una petición mínima, antes de lanzar el set completo.
        """
        try:
            self._client.models.list(limit=1)
        except Exception as exc:  # noqa: BLE001
            raise self._translate(exc) from exc

    def complete(
        self, *, system: str, messages: list[Message], max_tokens: int | None = None
    ) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self._settings.max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": self._settings.effort},
            )
        except Exception as exc:  # noqa: BLE001 — se traduce y se relanza tipado
            raise self._translate(exc) from exc

        if response.stop_reason == "refusal":
            raise LLMError("El modelo declinó responder por políticas de seguridad.")

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(text=text.strip(), usage=self._usage(response))

    def structured(
        self, *, system: str, messages: list[Message], schema: type[T]
    ) -> tuple[T, Usage]:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=self._settings.max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_format=schema,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._translate(exc) from exc

        parsed = response.parsed_output
        if parsed is None:
            raise LLMError(f"El modelo no devolvió una salida válida para {schema.__name__}.")
        return parsed, self._usage(response)
