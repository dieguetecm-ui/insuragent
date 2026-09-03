"""Trazado estructurado de los nodos (PRD §4.1)."""

from __future__ import annotations

import pytest

from insuragent import observability
from insuragent.observability import TraceWriter, new_run_id, trace_node


@pytest.fixture(autouse=True)
def _isolated_writer(settings, monkeypatch):
    monkeypatch.setattr(observability, "_writer", TraceWriter(settings.trace_file))
    return settings.trace_file


def test_traza_registra_nodo_y_duracion(settings):
    new_run_id()
    with trace_node("nodo_prueba", campo="valor") as span:
        span["extra"] = 42

    events = TraceWriter(settings.trace_file).read_all()
    assert len(events) == 1
    assert events[0]["node"] == "nodo_prueba"
    assert events[0]["status"] == "ok"
    assert events[0]["extra"] == 42
    assert events[0]["duration_ms"] >= 0


def test_traza_registra_el_error_y_lo_relanza(settings):
    with pytest.raises(ValueError), trace_node("nodo_falla"):
        raise ValueError("boom")

    event = TraceWriter(settings.trace_file).read_all()[0]
    assert event["status"] == "error"
    assert "boom" in event["error"]


def test_run_id_correlaciona_nodos_del_mismo_turno(settings):
    run_id = new_run_id()
    with trace_node("a"):
        pass
    with trace_node("b"):
        pass
    events = TraceWriter(settings.trace_file).read_all()
    assert {e["run_id"] for e in events} == {run_id}


def test_la_traza_nunca_interrumpe_el_flujo(monkeypatch, settings):
    """Si el disco falla, se degrada la observabilidad, no la conversación."""
    writer = TraceWriter(settings.trace_file)
    monkeypatch.setattr(
        writer, "_path", settings.trace_file / "ruta" / "imposible.jsonl", raising=False
    )
    monkeypatch.setattr(observability, "_writer", writer)
    with trace_node("nodo"):
        pass  # no debe lanzar
