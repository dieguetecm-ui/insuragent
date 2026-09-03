"""Set de preguntas doradas (PRD §5, Fase 2).

Tres familias de casos, cada una atada a una métrica del PRD:

* `RAG_CASES` — precisión de recuperación: ¿el agente cita la cláusula correcta
  y cotiza el deducible correcto?
* `ROUTING_CASES` — precisión de enrutamiento: la tabla del PRD §3.1 más
  variantes adversariales (menciones de siniestro que **no** deben ir a FNOL,
  preguntas de taller que mencionan un choque, etc.).
* `FNOL_SCENARIOS` — tasa de éxito end-to-end del flujo de reporte.

Los casos de RAG están diseñados alrededor del traslape del corpus: las mismas
preguntas contra paquetes distintos deben producir cláusulas y montos distintos.
Ahí es donde un recuperador flojo se rompe.
"""

from __future__ import annotations

from dataclasses import dataclass

from insuragent.schemas.policy import CoverageType
from insuragent.schemas.routing import Route


@dataclass(frozen=True, slots=True)
class RagCase:
    """Pregunta dorada sobre las condiciones generales."""

    case_id: str
    question: str
    coverage_type: CoverageType
    expected_clauses: tuple[str, ...]
    """Cláusulas aceptables; basta con que el agente cite una de ellas."""
    expected_deductible_mxn: float | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class RoutingCase:
    """Consulta de prueba con la ruta que debe elegir el orquestador."""

    case_id: str
    question: str
    expected_route: Route
    note: str = ""


@dataclass(frozen=True, slots=True)
class FNOLScenario:
    """Guion completo de reporte de siniestro."""

    scenario_id: str
    coverage_type: CoverageType
    turns: tuple[str, ...]
    expect_claim: bool = True
    note: str = ""
    evidence: bool = True


# ---------------------------------------------------------------------------
# Precisión de recuperación RAG — 15 casos
# ---------------------------------------------------------------------------

RAG_CASES: tuple[RagCase, ...] = (
    RagCase(
        "rag-01",
        "¿Qué cubre mi póliza de responsabilidad civil?",
        CoverageType.RC,
        ("RC-1.1",),
        None,
        "RC debe citar su propia cláusula, no la de Amplia.",
    ),
    RagCase(
        "rag-02",
        "¿Cuál es el límite de responsabilidad civil de mi póliza?",
        CoverageType.AMPLIA,
        ("AMP-1.1",),
        None,
        "Mismo texto en tres paquetes; debe elegir el del asegurado.",
    ),
    RagCase(
        "rag-03",
        "¿Cuánto me cubre la responsabilidad civil por daños a terceros?",
        CoverageType.BASICA,
        ("BAS-1.1",),
        None,
        "Límite de 3 MDP, distinto de RC y Amplia.",
    ),
    RagCase(
        "rag-04",
        "¿Cuál es mi deducible por robo total?",
        CoverageType.AMPLIA,
        ("AMP-3.1",),
        32000.0,
        "10% sobre suma asegurada de 320,000.",
    ),
    RagCase(
        "rag-05",
        "¿Cuánto pago de deducible si se roban mi auto?",
        CoverageType.BASICA,
        ("BAS-2.1",),
        32000.0,
        "Robo total sí está amparado en Básica.",
    ),
    RagCase(
        "rag-06",
        "¿Mi póliza cubre el robo total del vehículo?",
        CoverageType.RC,
        ("RC-2.1",),
        None,
        "Debe recuperar la exclusión, no una cláusula de cobertura.",
    ),
    RagCase(
        "rag-07",
        "Se me rompió el parabrisas, ¿está cubierto y cuánto pago?",
        CoverageType.AMPLIA,
        ("AMP-4.2",),
        2400.0,
        "20% sobre el costo de reposición de referencia ($12,000); supera el mínimo de $1,500.",
    ),
    RagCase(
        "rag-08",
        "¿Cubre la rotura de cristales mi paquete?",
        CoverageType.BASICA,
        ("BAS-4.2",),
        None,
        "Debe recuperar la exclusión de cristales de Básica.",
    ),
    RagCase(
        "rag-09",
        "¿Qué deducible tengo por daños materiales tras un choque?",
        CoverageType.AMPLIA,
        ("AMP-2.1",),
        16000.0,
        "5% sobre suma asegurada.",
    ),
    RagCase(
        "rag-10",
        "Si choco mi auto, ¿me cubren la reparación?",
        CoverageType.BASICA,
        ("BAS-2.2",),
        None,
        "Básica excluye daños materiales propios.",
    ),
    RagCase(
        "rag-11",
        "¿Hasta cuánto cubren los gastos médicos de los ocupantes?",
        CoverageType.AMPLIA,
        ("AMP-5.1",),
        None,
        "200,000 por ocupante, sin deducible.",
    ),
    RagCase(
        "rag-12",
        "¿Cuántos servicios de grúa tengo al año?",
        CoverageType.BASICA,
        ("BAS-6.1",),
        None,
        "4 eventos y 50 km, distinto de RC (2 eventos) y Amplia (ilimitado).",
    ),
    RagCase(
        "rag-13",
        "¿La asistencia vial incluye cerrajería?",
        CoverageType.RC,
        ("RC-6.1",),
        None,
        "RC excluye cerrajería explícitamente.",
    ),
    RagCase(
        "rag-14",
        "¿Qué pasa si el conductor iba tomado?",
        CoverageType.AMPLIA,
        ("AMP-9.1",),
        None,
        "Exclusiones generales.",
    ),
    RagCase(
        "rag-15",
        "¿Cuántos días tengo para avisar de un siniestro?",
        CoverageType.AMPLIA,
        ("AMP-8.1",),
        None,
        "Procedimiento de reclamación: 5 días naturales.",
    ),
)


# ---------------------------------------------------------------------------
# Precisión de enrutamiento — tabla PRD §3.1 más variantes adversariales
# ---------------------------------------------------------------------------

ROUTING_CASES: tuple[RoutingCase, ...] = (
    # -- casos textuales del PRD §3.1 ---------------------------------------
    RoutingCase("rt-01", "¿Qué cubre mi póliza de RC?", Route.POLICY, "PRD §3.1"),
    RoutingCase(
        "rt-02",
        "Se me rompió el cristal ayer",
        Route.POLICY,
        "PRD §3.1: primero póliza, la confirmación abre FNOL después.",
    ),
    RoutingCase("rt-03", "¿Cuál es mi deducible por robo total?", Route.POLICY, "PRD §3.1"),
    RoutingCase("rt-04", "¿Dónde hay un taller cerca de Polanco?", Route.NETWORK, "PRD §3.1"),
    RoutingCase("rt-05", "Quiero reportar un choque", Route.FNOL, "PRD §3.1"),
    # -- variantes ----------------------------------------------------------
    RoutingCase(
        "rt-06",
        "Necesito levantar el reporte de mi siniestro",
        Route.FNOL,
        "Intención explícita con otro verbo.",
    ),
    RoutingCase(
        "rt-07",
        "¿Me pueden mandar una grúa? Estoy en Del Valle",
        Route.NETWORK,
        "Asistencia vial: red, no FNOL.",
    ),
    RoutingCase("rt-08", "¿Cuánto es la suma asegurada de mi auto?", Route.POLICY),
    RoutingCase("rt-09", "Hola, buenos días", Route.SMALLTALK),
    RoutingCase(
        "rt-10",
        "Choqué y quiero dar aviso del siniestro formalmente",
        Route.FNOL,
        "Narra y además pide el aviso: gana FNOL.",
    ),
    RoutingCase("rt-11", "¿Qué talleres en convenio hay en Guadalajara?", Route.NETWORK),
    RoutingCase("rt-12", "¿La póliza ampara daños por inundación?", Route.POLICY),
    RoutingCase(
        "rt-13",
        "Me robaron el estéreo del coche anoche",
        Route.POLICY,
        "Adversarial: narra un siniestro sin pedir reporte.",
    ),
    RoutingCase("rt-14", "Gracias por la ayuda", Route.SMALLTALK),
    RoutingCase(
        "rt-15",
        "¿Puedo llevar mi auto chocado a un taller cerca de Satélite?",
        Route.NETWORK,
        "Adversarial: menciona choque pero pregunta por taller.",
    ),
    RoutingCase("rt-16", "¿Cuáles son las exclusiones de mi póliza?", Route.POLICY),
)


# ---------------------------------------------------------------------------
# Flujo FNOL end-to-end
# ---------------------------------------------------------------------------

FNOL_SCENARIOS: tuple[FNOLScenario, ...] = (
    FNOLScenario(
        "fnol-01",
        CoverageType.AMPLIA,
        turns=(
            "Ayer se rompió el cristal de mi auto",
            "Sí, quiero reportarlo",
            "Fue ayer en Avenida Insurgentes, colonia Roma. Una piedra levantada por un camión "
            "rompió el parabrisas mientras circulaba.",
        ),
        note="User journey completo del PRD §6, con evidencia adjunta.",
    ),
    FNOLScenario(
        "fnol-02",
        CoverageType.AMPLIA,
        turns=(
            "Quiero reportar un choque",
            "Fue el 2026-08-28 en Periférico Sur a la altura de San Jerónimo. Me impactaron "
            "por atrás mientras estaba detenido en el semáforo.",
        ),
        expect_claim=True,
        note="Entrada directa a FNOL sin pasar por póliza.",
        evidence=True,
    ),
    FNOLScenario(
        "fnol-03",
        CoverageType.AMPLIA,
        turns=(
            "Ayer se rompió el cristal de mi auto",
            "No, todavía no",
        ),
        expect_claim=False,
        note="El asegurado declina: no debe crearse expediente (PRD §6.4).",
        evidence=False,
    ),
)
