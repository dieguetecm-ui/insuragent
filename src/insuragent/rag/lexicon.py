"""Léxico del dominio asegurador para la recuperación léxica.

El embedder `hash` compara palabras, no significados: para él «choqué» y
«colisión» no tienen nada que ver, aunque el asegurado use una y la póliza la
otra. Ese desajuste entre el habla del cliente y la redacción contractual es el
problema central de un buscador léxico en seguros.

La solución aquí es un léxico explícito: cada grupo de sinónimos aporta un
término canónico que se añade como característica adicional tanto al indexar la
cláusula como al consultar. Así «choqué mi auto» y «daños por colisión» acaban
compartiendo la característica `#colision`.

Se prefiere un léxico revisable a un modelo denso por una razón operativa: cabe
en un despliegue gratuito sin arrastrar PyTorch, es auditable por un experto en
seguros y se corrige añadiendo una palabra. Su límite es que sólo cubre lo que
está escrito abajo — un modelo denso generaliza a términos no previstos.
"""

from __future__ import annotations

# término canónico → variantes que el asegurado o la póliza pueden usar.
GRUPOS: dict[str, tuple[str, ...]] = {
    "colision": (
        "choque",
        "choques",
        "choco",
        "choque",
        "choque",
        "colision",
        "colisiones",
        "impacto",
        "impactaron",
        "alcance",
        "alcanzaron",
        "golpe",
        "golpearon",
        "volcadura",
        "volco",
        "estrello",
        "estrelle",
        "estrellado",
        "topon",
    ),
    "cristales": (
        "cristal",
        "cristales",
        "parabrisas",
        "medallon",
        "vidrio",
        "vidrios",
        "quemacocos",
        "luna",
        "lunas",
    ),
    "robo": ("robo", "robaron", "roban", "robar", "robado", "hurto", "sustraccion"),
    "reparacion": (
        "reparacion",
        "reparar",
        "reparen",
        "arreglo",
        "arreglar",
        "arreglen",
        "compostura",
        "reposicion",
        "reponer",
    ),
    "cobertura": (
        "cubre",
        "cubren",
        "cubierto",
        "cubierta",
        "ampara",
        "amparado",
        "amparada",
        "amparan",
        "cobertura",
        "coberturas",
        "protege",
        "incluye",
    ),
    "exclusion": (
        "excluye",
        "excluido",
        "excluida",
        "exclusion",
        "exclusiones",
        "excluyen",
        "queda",
        "quedan",
    ),
    "deducible": ("deducible", "deducibles", "coaseguro"),
    "taller": ("taller", "talleres", "hojalateria", "hojalatero", "convenio"),
    "asistencia": (
        "grua",
        "gruas",
        "arrastre",
        "asistencia",
        "vial",
        "corriente",
        "cerrajeria",
        "llanta",
        "gasolina",
    ),
    "terceros": ("tercero", "terceros", "ajeno", "ajenos", "responsabilidad", "civil"),
    "lesiones": (
        "lesion",
        "lesiones",
        "medico",
        "medicos",
        "hospital",
        "hospitalarios",
        "ambulancia",
        "ocupantes",
        "heridos",
    ),
    "alcohol": ("alcohol", "alcoholicas", "tomado", "ebrio", "ebriedad", "drogas"),
    "aviso": ("aviso", "avisar", "reportar", "reporte", "denuncia", "denunciar", "plazo", "dias"),
    "monto": ("limite", "limites", "suma", "asegurada", "monto", "cuanto", "pago", "pagar"),
}

# Índice inverso, construido una vez: variante → término canónico.
CANONICO: dict[str, str] = {
    variante: canonico for canonico, variantes in GRUPOS.items() for variante in variantes
}


def expandir(tokens: list[str]) -> list[str]:
    """Añade el término canónico de cada token reconocido.

    Devuelve sólo las características **adicionales**, marcadas con `#` para que
    no colisionen con palabras reales del texto.
    """
    return [f"#{CANONICO[token]}" for token in tokens if token in CANONICO]
