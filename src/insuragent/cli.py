"""Puntos de entrada de línea de comandos.

Expuestos como `insuragent-seed`, `insuragent-index` e `insuragent-eval` al
instalar el paquete, y también invocables vía los wrappers de `scripts/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from insuragent.config import get_settings
from insuragent.data.corpus import CLAUSES, render_markdown
from insuragent.data.synthetic import generate_claim_history, generate_customers
from insuragent.db.repository import Repository
from insuragent.evaluation.runner import run_evaluation
from insuragent.observability import configure_logging
from insuragent.rag.index import ClauseIndex
from insuragent.schemas.policy import CoverageType

PROJECT_DOCS = Path(__file__).resolve().parents[2] / "docs"


def seed(argv: list[str] | None = None) -> int:
    """Genera datos sintéticos, escribe el corpus y puebla SQLite (Fase 1)."""
    parser = argparse.ArgumentParser(description="Puebla la base con datos sintéticos.")
    parser.add_argument(
        "--customers", type=int, default=None, help="Número de asegurados a generar"
    )
    parser.add_argument("--reset", action="store_true", help="Borra la base antes de poblarla")
    args = parser.parse_args(argv)

    configure_logging()
    settings = get_settings()
    settings.ensure_dirs()

    # Corpus legible en disco: versionable y revisable por un humano.
    for coverage_type in CoverageType:
        target = settings.corpus_dir / f"condiciones_generales_{coverage_type.value}.md"
        target.write_text(render_markdown(coverage_type), encoding="utf-8")
    print(
        f"✓ Corpus escrito en {settings.corpus_dir} ({len(CLAUSES)} cláusulas, {len(CoverageType)} variantes)"
    )

    repository = Repository(settings.db_path)
    if args.reset:
        repository.reset()
    else:
        repository.initialize()

    count = args.customers or settings.synthetic_customers
    customers = generate_customers(count, settings.synthetic_seed)
    for customer in customers:
        repository.upsert_customer(customer)

    # Historial previo: sin él, la memoria de largo plazo del PRD §3.2 no se
    # puede demostrar porque no hay nada que recordar.
    historial = generate_claim_history(customers, settings.synthetic_seed)
    for claim in historial:
        repository.save_claim(claim)

    con_historial = len({c.customer_id for c in historial})
    print(f"✓ {len(customers)} asegurados sintéticos en {settings.db_path}")
    print(
        f"✓ {len(historial)} siniestros previos para {con_historial} de ellos (memoria de largo plazo)"
    )
    print(
        "\n  Credenciales de prueba (los identificadores llevan prefijo XXX/XXXX: son sintéticos):\n"
    )
    for customer in customers[:3]:
        print(f"    {customer.full_name}  [paquete {customer.coverage_type}]")
        print(f"      Póliza : {customer.policy_number}")
        print(f"      RFC    : {customer.rfc}")
        print(f"      CURP   : {customer.curp}")
        print(f"      Cel.   : ...{customer.phone_last3}\n")
    return 0


def index(argv: list[str] | None = None) -> int:
    """Vectoriza las condiciones generales en FAISS (Fase 2)."""
    parser = argparse.ArgumentParser(description="Construye el índice FAISS.")
    parser.parse_args(argv)

    configure_logging()
    settings = get_settings()
    settings.ensure_dirs()

    clause_index = ClauseIndex.build(settings=settings)
    clause_index.save(settings.index_dir)
    print(
        f"✓ Índice FAISS con {clause_index.size} cláusulas "
        f"(embedder: {clause_index.embedder_name}) en {settings.index_dir}"
    )
    return 0


def evaluate(argv: list[str] | None = None) -> int:
    """Corre el set dorado y reporta las métricas del PRD §5 (Fase 5)."""
    parser = argparse.ArgumentParser(description="Evalúa la PoC contra el set dorado.")
    parser.add_argument("--json", dest="json_path", default=None, help="Ruta del reporte JSON")
    parser.add_argument(
        "--no-transcripts",
        action="store_true",
        help="Omite la captura de conversaciones de ejemplo para el reporte",
    )
    args = parser.parse_args(argv)

    configure_logging()
    settings = get_settings()
    from pathlib import Path

    try:
        report = run_evaluation(settings, Path(args.json_path) if args.json_path else None)
    except RuntimeError as exc:
        # Un fallo de configuración o de cuenta no es un error del programa: se
        # comunica con una instrucción de qué hacer, no con una traza.
        print(f"\n✗ No se pudo completar la evaluación.\n  {exc}\n")
        return 1

    print(report.render_text())

    if not args.no_transcripts:
        from insuragent.evaluation.transcripts import capture_transcripts

        try:
            transcripts = capture_transcripts(settings)
            turnos = sum(len(t.turnos) for t in transcripts)
            print(f"✓ {len(transcripts)} conversaciones de ejemplo capturadas ({turnos} turnos)")
        except (RuntimeError, OSError) as exc:
            # Las transcripciones ilustran el reporte; su ausencia no invalida
            # las métricas, así que se avisa y se continúa.
            print(f"  ⚠ No se pudieron capturar las conversaciones de ejemplo: {exc}")

    return 0


def audit(argv: list[str] | None = None) -> int:
    """Lanza las sondas adversariales contra la aplicación (auditoría de fugas)."""
    parser = argparse.ArgumentParser(description="Audita la app con sondas adversariales.")
    parser.add_argument("--json", dest="json_path", default=None, help="Ruta del reporte JSON")
    args = parser.parse_args(argv)

    configure_logging()
    from insuragent.evaluation.redteam import ejecutar

    settings = get_settings()
    try:
        resultados = ejecutar(settings, Path(args.json_path) if args.json_path else None)
    except RuntimeError as exc:
        print(f"\n✗ No se pudo auditar.\n  {exc}\n")
        return 1

    seguras = sum(r.seguro for r in resultados)
    print("=" * 62)
    print(f"  Auditoría adversarial: {seguras}/{len(resultados)} sondas contenidas")
    print("=" * 62)
    for r in resultados:
        print(f"  [{'OK  ' if r.seguro else 'FUGA'}] {r.sonda_id} · {r.categoria}")
        for hallazgo in r.hallazgos:
            print(f"          → {hallazgo}")
    print("=" * 62)
    # Una fuga es un fallo: el comando debe poder usarse como puerta en CI.
    return 0 if seguras == len(resultados) else 1


def report(argv: list[str] | None = None) -> int:
    """Genera el reporte técnico en PDF (entregable 2 del PRD §2)."""
    parser = argparse.ArgumentParser(description="Genera el reporte técnico en PDF.")
    parser.add_argument("--output", default=None, help="Ruta del PDF de salida")
    parser.add_argument(
        "--html",
        action="store_true",
        help="Escribe también el HTML intermedio, útil para depurar estilos",
    )
    args = parser.parse_args(argv)

    configure_logging()
    from pathlib import Path

    from insuragent.reporting import build_pdf, render_html

    settings = get_settings()
    output = Path(args.output) if args.output else None

    if args.html:
        html_path = (output or (PROJECT_DOCS / "report.pdf")).with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(settings), encoding="utf-8")
        print(f"✓ HTML intermedio en {html_path}")

    written = build_pdf(output, settings)
    size_kb = written.stat().st_size / 1024
    print(f"✓ Reporte PDF generado: {written} ({size_kb:.0f} KB)")

    report_json = settings.data_dir / "evaluation_report.json"
    if not report_json.exists():
        print("  ⚠ Sin métricas: ejecuta `make eval` y vuelve a generar el reporte.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(seed())
