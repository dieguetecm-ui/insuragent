"""Condiciones generales sintéticas del ramo de automóviles (PRD §4.2).

Se modelan **tres** variantes con cláusulas parcialmente traslapadas para que el
recuperador tenga que discriminar entre textos muy parecidos:

* ``rc``     — Responsabilidad Civil únicamente.
* ``basica`` — RC + Robo Total + Asistencia Vial.
* ``amplia`` — Todo lo anterior + Daños Materiales, Cristales y Gastos Médicos.

La cobertura de Responsabilidad Civil aparece en las tres con **límites
distintos**, y Robo Total aparece en dos con **deducibles distintos**: ése es el
caso duro que un corpus de un solo documento no ejercitaría.

Todos los importes son ficticios y no corresponden a ningún producto comercial.
"""

from __future__ import annotations

from decimal import Decimal

from insuragent.schemas.policy import Clause, Coverage, CoverageType

SUM_INSURED_MXN = Decimal("320000")
GLASS_REFERENCE_COST_MXN = Decimal("12000")

# ---------------------------------------------------------------------------
# Coberturas por variante — la fuente de verdad para el cálculo de deducibles.
# ---------------------------------------------------------------------------

COVERAGES: dict[CoverageType, tuple[Coverage, ...]] = {
    CoverageType.RC: (
        Coverage(
            key="responsabilidad_civil",
            label="Responsabilidad Civil por daños a terceros",
            covered=True,
            deductible_pct=None,
            sum_insured_mxn=Decimal("2000000"),
            notes="Sin deducible. Límite único combinado por evento.",
        ),
        Coverage(
            key="asistencia_vial",
            label="Asistencia vial básica",
            covered=True,
            notes="Hasta 2 eventos por vigencia, arrastre máximo 30 km.",
        ),
        Coverage(key="robo_total", label="Robo total", covered=False),
        Coverage(key="danos_materiales", label="Daños materiales", covered=False),
        Coverage(key="cristales", label="Rotura de cristales", covered=False),
        Coverage(key="gastos_medicos", label="Gastos médicos ocupantes", covered=False),
    ),
    CoverageType.BASICA: (
        Coverage(
            key="responsabilidad_civil",
            label="Responsabilidad Civil por daños a terceros",
            covered=True,
            sum_insured_mxn=Decimal("3000000"),
            notes="Sin deducible. Incluye daño moral hasta el límite contratado.",
        ),
        Coverage(
            key="robo_total",
            label="Robo total del vehículo",
            covered=True,
            deductible_pct=Decimal("10"),
            sum_insured_mxn=SUM_INSURED_MXN,
            notes="Deducible del 10% sobre el valor comercial al momento del siniestro.",
        ),
        Coverage(
            key="asistencia_vial",
            label="Asistencia vial",
            covered=True,
            notes="Hasta 4 eventos por vigencia, arrastre máximo 50 km.",
        ),
        Coverage(key="danos_materiales", label="Daños materiales", covered=False),
        Coverage(key="cristales", label="Rotura de cristales", covered=False),
        Coverage(key="gastos_medicos", label="Gastos médicos ocupantes", covered=False),
    ),
    CoverageType.AMPLIA: (
        Coverage(
            key="responsabilidad_civil",
            label="Responsabilidad Civil por daños a terceros",
            covered=True,
            sum_insured_mxn=Decimal("4000000"),
            notes="Sin deducible. Incluye RC en el extranjero dentro de EUA y Canadá.",
        ),
        Coverage(
            key="danos_materiales",
            label="Daños materiales al vehículo asegurado",
            covered=True,
            deductible_pct=Decimal("5"),
            sum_insured_mxn=SUM_INSURED_MXN,
            notes="Deducible del 5% sobre el valor comercial. Aplica por evento.",
        ),
        Coverage(
            key="robo_total",
            label="Robo total del vehículo",
            covered=True,
            deductible_pct=Decimal("10"),
            sum_insured_mxn=SUM_INSURED_MXN,
            notes="Deducible del 10% sobre el valor comercial al momento del siniestro.",
        ),
        Coverage(
            key="cristales",
            label="Rotura de cristales",
            covered=True,
            deductible_pct=Decimal("20"),
            deductible_min_mxn=Decimal("1500"),
            # Base de referencia: costo de reposición de un parabrisas de gama media.
            # Se usa sólo para cotizar un estimado cuando el asegurado aún no tiene
            # presupuesto del taller; con presupuesto real, `quote_deductible` recibe
            # `repair_cost_mxn` y esta cifra deja de intervenir.
            sum_insured_mxn=GLASS_REFERENCE_COST_MXN,
            notes="Deducible del 20% del costo de reposición, con mínimo de $1,500 MXN.",
        ),
        Coverage(
            key="gastos_medicos",
            label="Gastos médicos ocupantes",
            covered=True,
            sum_insured_mxn=Decimal("200000"),
            notes="Sin deducible. Límite por ocupante hasta el número de plazas de fábrica.",
        ),
        Coverage(
            key="asistencia_vial",
            label="Asistencia vial premium",
            covered=True,
            notes="Eventos ilimitados, arrastre sin límite de kilometraje a taller en convenio.",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Cláusulas indexables. El texto es deliberadamente similar entre variantes.
# ---------------------------------------------------------------------------

CLAUSES: tuple[Clause, ...] = (
    # ---- Responsabilidad Civil (aparece en las tres variantes) -------------
    Clause(
        clause_id="RC-1.1",
        coverage_type=CoverageType.RC,
        coverage_key="responsabilidad_civil",
        title="Responsabilidad Civil por daños a terceros",
        text=(
            "La Compañía cubre la responsabilidad civil en que incurra el Asegurado por daños "
            "materiales a bienes de terceros y por lesiones o muerte de terceros, derivados del uso "
            "del vehículo asegurado. El límite único y combinado por evento es de $2,000,000.00 MXN. "
            "Esta cobertura opera sin deducible."
        ),
    ),
    Clause(
        clause_id="BAS-1.1",
        coverage_type=CoverageType.BASICA,
        coverage_key="responsabilidad_civil",
        title="Responsabilidad Civil por daños a terceros",
        text=(
            "La Compañía cubre la responsabilidad civil del Asegurado por daños materiales a bienes "
            "de terceros y por lesiones o muerte de terceros, derivados del uso del vehículo "
            "asegurado. El límite único y combinado por evento es de $3,000,000.00 MXN e incluye la "
            "reclamación por daño moral hasta el límite contratado. Esta cobertura opera sin deducible."
        ),
    ),
    Clause(
        clause_id="AMP-1.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="responsabilidad_civil",
        title="Responsabilidad Civil por daños a terceros",
        text=(
            "La Compañía cubre la responsabilidad civil del Asegurado por daños materiales a bienes "
            "de terceros y por lesiones o muerte de terceros, derivados del uso del vehículo "
            "asegurado. El límite único y combinado por evento es de $4,000,000.00 MXN e incluye la "
            "responsabilidad civil por circulación en los Estados Unidos de América y Canadá. "
            "Esta cobertura opera sin deducible."
        ),
    ),
    # ---- Robo total (aparece en dos variantes, deducible idéntico) ---------
    Clause(
        clause_id="BAS-2.1",
        coverage_type=CoverageType.BASICA,
        coverage_key="robo_total",
        title="Robo total del vehículo",
        text=(
            "Se ampara la pérdida total del vehículo asegurado por robo. La indemnización se "
            "determina sobre el valor comercial del vehículo al momento del siniestro, aplicando un "
            "deducible del 10% sobre dicho valor. La cobertura procede únicamente si se presenta la "
            "denuncia ante el Ministerio Público dentro de las 24 horas siguientes al hecho."
        ),
    ),
    Clause(
        clause_id="AMP-3.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="robo_total",
        title="Robo total del vehículo",
        text=(
            "Se ampara la pérdida total del vehículo asegurado por robo. La indemnización se "
            "determina sobre el valor comercial del vehículo al momento del siniestro, aplicando un "
            "deducible del 10% sobre dicho valor. Se requiere la denuncia ante el Ministerio Público "
            "dentro de las 24 horas y la entrega de ambos juegos de llaves y la factura original."
        ),
    ),
    Clause(
        clause_id="RC-2.1",
        coverage_type=CoverageType.RC,
        coverage_key="robo_total",
        title="Exclusión de robo total",
        text=(
            "La cobertura de Responsabilidad Civil no ampara en ningún caso la pérdida, daño o robo "
            "del vehículo asegurado. El robo total y el robo parcial quedan expresamente excluidos "
            "de este paquete y sólo pueden contratarse bajo los paquetes Básica o Amplia."
        ),
    ),
    # ---- Daños materiales (sólo amplia) ------------------------------------
    Clause(
        clause_id="AMP-2.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="danos_materiales",
        title="Daños materiales al vehículo asegurado",
        text=(
            "Se amparan los daños materiales que sufra el vehículo asegurado por colisión, volcadura, "
            "incendio, rayo, explosión y fenómenos hidrometeorológicos. Se aplica un deducible del 5% "
            "sobre el valor comercial del vehículo por cada evento. La reparación se realiza en "
            "talleres de la red en convenio salvo pacto expreso en contrario."
        ),
    ),
    Clause(
        clause_id="BAS-2.2",
        coverage_type=CoverageType.BASICA,
        coverage_key="danos_materiales",
        title="Exclusión de daños materiales",
        text=(
            "El paquete Básica no ampara los daños materiales que sufra el vehículo asegurado por "
            "colisión, volcadura o incendio. Estos daños únicamente se cubren bajo el paquete Amplia. "
            "La atención de daños a terceros se mantiene bajo la cobertura de Responsabilidad Civil."
        ),
    ),
    # ---- Cristales (sólo amplia; caso del user journey PRD §6.2) ----------
    Clause(
        clause_id="AMP-4.2",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="cristales",
        title="Rotura de cristales",
        text=(
            "Se ampara la rotura de parabrisas, medallón, cristales laterales y quemacocos del "
            "vehículo asegurado, por cualquier causa accidental. Se aplica un deducible del 20% sobre "
            "el costo de reposición del cristal, con un mínimo de $1,500.00 MXN por evento. No se "
            "amparan espejos laterales, micas de faros ni calaveras."
        ),
    ),
    Clause(
        clause_id="BAS-4.2",
        coverage_type=CoverageType.BASICA,
        coverage_key="cristales",
        title="Exclusión de rotura de cristales",
        text=(
            "La rotura de cristales del vehículo asegurado no está amparada bajo el paquete Básica. "
            "El Asegurado puede contratar esta protección migrando al paquete Amplia en la siguiente "
            "renovación de la póliza."
        ),
    ),
    # ---- Gastos médicos ----------------------------------------------------
    Clause(
        clause_id="AMP-5.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="gastos_medicos",
        title="Gastos médicos ocupantes",
        text=(
            "Se cubren los gastos médicos, hospitalarios y de ambulancia de los ocupantes del "
            "vehículo asegurado, incluido el conductor, derivados de un accidente de tránsito. El "
            "límite es de $200,000.00 MXN por ocupante, hasta el número de plazas de fábrica. Esta "
            "cobertura opera sin deducible."
        ),
    ),
    # ---- Asistencia vial (aparece en las tres, con alcances distintos) -----
    Clause(
        clause_id="AMP-6.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key="asistencia_vial",
        title="Asistencia vial premium",
        text=(
            "Se otorga servicio de grúa, paso de corriente, cambio de llanta, envío de gasolina y "
            "cerrajería, con eventos ilimitados durante la vigencia y arrastre sin límite de "
            "kilometraje siempre que el destino sea un taller de la red en convenio."
        ),
    ),
    Clause(
        clause_id="BAS-6.1",
        coverage_type=CoverageType.BASICA,
        coverage_key="asistencia_vial",
        title="Asistencia vial",
        text=(
            "Se otorga servicio de grúa, paso de corriente, cambio de llanta y cerrajería, con un "
            "máximo de 4 eventos durante la vigencia y arrastre de hasta 50 kilómetros. El excedente "
            "de kilometraje corre por cuenta del Asegurado."
        ),
    ),
    Clause(
        clause_id="RC-6.1",
        coverage_type=CoverageType.RC,
        coverage_key="asistencia_vial",
        title="Asistencia vial básica",
        text=(
            "Se otorga servicio de grúa y paso de corriente, con un máximo de 2 eventos durante la "
            "vigencia y arrastre de hasta 30 kilómetros. No incluye cerrajería ni envío de gasolina."
        ),
    ),
    # ---- Exclusiones generales (comunes a las tres variantes) --------------
    Clause(
        clause_id="AMP-9.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key=None,
        title="Exclusiones generales",
        text=(
            "En ningún caso se amparan los siniestros ocurridos cuando el conductor se encuentre bajo "
            "el influjo de bebidas alcohólicas o drogas, carezca de licencia vigente, participe en "
            "competencias de velocidad, o utilice el vehículo para transporte público de pasajeros "
            "sin haberlo declarado en la carátula de la póliza."
        ),
    ),
    Clause(
        clause_id="BAS-9.1",
        coverage_type=CoverageType.BASICA,
        coverage_key=None,
        title="Exclusiones generales",
        text=(
            "En ningún caso se amparan los siniestros ocurridos cuando el conductor se encuentre bajo "
            "el influjo de bebidas alcohólicas o drogas, carezca de licencia vigente, o utilice el "
            "vehículo para transporte público de pasajeros sin haberlo declarado en la carátula."
        ),
    ),
    Clause(
        clause_id="RC-9.1",
        coverage_type=CoverageType.RC,
        coverage_key=None,
        title="Exclusiones generales",
        text=(
            "En ningún caso se ampara la responsabilidad civil derivada de siniestros ocurridos "
            "cuando el conductor se encuentre bajo el influjo de bebidas alcohólicas o drogas, "
            "carezca de licencia vigente, o participe en competencias de velocidad."
        ),
    ),
    # ---- Procedimiento de reclamación (común, redacción casi idéntica) -----
    Clause(
        clause_id="AMP-8.1",
        coverage_type=CoverageType.AMPLIA,
        coverage_key=None,
        title="Procedimiento de reclamación",
        text=(
            "El Asegurado debe dar aviso del siniestro dentro de los 5 días naturales siguientes a su "
            "ocurrencia, proporcionar la ubicación del evento y permitir la inspección del vehículo. "
            "La falta de aviso oportuno faculta a la Compañía a reducir la indemnización."
        ),
    ),
    Clause(
        clause_id="BAS-8.1",
        coverage_type=CoverageType.BASICA,
        coverage_key=None,
        title="Procedimiento de reclamación",
        text=(
            "El Asegurado debe dar aviso del siniestro dentro de los 5 días naturales siguientes a su "
            "ocurrencia y proporcionar la ubicación del evento. La falta de aviso oportuno faculta a "
            "la Compañía a reducir la indemnización en la proporción del perjuicio causado."
        ),
    ),
)


def clauses_for(coverage_type: CoverageType) -> tuple[Clause, ...]:
    """Cláusulas pertenecientes a una variante de condiciones generales."""
    return tuple(c for c in CLAUSES if c.coverage_type == coverage_type)


def coverages_for(coverage_type: CoverageType) -> tuple[Coverage, ...]:
    return COVERAGES[coverage_type]


def render_markdown(coverage_type: CoverageType) -> str:
    """Documento legible de una variante, para versionar en `data/raw/`."""
    titles = {
        CoverageType.RC: "Condiciones Generales — Paquete Responsabilidad Civil",
        CoverageType.BASICA: "Condiciones Generales — Paquete Básica",
        CoverageType.AMPLIA: "Condiciones Generales — Paquete Amplia",
    }
    lines = [
        f"# {titles[coverage_type]}",
        "",
        "> Documento **sintético** generado para la PoC InsurAgent. No corresponde a",
        "> ningún producto comercial ni constituye una oferta de seguro.",
        "",
    ]
    for clause in clauses_for(coverage_type):
        lines += [f"## {clause.clause_id} — {clause.title}", "", clause.text, ""]
    return "\n".join(lines)
