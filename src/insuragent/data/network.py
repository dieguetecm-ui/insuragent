"""Red de talleres con convenio (PRD §3, Agente de Red).

Catálogo estático y sintético. En producción esto sería una consulta geoespacial
contra el padrón de proveedores; para la PoC basta un match por colonia/ciudad
con normalización de acentos, que es determinista y no requiere red externa.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Workshop:
    """Taller en convenio."""

    workshop_id: str
    name: str
    city: str
    neighborhood: str
    address: str
    phone: str
    specialties: tuple[str, ...]

    def describe(self) -> str:
        return (
            f"{self.name} — {self.address}, {self.neighborhood}, {self.city}. "
            f"Tel. {self.phone}. Especialidades: {', '.join(self.specialties)}."
        )


# fmt: off
# Se mantiene como tabla alineada a propósito: es un catálogo, y una fila por
# taller se lee mejor que el desglose que produciría el formateador.
WORKSHOPS: tuple[Workshop, ...] = (
    Workshop("TAL-001", "Servicio Automotriz Polanco", "Ciudad de México", "Polanco",
             "Av. Horacio 1220", "55-5280-1140", ("hojalatería", "pintura", "cristales")),
    Workshop("TAL-002", "Carrocerías Anzures", "Ciudad de México", "Anzures",
             "Leibnitz 87", "55-5531-8890", ("hojalatería", "mecánica")),
    Workshop("TAL-003", "Cristales Express Condesa", "Ciudad de México", "Condesa",
             "Av. Tamaulipas 55", "55-5211-4407", ("cristales",)),
    Workshop("TAL-004", "Taller Del Valle", "Ciudad de México", "Del Valle",
             "Av. Coyoacán 1435", "55-5559-2210", ("hojalatería", "pintura", "mecánica")),
    Workshop("TAL-005", "Autoservicio Satélite", "Ciudad de México", "Ciudad Satélite",
             "Blvd. Manuel Ávila Camacho 2900", "55-5393-6612", ("mecánica", "cristales")),
    Workshop("TAL-006", "Centro de Colisión Providencia", "Guadalajara", "Providencia",
             "Av. Pablo Neruda 3025", "33-3642-7788", ("hojalatería", "pintura")),
    Workshop("TAL-007", "Talleres Chapalita", "Guadalajara", "Chapalita",
             "Av. Guadalupe 1050", "33-3121-5590", ("mecánica", "cristales")),
    Workshop("TAL-008", "Servicio San Pedro", "Monterrey", "San Pedro Garza García",
             "Av. Vasconcelos 220", "81-8338-4471", ("hojalatería", "pintura", "cristales")),
    Workshop("TAL-009", "Autocentro Cumbres", "Monterrey", "Cumbres",
             "Av. Paseo de los Leones 2410", "81-8371-9903", ("mecánica",)),
    Workshop("TAL-010", "Taller Angelópolis", "Puebla", "Angelópolis",
             "Blvd. del Niño Poblano 2510", "22-2225-1180", ("hojalatería", "cristales")),
    Workshop("TAL-011", "Servicio Juriquilla", "Querétaro", "Juriquilla",
             "Paseo de la República 13020", "44-2234-6650", ("mecánica", "pintura")),
    Workshop("TAL-012", "Talleres Montejo", "Mérida", "García Ginerés",
             "Av. Colón 340", "99-9925-7712", ("hojalatería", "mecánica")),
)
# fmt: on


def _normalize(text: str) -> str:
    """Minúsculas sin acentos, para comparar 'Satélite' con 'satelite'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def find_workshops(
    location: str,
    *,
    specialty: str | None = None,
    limit: int = 3,
) -> list[Workshop]:
    """Busca talleres por colonia o ciudad, opcionalmente filtrando por especialidad.

    El orden de preferencia es: coincidencia por colonia, luego por ciudad. Si
    nada coincide, devuelve los primeros talleres del catálogo como fallback
    para que el agente nunca responda con una lista vacía sin alternativas.
    """
    needle = _normalize(location)
    candidates = WORKSHOPS
    if specialty:
        wanted = _normalize(specialty)
        filtered = tuple(
            w for w in candidates if any(wanted in _normalize(s) for s in w.specialties)
        )
        candidates = filtered or candidates

    by_neighborhood = [
        w
        for w in candidates
        if _normalize(w.neighborhood) in needle or needle in _normalize(w.neighborhood)
    ]
    by_city = [
        w
        for w in candidates
        if w not in by_neighborhood
        and (_normalize(w.city) in needle or needle in _normalize(w.city))
    ]

    ordered = by_neighborhood + by_city
    return (ordered or list(candidates))[:limit]
