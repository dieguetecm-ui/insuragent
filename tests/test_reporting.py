"""Generación del reporte técnico en PDF (PRD §2, entregable 2)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from insuragent.reporting.builder import ReportData, build_pdf, load_report_data, render_html
from insuragent.reporting.diagram import arquitectura_svg


@pytest.fixture
def evaluacion() -> dict:
    """Reporte de evaluación mínimo pero con la forma real."""
    return {
        "provider": "anthropic",
        "configured_provider": "anthropic",
        "degraded": False,
        "model": "claude-opus-5",
        "embedder": "sentence-transformers",
        "started_at": "2026-09-02T12:00:00+00:00",
        "metrics": {
            "rag_precision": 0.93,
            "deductible_precision": 1.0,
            "routing_accuracy": 0.9375,
            "fnol_end_to_end": 1.0,
            "avg_latency_ms": 1840.0,
            "p95_latency_ms": 3200.0,
            "session_cost_usd": 0.0184,
            "total_input_tokens": 12345,
            "total_output_tokens": 2345,
        },
        "blocks": {
            "precisión_rag": {
                "passed": 14,
                "total": 15,
                "accuracy": 0.93,
                "cases": [
                    {
                        "case_id": "rag-01",
                        "passed": True,
                        "expected": "RC-1.1",
                        "observed": "RC-1.1",
                    },
                    {
                        "case_id": "rag-02",
                        "passed": False,
                        "expected": "AMP-1.1",
                        "observed": "BAS-1.1",
                    },
                ],
            },
            "precisión_deducible": {
                "passed": 15,
                "total": 15,
                "accuracy": 1.0,
                "cases": [
                    {"case_id": "rag-01", "passed": True, "expected": "None", "observed": "None"},
                    {"case_id": "rag-02", "passed": True, "expected": "None", "observed": "None"},
                ],
            },
            "precisión_enrutamiento": {
                "passed": 15,
                "total": 16,
                "accuracy": 0.9375,
                "cases": [
                    {
                        "case_id": "rt-01",
                        "passed": True,
                        "expected": "policy",
                        "observed": "policy",
                    },
                    {"case_id": "rt-02", "passed": False, "expected": "policy", "observed": "fnol"},
                ],
            },
            "fnol_end_to_end": {"passed": 3, "total": 3, "accuracy": 1.0, "cases": []},
        },
    }


def test_el_svg_de_arquitectura_es_xml_valido():
    """Un SVG mal formado no falla al generar el PDF: sale una página en blanco."""
    raiz = ET.fromstring(arquitectura_svg())
    assert raiz.tag.endswith("svg")
    assert raiz.get("viewBox")


def test_carga_sin_evaluacion_no_revienta(settings):
    data = load_report_data(settings)
    assert not data.hay_metricas
    assert data.proveedor == "—"


def test_html_sin_metricas_lo_dice_explicitamente(settings):
    html = render_html(settings)
    assert "make eval" in html
    assert "<!DOCTYPE html>" in html


def test_html_incluye_las_metricas_de_la_corrida(evaluacion):
    data = ReportData(evaluacion=evaluacion, generado=date(2026, 9, 2))
    html = render_html(data=data)
    assert "93%" in html  # precisión RAG
    assert "claude-opus-5" in html
    assert "$0.01840" in html
    assert "2 de septiembre de 2026" in html  # fecha en español, sin depender del locale


def test_html_marca_la_corrida_degradada(evaluacion):
    """Nunca debe poder confundirse una corrida con el stub con una medición real."""
    degradada = {**evaluacion, "provider": "stub", "degraded": True}
    html = render_html(data=ReportData(evaluacion=degradada, generado=date.today()))
    assert "no representan al modelo" in html
    assert "callout alerta" in html


def test_html_avisa_cuando_el_stub_fue_lo_configurado(evaluacion):
    """Configurar el stub a propósito no es una degradación, pero sigue sin medir al modelo."""
    con_stub = {**evaluacion, "provider": "stub", "configured_provider": "stub", "degraded": False}
    html = render_html(data=ReportData(evaluacion=con_stub, generado=date.today()))
    assert "Línea base" in html


def test_los_casos_fallidos_se_marcan_en_las_tablas(evaluacion):
    html = render_html(data=ReportData(evaluacion=evaluacion, generado=date.today()))
    assert 'class="fallo"' in html  # rag-02 y rt-02 fallan en el fixture
    assert 'class="ok"' in html


def test_genera_un_pdf_valido(tmp_path: Path, settings, evaluacion):
    (settings.data_dir / "evaluation_report.json").write_text(
        json.dumps(evaluacion), encoding="utf-8"
    )
    destino = tmp_path / "reporte.pdf"
    escrito = build_pdf(destino, settings)

    assert escrito == destino
    contenido = destino.read_bytes()
    assert contenido.startswith(b"%PDF-")
    assert contenido.rstrip().endswith(b"%%EOF")
    assert len(contenido) > 50_000  # con la portada y el diagrama vectorial
