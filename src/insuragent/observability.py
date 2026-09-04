"""Trazado estructurado de los nodos del grafo (PRD §4.1).

El PRD exige poder responder *por qué* el Orquestador enrutó una consulta de
cierta forma. En vez de depender de LangSmith (que requiere cuenta y envía datos
fuera del equipo), se emite un log estructurado JSONL local: una línea por
evento, con `run_id` para correlacionar todos los nodos de un mismo turno.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from insuragent.config import get_settings
from insuragent.fs import restringir

_LOGGER = logging.getLogger("insuragent")

# Identificadores que nunca deben quedar en un archivo de log en claro. Las
# trazas se comparten al depurar y se copian a tickets de soporte; un RFC ahí es
# una fuga aunque el archivo jamás se versione.
_PATRONES_SENSIBLES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}\b"), "[RFC]"),
    (re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{2}[A-Z]{3}[A-Z0-9]\d\b"), "[CURP]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), "[LLAVE]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[TARJETA]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"), "[CORREO]"),
    (re.compile(r"\b\d{10}\b"), "[TELEFONO]"),
)

LONGITUD_MAXIMA_TEXTO = 300


def redactar(texto: str) -> str:
    """Enmascara identificadores regulados en un texto libre antes de registrarlo.

    Se aplica al mensaje del asegurado: es el único campo de la traza donde
    puede aparecer cualquier cosa, porque lo escribe una persona. El resto de
    campos son valores que produce el propio sistema.
    """
    saneado = texto
    for patron, sustituto in _PATRONES_SENSIBLES:
        saneado = patron.sub(sustituto, saneado)
    if len(saneado) > LONGITUD_MAXIMA_TEXTO:
        saneado = saneado[:LONGITUD_MAXIMA_TEXTO] + "…[truncado]"
    return saneado


_CURRENT_RUN: ContextVar[str | None] = ContextVar("insuragent_run_id", default=None)


@dataclass(slots=True)
class TraceEvent:
    """Un evento de ejecución de un nodo del grafo."""

    run_id: str
    node: str
    status: str
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "run_id": self.run_id,
                "node": self.node,
                "status": self.status,
                "duration_ms": round(self.duration_ms, 2),
                **self.payload,
            },
            ensure_ascii=False,
            default=str,
        )


class TraceWriter:
    """Append-only sobre un archivo JSONL. Nunca interrumpe el flujo del agente."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)
        restringir(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: TraceEvent) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(event.to_json() + "\n")
        except OSError:  # observabilidad degradada, nunca fatal
            _LOGGER.warning("No se pudo escribir la traza en %s", self._path, exc_info=True)

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


_writer: TraceWriter | None = None


def get_writer() -> TraceWriter:
    """Escritor de trazas para la ruta configurada actualmente.

    Se cachea, pero se recrea si la ruta cambia. Un global fijado en el primer
    uso seguiría escribiendo en el archivo de la configuración anterior, y las
    trazas de una sesión acabarían en el archivo de otra.
    """
    global _writer
    destino = get_settings().trace_file
    if _writer is None or _writer.path != destino:
        _writer = TraceWriter(destino)
    return _writer


def new_run_id() -> str:
    """Abre un identificador de turno y lo fija en el contexto actual."""
    run_id = uuid.uuid4().hex[:12]
    _CURRENT_RUN.set(run_id)
    return run_id


def current_run_id() -> str:
    return _CURRENT_RUN.get() or new_run_id()


@contextmanager
def trace_node(node: str, **payload: Any) -> Iterator[dict[str, Any]]:
    """Envuelve la ejecución de un nodo y registra duración y resultado.

    El diccionario cedido puede enriquecerse dentro del bloque; lo que contenga
    al salir se serializa en la traza.
    """
    run_id = current_run_id()
    extra: dict[str, Any] = dict(payload)
    started = time.perf_counter()
    status = "ok"
    try:
        yield extra
    except Exception as exc:
        status = "error"
        extra["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        event = TraceEvent(
            run_id=run_id, node=node, status=status, duration_ms=elapsed_ms, payload=extra
        )
        get_writer().write(event)
        _LOGGER.info("node=%s status=%s %.0fms", node, status, elapsed_ms)


def configure_logging(level: str | None = None) -> None:
    """Configura el logging raíz una sola vez, con formato legible."""
    settings = get_settings()
    logging.basicConfig(
        level=(level or settings.log_level).upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silencia el ruido de las librerías de terceros en modo INFO.
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
