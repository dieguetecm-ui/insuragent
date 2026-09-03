"""Diagrama de la arquitectura como SVG en línea.

Se dibuja a mano en lugar de usar Mermaid porque WeasyPrint no ejecuta
JavaScript: un SVG embebido queda vectorial en el PDF, sin dependencias de
render y sin pérdida de nitidez al imprimir o al ampliar.

El trazado evita cruces: cada almacén queda directamente bajo el agente que lo
usa, y la observabilidad se representa como banda transversal en lugar de
flechas hacia los cuatro agentes, que sólo añadirían líneas cruzadas.
"""

from __future__ import annotations

_AZUL = "#1f5f8b"
_TINTA = "#1a1d21"
_TENUE = "#5c6470"
_LINEA = "#b9c1cb"
_CREMA = "#fdf6e3"


def _caja(
    x: int,
    y: int,
    w: int,
    h: int,
    titulo: str,
    subtitulo: str = "",
    relleno: str = "#ffffff",
    borde: str = _LINEA,
) -> str:
    titulo_y = y + h / 2 + 4 if not subtitulo else y + h / 2 - 3
    partes = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{relleno}" '
        f'stroke="{borde}" stroke-width="1.4"/>',
        f'<text x="{x + w / 2}" y="{titulo_y}" text-anchor="middle" font-size="12.5" '
        f'font-weight="600" fill="{_TINTA}">{titulo}</text>',
    ]
    if subtitulo:
        partes.append(
            f'<text x="{x + w / 2}" y="{y + h / 2 + 12}" text-anchor="middle" font-size="9.5" '
            f'fill="{_TENUE}">{subtitulo}</text>'
        )
    return "".join(partes)


def _flecha(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{_LINEA}" '
        f'stroke-width="1.4" marker-end="url(#punta)"/>'
    )


def _etiqueta(x: int, y: int, texto: str, color: str = _AZUL, tam: float = 9.5) -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{tam}" '
        f'font-weight="600" fill="{color}">{texto}</text>'
    )


def arquitectura_svg() -> str:
    """SVG del grafo de agentes, sus almacenes y la observabilidad transversal."""
    piezas: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 400" width="100%" '
        'font-family="DejaVu Sans, sans-serif">',
        '<defs><marker id="punta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" '
        f'fill="{_LINEA}"/></marker></defs>',
        # --- entrada ---------------------------------------------------------
        _caja(280, 6, 200, 36, "Turno del asegurado", relleno="#f2f4f7"),
        _flecha(380, 42, 380, 70),
        # --- orquestador -----------------------------------------------------
        _caja(
            255,
            72,
            250,
            52,
            "Agente Orquestador",
            "structured output → RouteDecision",
            relleno="#eef4f9",
            borde=_AZUL,
        ),
        # --- ramas hacia los agentes ----------------------------------------
        _flecha(310, 124, 105, 168),
        _etiqueta(185, 140, "policy"),
        _flecha(350, 124, 322, 168),
        _etiqueta(310, 145, "fnol"),
        _flecha(415, 124, 497, 168),
        _etiqueta(470, 143, "network"),
        _flecha(455, 124, 665, 168),
        _etiqueta(590, 140, "smalltalk"),
        # --- agentes ---------------------------------------------------------
        _caja(15, 170, 180, 56, "Agente de Pólizas", "RAG · FAISS · deducibles"),
        _caja(240, 170, 165, 56, "Agente FNOL", "extracción + validación"),
        _caja(420, 170, 155, 56, "Agente de Red", "talleres en convenio"),
        _caja(590, 170, 155, 56, "Cortesía", "guion fijo, sin LLM"),
        # --- confirmación entre pólizas y FNOL (PRD §6.4) --------------------
        f'<rect x="197" y="186" width="42" height="24" rx="3" fill="{_CREMA}" '
        f'stroke="{_LINEA}" stroke-width="1"/>',
        _flecha(197, 198, 238, 198),
        _etiqueta(218, 182, "sí", tam=9),
        _etiqueta(218, 243, "¿Levantamos el reporte?", _TENUE, 8.5),
        _etiqueta(218, 254, "confirmación determinista", _TENUE, 8),
        _etiqueta(218, 265, "respuesta negativa → cortesía", _TENUE, 8),
        # --- almacenes, cada uno bajo su consumidor --------------------------
        _caja(15, 285, 180, 50, "Índice FAISS", "19 cláusulas · 3 paquetes"),
        _flecha(105, 285, 105, 230),
        _caja(240, 285, 165, 50, "SQLite + disco", "siniestros · evidencia"),
        _flecha(322, 230, 322, 283),
        _caja(420, 285, 155, 50, "Catálogo de red", "talleres en convenio"),
        _flecha(497, 285, 497, 230),
        # --- observabilidad transversal --------------------------------------
        f'<line x1="15" y1="352" x2="745" y2="352" stroke="{_LINEA}" stroke-width="1" '
        'stroke-dasharray="4,3"/>',
        _caja(240, 358, 280, 34, "Trazas JSONL", relleno="#f7f8fa"),
        _etiqueta(128, 378, "un evento por nodo", _TENUE, 8.5),
        _etiqueta(632, 378, "run_id correlacionado", _TENUE, 8.5),
        "</svg>",
    ]
    return "".join(piezas)
