"""Generación determinista de asegurados sintéticos (PRD §4.3, Fase 1).

Los identificadores respetan el **formato** oficial mexicano pero llevan un
prefijo reservado (`XXX` en RFC, `XXXX` + entidad `NE` en CURP) que los hace
inasignables a una persona real. La semilla vive en `Settings.synthetic_seed`,
así que dos ejecuciones producen exactamente la misma base — condición necesaria
para que las métricas del PRD §5 sean reproducibles.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from insuragent.schemas.auth import Customer, Vehicle
from insuragent.schemas.fnol import ClaimReport, IncidentType
from insuragent.schemas.policy import CoverageType

FIRST_NAMES = [
    "Ana",
    "Bruno",
    "Carmen",
    "Diego",
    "Elena",
    "Fernando",
    "Gabriela",
    "Héctor",
    "Irene",
    "Joaquín",
    "Karla",
    "Luis",
]
LAST_NAMES = [
    "Aguirre",
    "Beltrán",
    "Cervantes",
    "Domínguez",
    "Escobar",
    "Fuentes",
    "Guerrero",
    "Herrera",
    "Ibarra",
    "Jiménez",
    "Kuri",
    "Lozano",
]
CITIES = [
    "Ciudad de México",
    "Guadalajara",
    "Monterrey",
    "Puebla",
    "Querétaro",
    "Mérida",
    "León",
    "Toluca",
]
VEHICLES = [
    ("Nissan", "Versa"),
    ("Volkswagen", "Jetta"),
    ("Toyota", "Corolla"),
    ("Chevrolet", "Aveo"),
    ("Kia", "Rio"),
    ("Mazda", "3"),
    ("Honda", "City"),
    ("Hyundai", "Accent"),
]
CONSONANTS = "BCDFGHJKLMNPQRSTVWXYZ"
VIN_ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # sin I, O, Q, como el estándar


def _synthetic_rfc(rng: random.Random, surname: str, birth: date) -> str:
    """RFC con formato válido y prefijo `XXX` reservado para datos sintéticos."""
    homoclave = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(3))
    return f"XXX{surname[0].upper()}{birth:%y%m%d}{homoclave}"


def _synthetic_curp(rng: random.Random, birth: date, sex: str) -> str:
    """CURP con formato válido, prefijo `XXXX` y entidad `NE` (no especificada)."""
    consonants = "".join(rng.choice(CONSONANTS) for _ in range(3))
    return f"XXXX{birth:%y%m%d}{sex}NE{consonants}{rng.choice('AB')}{rng.randint(0, 9)}"


def _vin(rng: random.Random) -> str:
    return "".join(rng.choice(VIN_ALPHABET) for _ in range(17))


def _plates(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    return f"{letters}{rng.randint(100, 999)}{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"


def generate_customers(count: int, seed: int) -> list[Customer]:
    """Genera `count` asegurados reproducibles a partir de `seed`.

    Se garantiza que las tres variantes de cobertura estén representadas,
    repartiéndolas cíclicamente antes de aleatorizar el resto de los campos.
    """
    rng = random.Random(seed)
    coverage_cycle = [CoverageType.AMPLIA, CoverageType.BASICA, CoverageType.RC]
    customers: list[Customer] = []

    for index in range(count):
        first = rng.choice(FIRST_NAMES)
        paternal = rng.choice(LAST_NAMES)
        maternal = rng.choice(LAST_NAMES)
        sex = "H" if first in {"Bruno", "Diego", "Fernando", "Héctor", "Joaquín", "Luis"} else "M"
        birth = date(1970, 1, 1) + timedelta(days=rng.randint(0, 365 * 35))
        start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 240))
        brand, model = rng.choice(VEHICLES)
        coverage = coverage_cycle[index % len(coverage_cycle)]

        customers.append(
            Customer(
                customer_id=f"CLI-{index + 1:04d}",
                full_name=f"{first} {paternal} {maternal}",
                rfc=_synthetic_rfc(rng, paternal, birth),
                curp=_synthetic_curp(rng, birth, sex),
                phone=f"55{rng.randint(10_000_000, 99_999_999)}",
                email=f"{first.lower()}.{paternal.lower()}@ejemplo-sintetico.mx",
                city=rng.choice(CITIES),
                policy_number=f"AUT-2026-{100000 + index * 137:06d}",
                coverage_type=coverage.value,
                policy_start=start,
                policy_end=start + timedelta(days=365),
                vehicle=Vehicle(
                    vin=_vin(rng),
                    brand=brand,
                    model=model,
                    year=rng.randint(2016, 2026),
                    plates=_plates(rng),
                ),
            )
        )
    return customers


# ---------------------------------------------------------------------------
# Historial de siniestros — memoria de largo plazo (PRD §3.2)
# ---------------------------------------------------------------------------

# Qué siniestros son plausibles bajo cada paquete. Un asegurado con sólo
# Responsabilidad Civil no puede tener un expediente de cristales: el historial
# sintético tiene que ser coherente con lo que cada quien contrató, o la demo de
# memoria de largo plazo mostraría datos imposibles.
HISTORIAL_POR_PAQUETE: dict[str, tuple[tuple[IncidentType, str], ...]] = {
    "amplia": (
        (IncidentType.CRISTALES, "Rotura de parabrisas por grava en carretera federal."),
        (IncidentType.COLISION, "Alcance por detrás en el semáforo de Av. Universidad."),
        (IncidentType.ROBO_PARCIAL, "Robo de espejo lateral izquierdo en estacionamiento público."),
    ),
    "basica": (
        (IncidentType.ROBO_TOTAL, "Robo del vehículo estacionado en vía pública durante la noche."),
        (
            IncidentType.DANOS_TERCEROS,
            "Daño a la defensa de un tercero al salir de un estacionamiento.",
        ),
    ),
    "rc": (
        (IncidentType.DANOS_TERCEROS, "Daño a la puerta de un tercero al abrir la portezuela."),
    ),
}

LUGARES = (
    "Av. Insurgentes Sur, Col. Del Valle",
    "Periférico Sur a la altura de San Jerónimo",
    "Calzada de Tlalpan, Col. Portales",
    "Av. Universidad, Col. Narvarte",
    "Blvd. Manuel Ávila Camacho, Ciudad Satélite",
    "Av. Vallarta, Col. Providencia",
)


def generate_claim_history(
    customers: list[Customer], seed: int, *, fraction: float = 0.5
) -> list[ClaimReport]:
    """Genera expedientes pasados para una parte de la cartera.

    Sin historial previo, la memoria de largo plazo del PRD §3.2 no se puede
    demostrar: el asistente no tendría nada que recordar. Se puebla la mitad de
    los asegurados para que la demo muestre ambos casos —con y sin historial— y
    se pueda comparar el comportamiento.

    Las fechas caen entre 30 y 400 días antes de hoy, y el deducible se calcula
    con la misma función que usa el agente FNOL en producción, no con un número
    inventado: si mañana cambia la tabla de coberturas, el historial cambia con
    ella.
    """
    from insuragent.agents.tools import INCIDENT_TO_COVERAGE, quote_deductible
    from insuragent.schemas.policy import CoverageType

    rng = random.Random(seed + 977)
    hoy = date.today()
    claims: list[ClaimReport] = []
    con_historial = customers[: max(1, int(len(customers) * fraction))]

    for customer in con_historial:
        catalogo = HISTORIAL_POR_PAQUETE[customer.coverage_type]
        cuantos = rng.randint(1, min(2, len(catalogo)))
        for tipo, descripcion in rng.sample(catalogo, cuantos):
            ocurrido = hoy - timedelta(days=rng.randint(30, 400))
            cobertura = INCIDENT_TO_COVERAGE[tipo]
            cotizacion = quote_deductible(CoverageType(customer.coverage_type), cobertura)
            claims.append(
                ClaimReport(
                    claim_id=f"SIN-{ocurrido:%Y%m}-{rng.randint(1, 99999):05d}",
                    customer_id=customer.customer_id,
                    policy_number=customer.policy_number,
                    incident_type=tipo,
                    incident_date=ocurrido,
                    location=rng.choice(LUGARES),
                    description=descripcion,
                    third_parties_involved=tipo is IncidentType.DANOS_TERCEROS,
                    deductible_quoted_mxn=cotizacion.deductible_mxn,
                    created_at=datetime.combine(ocurrido + timedelta(days=1), datetime.min.time()),
                )
            )
    return claims
