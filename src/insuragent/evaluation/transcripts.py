"""Captura de conversaciones de ejemplo con su traza completa.

Las tablas de métricas dicen *cuánto* acierta el sistema, pero no dejan ver
*cómo* llega a una respuesta. Estas transcripciones ejecutan conversaciones
reales contra la aplicación y registran, turno a turno, la decisión de
enrutamiento con su justificación, las cláusulas recuperadas con su score, el
deducible calculado y la respuesta final.

Cada guion apunta a los casos del set dorado que ejercita, para que en el
reporte se pueda ir de una fila de la tabla a la conversación que la produjo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from insuragent.config import Settings, get_settings
from insuragent.db.repository import Repository
from insuragent.graph.state import Stage
from insuragent.schemas.auth import Customer
from insuragent.schemas.policy import CoverageType
from insuragent.session import InsurAgentSession

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TurnTrace:
    """Todo lo observable de un turno, listo para pintar en el reporte."""

    numero: int
    usuario: str
    ruta: str
    confianza: float
    razonamiento: str
    respuesta: str
    etapa: str
    latencia_ms: float
    citas: list[str] = field(default_factory=list)
    recuperacion: list[dict] = field(default_factory=list)
    talleres: list[str] = field(default_factory=list)
    deducible_mxn: float | None = None
    historial_usado: int = 0
    folio: str | None = None
    nota: str = ""


@dataclass(slots=True)
class Transcript:
    """Una conversación completa con su contexto."""

    transcript_id: str
    titulo: str
    proposito: str
    asegurado: dict
    casos_dorados: list[str]
    turnos: list[TurnTrace] = field(default_factory=list)
    evidencia: str | None = None


@dataclass(slots=True)
class Guion:
    """Definición de una conversación a capturar."""

    transcript_id: str
    titulo: str
    proposito: str
    paquete: CoverageType
    mensajes: tuple[str, ...]
    casos_dorados: tuple[str, ...]
    requiere_historial: bool = False
    adjunta_evidencia: bool = False


# ---------------------------------------------------------------------------
# Guiones
# ---------------------------------------------------------------------------

GUIONES: tuple[Guion, ...] = (
    Guion(
        transcript_id="conv-01",
        titulo="Siniestro recurrente: memoria de largo plazo y flujo FNOL completo",
        proposito=(
            "Recorre el user journey del PRD §6 de principio a fin sobre un asegurado que ya tiene "
            "un siniestro de cristales en su historial. Muestra las tres cosas juntas: que el "
            "asistente recuerda conversaciones anteriores, que el enrutamiento cambia de agente "
            "entre turnos, y que el expediente sólo se crea cuando el asegurado lo confirma."
        ),
        paquete=CoverageType.AMPLIA,
        mensajes=(
            "Otra vez se me estrelló el parabrisas. ¿Cuánto tendría que pagar de deducible?",
            "Sí, quiero reportarlo",
            "Fue ayer en Avenida Insurgentes, colonia Del Valle. Una grava que levantó un camión "
            "de carga rompió el parabrisas mientras iba circulando.",
        ),
        casos_dorados=("rag-07", "rt-02"),
        requiere_historial=True,
        adjunta_evidencia=True,
    ),
    Guion(
        transcript_id="conv-02",
        titulo="Discriminación entre paquetes: la misma pregunta, otra respuesta",
        proposito=(
            "El mismo tema —rotura de cristales— consultado por un asegurado con paquete Básica. "
            "El recuperador debe traer la cláusula de exclusión de Básica y no la de cobertura de "
            "Amplia, que es el caso duro del corpus traslapado descrito en el PRD §4.2."
        ),
        paquete=CoverageType.BASICA,
        mensajes=("Se me rompió el cristal del coche, ¿mi póliza lo cubre?",),
        casos_dorados=("rag-08", "rt-02"),
    ),
    Guion(
        transcript_id="conv-03",
        titulo="Enrutamiento a la red de talleres",
        proposito=(
            "Consulta que menciona un siniestro pero pregunta por un taller. El orquestador debe "
            "mandarla al Agente de Red y no al de FNOL: es la variante adversarial rt-15 del set "
            "dorado."
        ),
        paquete=CoverageType.AMPLIA,
        mensajes=("¿Puedo llevar mi auto chocado a un taller cerca de Polanco?",),
        casos_dorados=("rt-04", "rt-15"),
    ),
)


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------


def _png_minimo() -> bytes:
    """PNG 1×1 válido para ejercitar la carga de evidencia."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
        "0000000049454e44ae426082"
    )


def _elegir_asegurado(
    repository: Repository, paquete: CoverageType, con_historial: bool
) -> Customer:
    """Primer asegurado del paquete pedido, con o sin siniestros previos."""
    candidatos = [c for c in repository.list_customers() if c.coverage_type == paquete.value]
    if not candidatos:
        raise RuntimeError(
            f"No hay asegurados con paquete '{paquete.value}'. Corre `make seed` primero."
        )
    if con_historial:
        con_previos = [c for c in candidatos if repository.list_claims(c.customer_id)]
        if not con_previos:
            raise RuntimeError(
                f"Ningún asegurado con paquete '{paquete.value}' tiene siniestros previos. "
                "El seed debe generar historial para poder demostrar la memoria de largo plazo."
            )
        return con_previos[0]
    return candidatos[0]


def capturar(guion: Guion, session: InsurAgentSession) -> Transcript:
    """Ejecuta un guion contra la aplicación real y registra cada turno."""
    customer = _elegir_asegurado(session.repository, guion.paquete, guion.requiere_historial)
    session.customer = customer
    session.reset_conversation()

    previos = session.past_claims()
    transcript = Transcript(
        transcript_id=guion.transcript_id,
        titulo=guion.titulo,
        proposito=guion.proposito,
        casos_dorados=list(guion.casos_dorados),
        asegurado={
            "nombre": customer.full_name,
            "poliza": customer.policy_number,
            "paquete": customer.coverage_type,
            "vehiculo": f"{customer.vehicle.brand} {customer.vehicle.model} {customer.vehicle.year}",
            "ciudad": customer.city,
            "siniestros_previos": [
                {
                    "folio": c["claim_id"],
                    "tipo": c["incident_type"],
                    "fecha": c["incident_date"],
                    "lugar": c["location"],
                }
                for c in previos
            ],
        },
    )

    for numero, mensaje in enumerate(guion.mensajes, start=1):
        turno = session.send(mensaje)
        transcript.turnos.append(
            TurnTrace(
                numero=numero,
                usuario=mensaje,
                ruta=turno.route,
                confianza=turno.route_confidence,
                razonamiento=turno.route_reasoning,
                respuesta=turno.answer,
                etapa=turno.stage,
                latencia_ms=round(turno.latency_ms, 1),
                citas=turno.citations,
                recuperacion=turno.retrieval,
                talleres=turno.workshop_ids,
                deducible_mxn=turno.deductible_mxn,
                historial_usado=turno.history_used,
                folio=turno.claim_id,
            )
        )

    etapa = (session.state or {}).get("stage")
    if guion.adjunta_evidencia and etapa == Stage.AWAITING_EVIDENCE.value:
        claim = session.attach_evidence("dano_parabrisas.png", _png_minimo(), "image/png")
        transcript.evidencia = claim.claim_id
        transcript.turnos.append(
            TurnTrace(
                numero=len(guion.mensajes) + 1,
                usuario="[adjunta fotografía del daño: dano_parabrisas.png]",
                ruta="fnol",
                confianza=1.0,
                razonamiento="Carga de evidencia fuera del grafo: la valida y persiste la sesión.",
                respuesta=(
                    f"Reporte registrado con folio {claim.claim_id}. "
                    f"Evidencia guardada en {claim.evidence[0].stored_path.name}."
                ),
                etapa=Stage.DONE.value,
                latencia_ms=0.0,
                deducible_mxn=claim.deductible_quoted_mxn,
                folio=claim.claim_id,
                nota="La evidencia se valida (tipo MIME y tamaño) antes de tocar el disco.",
            )
        )

    return transcript


def _base_limpia(settings: Settings) -> Settings:
    """Configuración apuntando a una base recién sembrada, sólo para los guiones.

    Las transcripciones ilustran el reporte, así que tienen que ser
    reproducibles. Si compartieran base con la evaluación, el historial de un
    asegurado incluiría los expedientes que la propia corrida acaba de crear —y
    el ejemplo de memoria de largo plazo mostraría siniestros que el lector no
    puede rastrear a ningún lado.
    """
    from insuragent.data.synthetic import generate_claim_history, generate_customers

    aislada = settings.model_copy(update={"db_path": settings.data_dir / "transcripts.db"})
    repository = Repository(aislada.db_path)
    repository.reset()

    customers = generate_customers(aislada.synthetic_customers, aislada.synthetic_seed)
    for customer in customers:
        repository.upsert_customer(customer)
    for claim in generate_claim_history(customers, aislada.synthetic_seed):
        repository.save_claim(claim)
    return aislada


def capture_transcripts(
    settings: Settings | None = None, output: Path | None = None
) -> list[Transcript]:
    """Captura todos los guiones y los guarda en JSON para el reporte."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    session = InsurAgentSession.create(_base_limpia(settings))

    transcripts = []
    for guion in GUIONES:
        _LOGGER.info("Capturando %s: %s", guion.transcript_id, guion.titulo)
        transcripts.append(capturar(guion, session))

    output = output or (settings.data_dir / "transcripts.json")
    output.write_text(
        json.dumps(
            {
                "proveedor": session.provider.name,
                "modelo": session.provider.model,
                "conversaciones": [asdict(t) for t in transcripts],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    _LOGGER.info("Transcripciones escritas en %s", output)
    return transcripts
