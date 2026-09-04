"""Construcción del reporte técnico en PDF.

El contenido narrativo vive en `content.py`; aquí queda sólo el ensamblado:
cargar el reporte de evaluación, componer el HTML y renderizarlo con WeasyPrint.
Separarlos permite probar el HTML sin pagar el costo de renderizar un PDF.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from insuragent.config import Settings, get_settings
from insuragent.reporting.styles import STYLESHEET

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ReportData:
    """Datos de la corrida de evaluación que alimentan el reporte.

    `evaluacion` es `None` cuando aún no se ha corrido `make eval`; el reporte
    se genera igual, señalando explícitamente qué secciones quedan sin medir en
    lugar de omitirlas en silencio.
    """

    evaluacion: dict[str, Any] | None
    generado: date
    transcripciones: dict[str, Any] | None = None
    auditoria: dict[str, Any] | None = None

    @property
    def hay_metricas(self) -> bool:
        return self.evaluacion is not None

    @property
    def conversaciones(self) -> list[dict[str, Any]]:
        return (self.transcripciones or {}).get("conversaciones", [])

    @property
    def metricas(self) -> dict[str, Any]:
        return self.evaluacion["metrics"] if self.evaluacion else {}

    @property
    def bloques(self) -> dict[str, Any]:
        return self.evaluacion["blocks"] if self.evaluacion else {}

    @property
    def degradada(self) -> bool:
        return bool(self.evaluacion and self.evaluacion.get("degraded"))

    @property
    def proveedor(self) -> str:
        return self.evaluacion["provider"] if self.evaluacion else "—"

    @property
    def proveedor_configurado(self) -> str:
        return self.evaluacion.get("configured_provider", "—") if self.evaluacion else "—"

    @property
    def modelo(self) -> str:
        return self.evaluacion["model"] if self.evaluacion else "—"

    @property
    def embedder(self) -> str:
        return self.evaluacion["embedder"] if self.evaluacion else "—"


def load_report_data(settings: Settings | None = None) -> ReportData:
    """Lee `data/evaluation_report.json` si existe."""
    settings = settings or get_settings()
    path = settings.data_dir / "evaluation_report.json"
    evaluacion = None
    if path.exists():
        evaluacion = json.loads(path.read_text(encoding="utf-8"))
    else:
        _LOGGER.warning(
            "No hay reporte de evaluación en %s; el PDF saldrá sin métricas. Corre `make eval`.",
            path,
        )
    transcripciones = None
    ruta_transcripciones = settings.data_dir / "transcripts.json"
    if ruta_transcripciones.exists():
        transcripciones = json.loads(ruta_transcripciones.read_text(encoding="utf-8"))
    else:
        _LOGGER.warning(
            "No hay transcripciones en %s; el reporte saldrá sin conversaciones de ejemplo.",
            ruta_transcripciones,
        )

    auditoria = None
    ruta_auditoria = settings.data_dir / "redteam_report.json"
    if ruta_auditoria.exists():
        auditoria = json.loads(ruta_auditoria.read_text(encoding="utf-8"))
    else:
        _LOGGER.info(
            "No hay reporte de auditoría en %s; el capítulo de seguridad saldrá sin sondas.",
            ruta_auditoria,
        )

    return ReportData(
        evaluacion=evaluacion,
        generado=date.today(),
        transcripciones=transcripciones,
        auditoria=auditoria,
    )


def render_html(settings: Settings | None = None, data: ReportData | None = None) -> str:
    """Genera el documento HTML completo, con los estilos embebidos."""
    from insuragent.reporting.content import documento

    data = data or load_report_data(settings)
    cuerpo = documento(data)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es"><head><meta charset="utf-8">'
        "<title>InsurAgent — Reporte Técnico de la PoC</title>"
        # WeasyPrint traslada estas etiquetas a los metadatos del PDF, de modo
        # que la autoría viaja con el archivo aunque se renombre.
        '<meta name="author" content="Diego Carrillo Mondragón">'
        '<meta name="description" content="Reporte técnico de la PoC InsurAgent — '
        'asistente agéntico para el ramo de seguros de automóviles.">'
        '<meta name="keywords" content="InsurAgent, seguros, agentes, RAG, LangGraph, FNOL">'
        f"<style>{STYLESHEET}</style>"
        f"</head><body>{cuerpo}</body></html>"
    )


def build_pdf(output: Path | None = None, settings: Settings | None = None) -> Path:
    """Renderiza el reporte a PDF y devuelve la ruta escrita."""
    from weasyprint import HTML

    settings = settings or get_settings()
    output = output or (Path(__file__).resolve().parents[3] / "docs" / "report.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    html = render_html(settings)
    HTML(string=html).write_pdf(str(output))
    _LOGGER.info("Reporte PDF escrito en %s", output)
    return output
