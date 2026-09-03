"""Selección y degradación de proveedores de LLM (PRD §4.2, §8)."""

from __future__ import annotations

import pytest

from insuragent.llm import LLMError, get_provider
from insuragent.llm.base import PRICING_USD_PER_MTOK, LLMProvider, Usage
from insuragent.llm.stub_provider import StubProvider, isolate_user_message
from insuragent.schemas.fnol import IncidentDraft
from insuragent.schemas.routing import Route, RouteDecision


class _BrokenProvider(LLMProvider):
    """Proveedor que construye bien pero no está utilizable."""

    name = "roto"
    model = "roto"

    def healthcheck(self) -> None:
        raise LLMError("sin credenciales")

    def complete(self, *, system, messages, max_tokens=None):  # pragma: no cover
        raise AssertionError("no debería llamarse")

    def structured(self, *, system, messages, schema):  # pragma: no cover
        raise AssertionError("no debería llamarse")


def test_proveedor_stub_se_devuelve_tal_cual(settings):
    assert isinstance(get_provider(settings), StubProvider)


def test_proveedor_no_utilizable_degrada_al_stub(settings, monkeypatch, caplog):
    """El healthcheck es lo que hace posible la degradación ordenada.

    Sin él, el SDK de Anthropic construye el cliente sin validar credenciales y
    el fallo aparece hasta el primer turno de la conversación.
    """
    broken_settings = settings.model_copy(update={"llm_provider": "ollama"})
    monkeypatch.setattr(
        "insuragent.llm.ollama_provider.OllamaProvider",
        lambda _settings: _BrokenProvider(),
    )

    with caplog.at_level("WARNING"):
        provider = get_provider(broken_settings)

    assert isinstance(provider, StubProvider)
    assert any("no está disponible" in record.message for record in caplog.records)


def test_healthcheck_por_defecto_es_un_no_op():
    StubProvider().healthcheck()  # no debe lanzar


def test_calculo_de_costo_usa_la_tarifa_del_modelo():
    usage = Usage.priced("claude-opus-5", input_tokens=1_000_000, output_tokens=1_000_000)
    rate_in, rate_out = PRICING_USD_PER_MTOK["claude-opus-5"]
    assert usage.cost_usd == pytest.approx(rate_in + rate_out)


def test_modelo_sin_tarifa_no_inventa_un_costo():
    assert Usage.priced("modelo-desconocido", 1000, 1000).cost_usd == 0.0


def test_los_consumos_se_suman():
    total = Usage(10, 20, 0.5) + Usage(1, 2, 0.25)
    assert (total.input_tokens, total.output_tokens, total.cost_usd) == (11, 22, 0.75)


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("FECHA DE HOY: 2026-09-02\n\nMensaje del asegurado:\nChoqué ayer", "Choqué ayer"),
        ("contexto…\n\nPregunta del asegurado: ¿Qué cubre?", "¿Qué cubre?"),
        ("sin marcador", "sin marcador"),
    ],
)
def test_aislamiento_del_mensaje_del_asegurado(prompt, expected):
    """El stub no debe leer el andamiaje del prompt como si fuera del usuario."""
    assert isolate_user_message(prompt) == expected


def test_stub_clasifica_con_el_esquema_de_enrutamiento():
    decision, usage = StubProvider().structured(
        system="",
        messages=[{"role": "user", "content": "Pregunta del asegurado: quiero reportar un choque"}],
        schema=RouteDecision,
    )
    assert isinstance(decision, RouteDecision)
    assert decision.route is Route.FNOL
    assert usage.cost_usd == 0.0


def test_stub_extrae_con_el_esquema_de_siniestro():
    draft, _ = StubProvider().structured(
        system="",
        messages=[
            {"role": "user", "content": "Mensaje del asegurado: ayer se rompió el parabrisas"}
        ],
        schema=IncidentDraft,
    )
    assert isinstance(draft, IncidentDraft)
    assert draft.incident_type is not None


def test_la_evaluacion_aborta_temprano_si_el_proveedor_no_puede_generar(
    settings, repository, monkeypatch
):
    """Descubrir que la cuenta no tiene saldo a mitad de 34 casos es tiempo perdido.

    El healthcheck usa una petición gratuita y por eso no puede detectar un saldo
    agotado; la prueba previa de la evaluación sí, con una petición mínima.
    """
    from insuragent.evaluation import runner
    from insuragent.rag.index import ClauseIndex

    class _SinSaldo(StubProvider):
        name = "sin-saldo"

        def complete(self, *, system, messages, max_tokens=None):
            raise LLMError("La cuenta de Anthropic no tiene saldo suficiente.")

    monkeypatch.setattr(runner, "get_provider", lambda _s: _SinSaldo())
    monkeypatch.setattr(
        ClauseIndex,
        "load",
        classmethod(lambda cls, d=None, settings=None: cls.build(settings=settings)),
    )

    with pytest.raises(RuntimeError, match="no puede generar respuestas"):
        runner.run_evaluation(settings)


def test_los_reintentos_por_defecto_superan_los_del_sdk(settings):
    """Una corrida de evaluación son decenas de peticiones seguidas.

    Con los 2 reintentos que trae el SDK, un solo pico de carga (HTTP 529
    `overloaded`) tira la corrida completa — que fue exactamente lo que pasó al
    capturar las transcripciones la primera vez.
    """
    assert settings.max_retries >= 5


def test_el_529_se_traduce_a_un_mensaje_accionable():
    """Un `overloaded` es transitorio y el mensaje debe decirlo."""
    import anthropic

    from insuragent.llm.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._errors = anthropic
    provider.model = "claude-opus-5"

    class _Respuesta:
        status_code = 529
        headers: dict[str, str] = {}
        request = None

    error = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    error.status_code = 529
    error.response = _Respuesta()

    traducido = provider._translate(error)
    assert "sobrecargada" in str(traducido)
    assert "transitorio" in str(traducido)
