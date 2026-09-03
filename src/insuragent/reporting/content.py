"""Contenido narrativo del reporte técnico.

Cada capítulo es una función que devuelve HTML. El texto describe decisiones y
sus razones, no sólo resultados: un reporte que dice «100 % de precisión» sin
explicar contra qué se midió no sirve para tomar decisiones.
"""

from __future__ import annotations

import re
from html import escape

from insuragent.data.corpus import CLAUSES
from insuragent.reporting.builder import ReportData
from insuragent.reporting.diagram import arquitectura_svg
from insuragent.schemas.policy import CoverageType

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _fecha_larga(valor) -> str:
    """Fecha en español sin depender del locale del sistema.

    `strftime("%B")` devuelve el mes en el idioma que tenga configurado la
    máquina, así que en un servidor con locale C saldría en inglés.
    """
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


# ---------------------------------------------------------------------------
# Utilidades de composición
# ---------------------------------------------------------------------------


def _tabla(encabezados: list[str], filas: list[list[str]], clases: list[str] | None = None) -> str:
    clases = clases or [""] * len(encabezados)
    cabeza = "".join(
        f'<th class="{c}">{escape(h)}</th>' for h, c in zip(encabezados, clases, strict=True)
    )
    cuerpo = "".join(
        "<tr>"
        + "".join(f'<td class="{c}">{v}</td>' for v, c in zip(fila, clases, strict=True))
        + "</tr>"
        for fila in filas
    )
    return f"<table><thead><tr>{cabeza}</tr></thead><tbody>{cuerpo}</tbody></table>"


def _callout(titulo: str, cuerpo: str, tipo: str = "") -> str:
    clase = f"callout {tipo}".strip()
    return f'<div class="{clase}"><div class="titulo">{escape(titulo)}</div>{cuerpo}</div>'


def _metrica(valor: str, etiqueta: str, umbral: str = "") -> str:
    pie = f'<div class="umbral">{escape(umbral)}</div>' if umbral else ""
    return (
        f'<div class="metrica"><div class="valor">{escape(valor)}</div>'
        f'<div class="etiqueta">{escape(etiqueta)}</div>{pie}</div>'
    )


def _marca(ok: bool) -> str:
    return '<span class="ok">✓</span>' if ok else '<span class="fallo">✗</span>'


def _pct(data: ReportData, clave: str) -> str:
    valor = data.metricas.get(clave)
    return f"{valor:.0%}" if isinstance(valor, (int, float)) else "—"


def _capitulo(titulo: str, cuerpo: str) -> str:
    return f'<section class="capitulo"><h1>{escape(titulo)}</h1>{cuerpo}</section>'


# ---------------------------------------------------------------------------
# Capítulos
# ---------------------------------------------------------------------------


def portada(data: ReportData) -> str:
    return f"""
<div class="portada">
  <div class="eyebrow">Prueba de Concepto · Ramo Automóviles</div>
  <h1>InsurAgent</h1>
  <div class="subtitulo">Reporte técnico de un asistente agéntico para el sector asegurador:
  arquitectura, razonamiento de diseño, métricas de evaluación e infraestructura.</div>
  <div class="regla"></div>
  <dl>
    <dt>Autor</dt><dd>Diego Carrillo Mondragón</dd>
    <dt>Fecha de generación</dt><dd>{_fecha_larga(data.generado)}</dd>
    <dt>Proveedor evaluado</dt><dd>{escape(data.proveedor)} · {escape(data.modelo)}</dd>
    <dt>Embeddings</dt><dd>{escape(data.embedder)}</dd>
  </dl>
  <div class="pie">Documento generado automáticamente a partir de la corrida de evaluación.
  Todos los datos son sintéticos: identificadores, condiciones generales, importes y
  catálogo de talleres son ficticios y no corresponden a personas ni a productos reales.</div>
</div>
"""


def contenidos() -> str:
    capitulos = [
        ("Resumen y métricas de aceptación", "Las cinco métricas del PRD §5 y cómo leerlas."),
        ("Arquitectura agéntica", "Topología del grafo, el orquestador y la máquina de estados."),
        ("Recuperación aumentada (RAG)", "Diseño del corpus, decisiones de indexado y resultados."),
        (
            "Conversaciones trazadas",
            "Tres conversaciones reales, turno a turno, con su traza interna.",
        ),
        ("Contratos de datos y validación", "Cómo se impide que una alucinación llegue a la base."),
        ("Aritmética fuera del modelo", "Por qué el deducible no lo calcula el LLM."),
        ("Gestión de memoria", "Memoria de sesión y memoria de largo plazo: dónde vive cada una."),
        ("Observabilidad", "Trazado por nodo y auditoría de las decisiones de enrutamiento."),
        ("Latencia y costo", "Consumo medido y las decisiones que lo mantienen bajo."),
        ("Seguridad y datos personales", "LFPDPPP, datos sintéticos y gestión de secretos."),
        ("Infraestructura en GCP", "Equivalencias local ↔ nube y el esquema de Terraform."),
        (
            "Acceso al servicio y credenciales",
            "Cómo levantar la aplicación y con qué datos entrar.",
        ),
        ("Limitaciones y siguientes pasos", "Qué queda fuera y qué habría que hacer después."),
    ]
    filas = "".join(
        f"<li>{escape(t)}<span class='desc'>{escape(d)}</span></li>" for t, d in capitulos
    )
    return f'<div class="toc"><h1>Contenido</h1><ol>{filas}</ol></div>'


def resumen(data: ReportData) -> str:
    intro = """
<p><strong>InsurAgent</strong> es un sistema agéntico conversacional que interpreta las
condiciones generales de una póliza de automóvil y asiste al asegurado en tres tareas:
consultar coberturas y deducibles, levantar el reporte de un siniestro (FNOL) y localizar
talleres de la red en convenio.</p>

<p>La PoC corre íntegramente en local —SQLite, FAISS y Streamlit—, con el modelo de lenguaje
como único componente remoto. Su equivalente en Google Cloud está escrito en Terraform y
validado, de modo que el salto a la nube no requiere rediseñar nada.</p>
"""

    if not data.hay_metricas:
        return intro + _callout(
            "Sin métricas en este documento",
            "<p>No se encontró <code>data/evaluation_report.json</code>. Ejecuta "
            "<code>make eval</code> y vuelve a generar el reporte para incluir los resultados.</p>",
            "alerta",
        )

    m = data.metricas
    tarjetas = "".join(
        [
            _metrica(_pct(data, "rag_precision"), "Recuperación RAG", "umbral ≥ 80 %"),
            _metrica(_pct(data, "deductible_precision"), "Deducible cotizado", "umbral 100 %"),
            _metrica(_pct(data, "routing_accuracy"), "Enrutamiento", "umbral ≥ 85 %"),
            _metrica(_pct(data, "fnol_end_to_end"), "FNOL end-to-end", "umbral 100 %"),
            _metrica(
                f"{m.get('avg_latency_ms', 0):.0f} ms", "Latencia media/turno", "umbral < 5 000 ms"
            ),
            _metrica(
                f"${m.get('session_cost_usd', 0):.5f}", "Costo por sesión", "umbral < $0.10 USD"
            ),
        ]
    )

    aviso = ""
    if data.degradada:
        aviso = _callout(
            "Corrida degradada: estas cifras no representan al modelo",
            f"<p>Se configuró el proveedor <code>{escape(data.proveedor_configurado)}</code> pero la "
            f"evaluación corrió con <code>{escape(data.proveedor)}</code>, porque el primero no estaba "
            "disponible (sin credenciales, sin red, o sin el modelo descargado).</p>"
            "<p>Para una medición válida: colocar <code>ANTHROPIC_API_KEY</code> en <code>.env</code>, "
            "ejecutar <code>make eval</code> y regenerar este documento.</p>",
            "alerta",
        )
    elif data.proveedor == "stub":
        aviso = _callout(
            "Línea base, no medición del modelo",
            "<p>La corrida usó el proveedor <code>stub</code>, cuyo enrutamiento son reglas "
            "deterministas escritas conociendo estos mismos casos. Sirve como piso de comparación: "
            "si el modelo no supera estas cifras, no está aportando.</p>",
            "aviso",
        )

    detalle = _tabla(
        ["Concepto", "Valor"],
        [
            ["Latencia p95 por turno", f"{m.get('p95_latency_ms', 0):.0f} ms"],
            ["Tokens de entrada", f"{m.get('total_input_tokens', 0):,}"],
            ["Tokens de salida", f"{m.get('total_output_tokens', 0):,}"],
            ["Corrida ejecutada", escape(str(data.evaluacion.get("started_at", "—")))],
        ],
        ["", "num"],
    )

    return (
        intro
        + f'<div class="metricas">{tarjetas}</div>'
        + aviso
        + "<h2>Detalle de la corrida</h2>"
        + detalle
    )


def arquitectura(data: ReportData) -> str:
    diagrama = (
        f"<figure>{arquitectura_svg()}"
        "<figcaption>Grafo de agentes. El Orquestador es el único nodo condicional; los cuatro "
        "agentes son terminales. Todos los nodos emiten trazas, de ahí la banda transversal "
        "inferior.</figcaption></figure>"
    )

    decisiones = _tabla(
        ["Decisión de diseño", "Razón"],
        [
            [
                "La confirmación «¿deseas reportarlo?» se resuelve con reglas, no con el LLM",
                "Un sí/no no justifica una llamada al modelo: ni su latencia, ni su costo, ni su "
                "varianza. La comparación es por token completo, no por subcadena, para que "
                "<code>nosotros</code> no se lea como <code>no</code>.",
            ],
            [
                "Dentro del flujo FNOL el orquestador no vuelve a clasificar",
                "Reclasificar cada turno sacaría al asegurado del flujo a la mitad —por ejemplo si "
                "al describir el percance menciona un taller—. La continuidad es una regla explícita "
                "de la máquina de estados, no un accidente.",
            ],
            [
                "El enrutamiento usa salida estructurada, sin clasificador adicional",
                "El modelo devuelve un JSON validado contra <code>RouteDecision</code> (ruta, "
                "confianza y justificación). La justificación se persiste en la traza: sin ella no "
                "se puede auditar por qué una consulta terminó en cierto agente.",
            ],
            [
                "El nodo de cortesía no consume modelo",
                "Su guion es fijo y auditable. Gastar tokens en «gracias, ¿algo más?» no aporta "
                "calidad y sí introduce variabilidad.",
            ],
        ],
    )

    estados = _tabla(
        ["Etapa", "Significado", "Qué la abre"],
        [
            [
                "<code>idle</code>",
                "Conversación libre; cada turno se enruta desde cero.",
                "Inicio de sesión, o una negativa.",
            ],
            [
                "<code>confirm_fnol</code>",
                "Se evaluó la póliza y se preguntó si desea reportar.",
                "El Agente de Pólizas detecta un siniestro amparado.",
            ],
            [
                "<code>collecting</code>",
                "El Agente FNOL recolecta los datos del siniestro.",
                "Confirmación afirmativa, o intención explícita de reportar.",
            ],
            [
                "<code>awaiting_evidence</code>",
                "Datos completos; falta la fotografía del daño.",
                "El borrador pasa la validación de completitud.",
            ],
            [
                "<code>done</code>",
                "Expediente registrado con folio.",
                "Se adjunta la evidencia, o el asegurado la omite.",
            ],
        ],
    )

    cuerpo = (
        "<p>El sistema es un grafo de estados de LangGraph con un nodo condicional —el "
        "Orquestador— y cuatro agentes terminales. Sobre ese grafo corre una máquina de estados "
        "que da continuidad al flujo de reporte a lo largo de varios turnos.</p>"
        + diagrama
        + "<h2>Decisiones que definen el comportamiento</h2>"
        + decisiones
        + "<h2>Máquina de estados de la conversación</h2>"
        + "<p>El PRD §6 describe el recorrido del usuario en prosa. Traducido a estados explícitos, "
        "queda así —y es lo que permite que el sistema retome una conversación a medias sin "
        "volver a preguntar lo ya capturado:</p>" + estados
    )

    if data.hay_metricas and "precisión_enrutamiento" in data.bloques:
        casos = data.bloques["precisión_enrutamiento"]["cases"]
        filas = [
            [
                f"<code>{escape(c['case_id'])}</code>",
                escape(c["expected"]),
                escape(c["observed"]),
                _marca(c["passed"]),
            ]
            for c in casos
        ]
        cuerpo += (
            "<h2>Resultados por caso de enrutamiento</h2>"
            "<p>Los cinco primeros casos son la tabla textual del PRD §3.1; el resto son variantes "
            "adversariales: menciones de siniestro que <em>no</em> deben abrir un expediente, y "
            "preguntas de taller que mencionan un choque.</p>"
            + _tabla(
                ["Caso", "Ruta esperada", "Ruta observada", "Correcto"],
                filas,
                ["", "", "", "centro"],
            )
        )
    return cuerpo


def rag(data: ReportData) -> str:
    conteo = {ct: sum(1 for c in CLAUSES if c.coverage_type is ct) for ct in CoverageType}
    corpus = _tabla(
        ["Paquete", "Cláusulas", "Alcance"],
        [
            [
                "Responsabilidad Civil",
                str(conteo[CoverageType.RC]),
                "Sólo RC ($2 MDP) y asistencia vial básica.",
            ],
            [
                "Básica",
                str(conteo[CoverageType.BASICA]),
                "RC ($3 MDP), robo total y asistencia vial ampliada.",
            ],
            [
                "Amplia",
                str(conteo[CoverageType.AMPLIA]),
                "Todo lo anterior más daños materiales, cristales y gastos médicos.",
            ],
        ],
        ["", "num", ""],
    )

    decisiones = _tabla(
        ["Decisión", "Razón"],
        [
            [
                "<code>IndexFlatIP</code> sobre vectores normalizados L2",
                f"El score es coseno exacto. Con {len(CLAUSES)} cláusulas, un índice aproximado "
                "(IVF/HNSW) sólo añadiría error e hiperparámetros sin ganancia de latencia medible.",
            ],
            [
                "Una cláusula equivale a un fragmento",
                "La cláusula ya es la unidad semántica del documento. Partir por ventana fija "
                "separaría el deducible de la cobertura a la que pertenece.",
            ],
            [
                "Se antepone el nombre del paquete al texto vectorizado",
                "Sin esa señal, las tres versiones de la cláusula de Responsabilidad Civil producen "
                "vectores casi idénticos y el recuperador elige prácticamente al azar.",
            ],
            [
                "El filtro por paquete se aplica <em>después</em> de la búsqueda vectorial",
                "Filtrar antes volvería trivial el problema y produciría una métrica inflada. Se "
                "sobre-recupera y luego se restringe, de modo que el recuperador tenga que "
                "discriminar de verdad entre textos casi iguales.",
            ],
        ],
    )

    cuerpo = (
        "<p>Se indexan <strong>tres</strong> variantes de condiciones generales con cláusulas "
        "deliberadamente traslapadas. La cobertura de Responsabilidad Civil aparece en las tres "
        "con límites distintos, y Robo Total aparece en dos con el mismo deducible pero requisitos "
        "distintos.</p>"
        "<p>Ese traslape es el punto del ejercicio: un corpus de un solo documento no obliga al "
        "recuperador a discriminar y produce métricas engañosamente altas.</p>"
        + corpus
        + "<h2>Decisiones de indexado</h2>"
        + decisiones
    )

    cuerpo += (
        "<h2>Dos caminos para el mismo resultado</h2>"
        "<p>La recuperación admite dos backends intercambiables, y la elección resultó ser una "
        "decisión de despliegue antes que de calidad.</p>"
        + _tabla(
            ["Backend", "Precisión RAG", "Memoria del proceso", "Arranque"],
            [
                ["Modelo denso multilingüe", "15/15 · 100 %", "2 158 MB", "≈ 6 s"],
                [
                    "Léxico con diccionario del dominio",
                    "<b>15/15 · 100 %</b>",
                    "<b>214 MB</b>",
                    "<b>0.3 s</b>",
                ],
            ],
            ["", "centro", "num", "num"],
        )
        + "<p>El modelo denso no cabe en un hosting gratuito: PyTorch más el modelo llevan el "
        "proceso a más de 2 GB. La alternativa fue un diccionario del dominio que traduce el habla "
        "del asegurado a la redacción contractual —«choqué» y «colisión» comparten un término "
        "canónico que se añade como característica tanto al indexar como al consultar—, con las "
        "características del dominio ponderadas por encima de los n-gramas de carácter, que son "
        "decenas por frase y ahogaban la señal.</p>"
        + _callout(
            "Igualar no es equivaler",
            "<p>Que ambos midan 15/15 sobre este set no los hace intercambiables. El diccionario "
            "sólo cubre lo que está escrito en él; el modelo denso generaliza a términos no "
            "previstos. Con 19 cláusulas y un vocabulario acotado esa ventaja no se manifiesta, "
            "pero con un corpus de miles reaparecería — y entonces el modelo denso volvería a ser "
            "la elección correcta, sobre un plan con memoria suficiente.</p>"
            "<p>La contrapartida es que el diccionario es auditable por un experto en seguros y se "
            "corrige añadiendo una palabra, cosa que un modelo denso no permite.</p>",
        )
    )

    if data.hay_metricas and "precisión_rag" in data.bloques:
        casos = data.bloques["precisión_rag"]["cases"]
        ded = {c["case_id"]: c for c in data.bloques["precisión_deducible"]["cases"]}
        filas = [
            [
                f"<code>{escape(c['case_id'])}</code>",
                f"<code>{escape(c['expected'])}</code>",
                escape(c["observed"])[:60],
                _marca(c["passed"]),
                _marca(ded.get(c["case_id"], {}).get("passed", False)),
            ]
            for c in casos
        ]
        cuerpo += "<h2>Resultados por pregunta dorada</h2>" + _tabla(
            ["Caso", "Cláusula esperada", "Cláusulas citadas", "Cita", "Deducible"],
            filas,
            ["", "", "", "centro", "centro"],
        )
    return cuerpo


def contratos() -> str:
    return (
        "<p>Toda información que cruza una frontera del sistema —entrada del usuario, salida "
        "estructurada del modelo, escritura a la base— pasa por un modelo Pydantic. Dos contratos "
        "merecen explicación.</p>"
        "<h2>Autenticación</h2>"
        "<p><code>LoginRequest</code> valida el formato de los cuatro factores exigidos por el PRD "
        "§6.1 —póliza, RFC, CURP y últimos tres dígitos del celular— <em>antes</em> de tocar la "
        "base. La comparación de los cuatro ocurre en un solo método auditable, "
        "<code>Customer.matches</code>: la regla de acceso vive en un único lugar.</p>"
        "<h2>Siniestro: borrador contra expediente</h2>"
        "<p>Se distinguen dos tipos. El <strong>borrador</strong> (<code>IncidentDraft</code>) tiene "
        "todos los campos opcionales y se acumula turno a turno. El <strong>expediente</strong> "
        "(<code>ClaimReport</code>) los tiene todos obligatorios y es lo único que se persiste.</p>"
        "<p>Un campo que el modelo no logre extraer se queda en <code>null</code> y se vuelve a "
        "preguntar, en lugar de rellenarse con una suposición. Esa separación es la barrera que "
        "impide que una alucinación llegue a la base transaccional: promover un borrador incompleto "
        "lanza una excepción, y hay una prueba que lo verifica.</p>"
        + _callout(
            "Por qué importa en seguros",
            "<p>Un expediente de siniestro con una fecha inventada no es un error cosmético: es un "
            "dato que un ajustador usará para dictaminar. Preferimos preguntar de nuevo antes que "
            "registrar algo plausible pero falso.</p>",
        )
    )


def aritmetica() -> str:
    return (
        "<p>El deducible <strong>no</strong> lo calcula el modelo de lenguaje. "
        "<code>quote_deductible()</code> lo resuelve en Python a partir de la tabla de coberturas, y "
        "el resultado se inyecta en el prompt como <em>hecho calculado</em>; el modelo únicamente "
        "redacta. El prompt del Agente de Pólizas le prohíbe explícitamente recalcular o estimar "
        "importes.</p>"
        + _tabla(
            ["Paquete", "Cobertura", "Deducible"],
            [
                [
                    "Amplia",
                    "Daños materiales",
                    "5 % sobre valor comercial → $16 000 sobre $320 000",
                ],
                ["Amplia · Básica", "Robo total", "10 % sobre valor comercial → $32 000"],
                ["Amplia", "Rotura de cristales", "20 % del costo de reposición, mínimo $1 500"],
                ["Las tres", "Responsabilidad civil", "Sin deducible"],
            ],
        )
        + "<p>El mínimo contractual de cristales es el caso interesante: con un costo de reposición "
        "de $5 000, el 20 % son $1 000 y entra el mínimo de $1 500. Con $20 000, el porcentaje manda "
        "y son $4 000. Ambas ramas están cubiertas por prueba.</p>"
        + _callout(
            "El principio general",
            "<p>Un modelo de lenguaje es un mal lugar para hacer aritmética sobre dinero. Todo "
            "cálculo con consecuencia económica se hace en código determinista y verificable, y el "
            "modelo se limita a comunicarlo.</p>",
        )
    )


def memoria() -> str:
    """Cómo se gestionan las dos memorias del PRD §3.2."""
    return (
        "<p>El PRD distingue dos memorias y la implementación las mantiene separadas a propósito: "
        "viven en sitios distintos porque tienen ciclos de vida distintos.</p>"
        + _tabla(
            ["Memoria", "Dónde vive", "Qué contiene", "Cuándo cambia"],
            [
                [
                    "Corto plazo",
                    "Estado del grafo, en memoria del proceso",
                    "Asegurado autenticado, etapa del flujo FNOL, borrador del siniestro, "
                    "cláusulas del turno",
                    "En cada turno; se descarta al cerrar sesión",
                ],
                [
                    "Largo plazo",
                    "SQLite (PostgreSQL en GCP)",
                    "Siniestros previos con folio, tipo, fecha, lugar y deducible aplicado; "
                    "vehículos; historial conversacional",
                    "Sólo cuando se registra un expediente nuevo",
                ],
            ],
        )
        + "<h2>Cómo llega al modelo</h2>"
        "<p>El historial se carga una sola vez al iniciar sesión —no en cada turno: es memoria de "
        "largo plazo y no cambia a mitad de una conversación— y el Agente de Pólizas recibe un "
        "resumen de los <b>tres</b> expedientes más recientes en su contexto.</p>"
        "<p>El límite de tres no es arbitrario: el historial completo crecería sin cota y "
        "desplazaría del contexto a las cláusulas recuperadas, que son justamente lo que el agente "
        "necesita para responder. Tres bastan para reconocer una recurrencia.</p>"
        "<p>El prompt acota qué puede hacer con esa información: mencionar el folio de un siniestro "
        "previo del mismo tipo, y nada más. Tiene prohibido inferir que la prima subirá, que la "
        "cobertura se agotó o que hay penalización por recurrencia, porque nada de eso está en las "
        "cláusulas y sería exactamente el tipo de invención que más daño hace en seguros.</p>"
        + _callout(
            "Sin historial precargado no hay nada que demostrar",
            "<p>Los datos sintéticos incluyen siniestros previos para la mitad de la cartera. Son "
            "coherentes con lo contratado —un asegurado con sólo Responsabilidad Civil no puede "
            "tener un expediente de cristales— y su deducible se calcula con la misma función que "
            "usa el Agente FNOL en producción, no con un número escrito a mano: si cambia la tabla "
            "de coberturas, el historial cambia con ella.</p>",
        )
        + "<p>Un expediente recién creado pasa a ser memoria de largo plazo de inmediato: si el "
        "asegurado pregunta en el siguiente turno, el asistente ya lo conoce. La conversación "
        "<code>conv-01</code> del capítulo 4 muestra el ciclo completo.</p>"
    )


def observabilidad() -> str:
    return (
        "<p>Cada nodo del grafo se envuelve en un contexto que emite un evento JSONL con "
        "<code>run_id</code>, nodo, estado, duración y carga útil específica. Para el orquestador, "
        "esa carga incluye la ruta elegida, la confianza y la justificación textual.</p>"
        "<p>Se optó por trazado propio en lugar de LangSmith por dos razones: no requiere cuenta ni "
        "envía datos fuera del equipo —relevante cuando el dominio son datos de asegurados—, y el "
        "formato JSONL es directamente consultable durante una demostración.</p>"
        "<pre><code># Todas las decisiones de enrutamiento de una sesión\n"
        "jq -c 'select(.node==\"orchestrator\") | {run_id, route, reasoning}' data/traces.jsonl\n\n"
        "# Los turnos más lentos\n"
        "jq -s 'sort_by(-.duration_ms) | .[0:5] | .[] | {node, duration_ms}' data/traces.jsonl</code></pre>"
        "<p>La escritura de trazas nunca interrumpe la conversación: si el disco falla, se degrada "
        "la observabilidad y se registra una advertencia, pero el turno del asegurado continúa. "
        "También eso está cubierto por prueba.</p>"
        "<p>El panel lateral de la interfaz muestra las últimas decisiones de enrutamiento en vivo, "
        "que es el requisito del PRD §4.1 llevado a la pantalla: quien hace la demostración puede "
        "explicar <em>por qué</em> el orquestador eligió cada agente.</p>"
    )


def costos(data: ReportData) -> str:
    cuerpo = (
        "<p>El costo se calcula a partir de los tokens que reporta la API y la tarifa del modelo, "
        "no de una estimación a ojo. Tres decisiones lo mantienen bajo:</p>"
        "<ul>"
        "<li>El enrutamiento corre con <code>effort: low</code>. Es una clasificación, no un "
        "problema de razonamiento.</li>"
        "<li>La confirmación sí/no y el nodo de cortesía no consumen modelo.</li>"
        "<li>El contexto RAG se limita a las <code>top_k</code> cláusulas pertinentes, nunca al "
        "documento completo.</li>"
        "</ul>"
    )
    if data.hay_metricas:
        m = data.metricas
        cuerpo += _tabla(
            ["Concepto", "Valor"],
            [
                ["Tokens de entrada", f"{m.get('total_input_tokens', 0):,}"],
                ["Tokens de salida", f"{m.get('total_output_tokens', 0):,}"],
                ["Costo por sesión completa", f"${m.get('session_cost_usd', 0):.6f} USD"],
                ["Latencia promedio por turno", f"{m.get('avg_latency_ms', 0):.0f} ms"],
                ["Latencia p95 por turno", f"{m.get('p95_latency_ms', 0):.0f} ms"],
            ],
            ["", "num"],
        )
    cuerpo += (
        "<p>El techo de 10 USD que fija el PRD corresponde a la PoC completa —desarrollo, pruebas y "
        "demostración—, no a una sesión individual. El costo por sesión queda varios órdenes de "
        "magnitud por debajo de ese techo.</p>"
    )
    return cuerpo


def seguridad() -> str:
    return (
        "<h2>Identificadores sintéticos</h2>"
        "<p>El RFC y la CURP son datos personales regulados por la LFPDPPP en México. Los "
        "identificadores que genera la PoC respetan el <strong>formato</strong> oficial —para que la "
        "validación sea representativa— pero llevan un marcador que los hace inasignables a una "
        "persona real:</p>"
        "<ul>"
        "<li><strong>RFC</strong> — inicia siempre con <code>XXX</code>, por ejemplo "
        "<code>XXXJ860330FYB</code>.</li>"
        "<li><strong>CURP</strong> — inicia con <code>XXXX</code> y usa la entidad <code>NE</code>, "
        "por ejemplo <code>XXXX860330MNEYSTB7</code>.</li>"
        "</ul>"
        "<p><code>LoginRequest.is_synthetic()</code> verifica ese marcador y la interfaz rechaza el "
        "acceso si no está presente: la PoC no puede ingerir un identificador real por accidente, "
        "ni siquiera si alguien lo teclea a propósito durante una demostración.</p>"
        "<h2>Gestión de secretos</h2>"
        "<p>Ninguna credencial vive en el repositorio. La API key se lee de <code>.env</code>, que "
        "está excluido del control de versiones junto con las llaves privadas, los archivos de "
        "credenciales de nube, el estado de Terraform —que guarda los secretos en texto plano— y "
        "los datos de asegurados.</p>"
        + _callout(
            "El .gitignore se prueba como control de seguridad",
            "<p>Un secreto sólo se filtra una vez: después de un <code>push</code> queda en el "
            "historial público para siempre, aunque se borre en el commit siguiente. Por eso hay "
            "pruebas automatizadas que crean un repositorio desechable y le preguntan a git —no a "
            "una expresión regular propia— si cada ruta sensible quedaría fuera. Una prueba "
            "adicional escanea el árbol completo en busca de patrones de llaves.</p>",
        )
        + "<h2>Superficie de ataque considerada</h2>"
        + _tabla(
            ["Riesgo", "Mitigación implementada"],
            [
                [
                    "Escritura fuera del directorio de evidencia",
                    "Un nombre de archivo con <code>../</code> se reduce a su nombre base antes de "
                    "tocar el disco. Cubierto por prueba.",
                ],
                [
                    "Carga de archivos maliciosos o desmedidos",
                    "Lista blanca de tipos MIME y tope de 10 MB, validados antes de escribir.",
                ],
                [
                    "Registro de siniestros con datos incompletos",
                    "Adjuntar evidencia fuera de la etapa <code>awaiting_evidence</code> lanza una "
                    "excepción.",
                ],
                [
                    "Integridad referencial en la base",
                    "<code>PRAGMA foreign_keys</code> activo; un siniestro huérfano es rechazado por "
                    "el motor.",
                ],
            ],
        )
    )


def infraestructura() -> str:
    return (
        "<p>El código Terraform está escrito y validado con <code>terraform validate</code>. "
        "Conforme al PRD §8 no se ejecuta en esta fase: queda listo para provisionar.</p>"
        + _tabla(
            ["Componente local", "Equivalente en GCP", "Nota"],
            [
                ["Streamlit", "Cloud Run", "Escala a cero: sin tráfico, sin costo de cómputo."],
                [
                    "SQLite",
                    "Cloud SQL for PostgreSQL",
                    "<code>db-f1-micro</code>, IP privada, sin IP pública.",
                ],
                [
                    "<code>data/uploads/</code>",
                    "Cloud Storage",
                    "Acceso público bloqueado, versionado, ciclo a Nearline a los 90 días.",
                ],
                [
                    "<code>.env</code>",
                    "Secret Manager",
                    "La llave nunca vive en la imagen ni en el estado de Terraform.",
                ],
                [
                    "<code>data/index/</code>",
                    "Horneado en la imagen",
                    "El corpus es estático y pequeño; un servicio gestionado de búsqueda vectorial costaría más que todo lo demás junto.",
                ],
            ],
        )
        + "<h2>Decisiones de seguridad en la nube</h2>"
        "<ul>"
        "<li>Identidad de servicio dedicada con privilegio mínimo, no la cuenta por defecto del proyecto.</li>"
        "<li>Acceso público desactivado salvo que se pida explícitamente con una variable.</li>"
        "<li><code>max_instances</code> como control de costo real, no como parámetro de rendimiento.</li>"
        "<li>Imagen fijada por tag inmutable: nunca <code>latest</code>.</li>"
        "<li>Contenedor con usuario no privilegiado y compilación en dos etapas, sin toolchain en la imagen final.</li>"
        "</ul>"
    )


def limitaciones() -> str:
    return (
        "<h2>Fuera de alcance por diseño (PRD §8)</h2>"
        "<ul>"
        "<li><strong>Visión computacional.</strong> La evidencia se almacena y se registra su "
        "metadata; no se evalúa el daño en la imagen.</li>"
        "<li><strong>Gestión de identidades.</strong> El acceso es simulado contra la base "
        "sintética; no hay Auth0 ni Google IAM.</li>"
        "<li><strong>Otros ramos.</strong> Vida, hogar y gastos médicos quedan fuera.</li>"
        "<li><strong>Modelo local.</strong> Ollama está implementado como proveedor intercambiable "
        "y documentado como ruta de costo cero, condicionado a disponer de GPU con VRAM suficiente "
        "para invocación de herramientas estable.</li>"
        "</ul>"
        "<h2>Limitaciones de la implementación</h2>"
        "<p>Estas no vienen del alcance sino de decisiones concretas, y conviene conocerlas antes "
        "de extender el sistema:</p>"
        + _tabla(
            ["Limitación", "Cuándo se vuelve un problema", "Qué hacer entonces"],
            [
                [
                    f"El corpus tiene {len(CLAUSES)} cláusulas y usa búsqueda exhaustiva.",
                    "Con miles de cláusulas la latencia crece linealmente.",
                    "Migrar a un índice aproximado (HNSW) y medir la pérdida de recuperación.",
                ],
                [
                    "La cobertura aludida se detecta con señales léxicas.",
                    "Al añadir ramos o coberturas, las palabras clave se vuelven inmanejables.",
                    "Resolverlo también con salida estructurada, como el enrutamiento.",
                ],
                [
                    "La evaluación con el proveedor <code>stub</code> es una línea base.",
                    "Siempre: no mide al modelo real.",
                    "Correr <code>make eval</code> con credenciales de Anthropic antes de concluir nada.",
                ],
                [
                    "El historial se resume a los tres expedientes más recientes.",
                    "Con un asegurado de cartera antigua, un siniestro relevante de hace años "
                    "quedaría fuera del contexto.",
                    "Seleccionar por relevancia semántica —los del mismo tipo que la consulta— en "
                    "lugar de por recencia.",
                ],
                [
                    "El Agente FNOL no consulta el historial.",
                    "Al reportar un siniestro recurrente: no puede advertir que ya hay un "
                    "expediente abierto por el mismo hecho.",
                    "Inyectarle el mismo resumen que recibe el Agente de Pólizas y añadir una "
                    "regla de detección de duplicados.",
                ],
            ],
        )
        + "<h2>Reproducibilidad</h2>"
        "<pre><code>pip install -r requirements-dev.txt\n"
        "cp .env.example .env          # colocar ANTHROPIC_API_KEY\n"
        "make bootstrap                # datos sintéticos, historial e índice FAISS\n"
        "make eval                     # métricas y conversaciones de este reporte\n"
        "make report                   # regenera este PDF</code></pre>"
        "<p>Las versiones están fijadas en <code>requirements.txt</code> y la generación de datos "
        "sintéticos —cartera e historial de siniestros— es determinista: dos ejecuciones producen "
        "la misma base y las mismas credenciales. Las conversaciones del capítulo 4 se capturan "
        "contra una base sembrada de cero, así que no dependen del orden en que se corrieron las "
        "demás pruebas.</p>"
        '<p class="nota-pie">InsurAgent — Prueba de Concepto del ramo de automóviles. '
        "Autor: <b>Diego Carrillo Mondragón</b>. Documento generado automáticamente por "
        "<code>insuragent.reporting</code> a partir de la corrida de evaluación registrada en "
        "<code>data/evaluation_report.json</code>.</p>"
    )


# ---------------------------------------------------------------------------
# Conversaciones trazadas (PRD §2, entregable 2)
# ---------------------------------------------------------------------------

ETIQUETA_RUTA = {
    "policy": "Agente de Pólizas",
    "fnol": "Agente FNOL",
    "network": "Agente de Red",
    "smalltalk": "Cortesía",
}

ETIQUETA_ETAPA = {
    "idle": "conversación libre",
    "confirm_fnol": "esperando confirmación",
    "collecting": "recolectando datos",
    "awaiting_evidence": "esperando evidencia",
    "done": "expediente cerrado",
}


def _ficha_asegurado(asegurado: dict) -> str:
    """Contexto del asegurado, incluido su historial previo."""
    previos = asegurado.get("siniestros_previos") or []
    bloque_previos = (
        '<div class="previos">'
        + "<br>".join(
            f"◦ {escape(str(c['folio']))} · {escape(str(c['tipo']))} · {escape(str(c['fecha']))} · "
            f"{escape(str(c['lugar']))}"
            for c in previos
        )
        + "</div>"
        if previos
        else '<div class="previos">◦ Sin siniestros previos registrados.</div>'
    )
    return (
        '<div class="ficha-asegurado">'
        f"<b>Asegurado:</b> {escape(asegurado['nombre'])} &nbsp;·&nbsp; "
        f"<b>Póliza:</b> {escape(asegurado['poliza'])} &nbsp;·&nbsp; "
        f"<b>Paquete:</b> {escape(asegurado['paquete'])}<br>"
        f"<b>Vehículo:</b> {escape(asegurado['vehiculo'])} &nbsp;·&nbsp; "
        f"<b>Ciudad:</b> {escape(asegurado['ciudad'])}<br>"
        f"<b>Memoria de largo plazo ({len(previos)} expediente"
        f"{'s' if len(previos) != 1 else ''}):</b>"
        f"{bloque_previos}</div>"
    )


def _traza_turno(turno: dict) -> str:
    """Lo que el sistema hizo entre el mensaje y la respuesta."""
    lineas = [
        f"<b>Decisión del orquestador:</b> {escape(turno['razonamiento'])}",
    ]

    if turno.get("historial_usado"):
        lineas.append(
            f"<b>Memoria de largo plazo:</b> se inyectaron "
            f"<span class='destacado'>{turno['historial_usado']}</span> expediente(s) previos en el contexto."
        )

    if turno.get("deducible_mxn") is not None:
        lineas.append(
            f"<b>Deducible calculado en Python:</b> "
            f"<span class='destacado'>${turno['deducible_mxn']:,.2f} MXN</span> "
            "(no lo produjo el modelo)."
        )

    if turno.get("talleres"):
        lineas.append(f"<b>Talleres consultados:</b> {escape(', '.join(turno['talleres']))}")

    if turno.get("folio"):
        lineas.append(
            f"<b>Expediente creado:</b> <span class='destacado'>{escape(turno['folio'])}</span>"
        )

    if turno.get("nota"):
        lineas.append(escape(turno["nota"]))

    cuerpo = "<br>".join(lineas)

    recuperacion = turno.get("recuperacion") or []
    if recuperacion:
        filas = [
            [
                f"<code>{escape(item['clause_id'])}</code>",
                escape(item["title"]),
                escape(item["coverage_type"]),
                f"{item['score']:.3f}",
            ]
            for item in recuperacion
        ]
        cuerpo += "<br><b>Cláusulas recuperadas de FAISS:</b>" + _tabla(
            ["Cláusula", "Título", "Paquete", "Similitud"], filas, ["", "", "", "num"]
        )

    return f'<div class="traza">{cuerpo}</div>'


_NEGRITA = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_CODIGO = re.compile(r"`([^`]+?)`")
_VINETA = re.compile(r"^\s*[-*]\s+", re.MULTILINE)


def _texto_respuesta(texto: str) -> str:
    """Convierte la respuesta del modelo a HTML seguro.

    El modelo redacta en markdown ligero —negritas, viñetas, algún backtick— y
    escaparlo tal cual dejaría los asteriscos a la vista en el PDF. Se escapa
    primero (nada de lo que escriba el modelo puede inyectar HTML) y sólo después
    se reintroducen las tres marcas que sí usa.
    """
    salida = escape(texto)
    salida = _NEGRITA.sub(r"<b>\1</b>", salida)
    salida = _CODIGO.sub(r"<code>\1</code>", salida)
    salida = _VINETA.sub("• ", salida)
    return salida.replace("\n", "<br>")


def _turno(turno: dict) -> str:
    ruta = ETIQUETA_RUTA.get(turno["ruta"], turno["ruta"])
    etapa = ETIQUETA_ETAPA.get(turno["etapa"], turno["etapa"])
    cabecera = (
        f'<div class="turno-cabecera">Turno {turno["numero"]} &nbsp; '
        f'<span class="ruta">{escape(ruta)}</span> &nbsp; '
        f"confianza {turno['confianza']:.0%} &nbsp;·&nbsp; {escape(etapa)} &nbsp;·&nbsp; "
        f"{turno['latencia_ms']:,.0f} ms</div>"
    )
    usuario = (
        '<div class="burbuja usuario"><span class="quien">Asegurado</span>'
        f"{escape(turno['usuario'])}</div>"
    )
    agente = (
        '<div class="burbuja agente"><span class="quien">InsurAgent</span>'
        f"{_texto_respuesta(turno['respuesta'])}</div>"
    )
    return f'<div class="turno">{cabecera}{usuario}{_traza_turno(turno)}{agente}</div>'


def _conversacion(conv: dict) -> str:
    referencias = ", ".join(f"<code>{escape(c)}</code>" for c in conv.get("casos_dorados", []))
    turnos = "".join(_turno(t) for t in conv["turnos"])
    pie = ""
    if conv.get("evidencia"):
        pie = (
            '<p class="nota-pie">La evidencia quedó vinculada al expediente '
            f"<code>{escape(conv['evidencia'])}</code>: el archivo se guardó en disco y su metadata "
            "—nombre, ruta, tipo, tamaño y fecha— en la base transaccional.</p>"
        )
    return (
        '<div class="conversacion">'
        f"<h3>{escape(conv['transcript_id'])} — {escape(conv['titulo'])}</h3>"
        f"<p>{escape(conv['proposito'])}</p>"
        f"<p style='font-size:8.5pt;color:#5c6470'>Casos del set dorado que ejercita: {referencias}</p>"
        f"{_ficha_asegurado(conv['asegurado'])}"
        f"{turnos}{pie}</div>"
    )


def conversaciones(data: ReportData) -> str:
    """Transcripciones reales con la traza completa de cada turno."""
    intro = (
        "<p>Las tablas de los capítulos anteriores dicen <em>cuánto</em> acierta el sistema, pero no "
        "dejan ver <em>cómo</em> llega a una respuesta. Estas conversaciones se capturaron "
        "ejecutando la aplicación real: entre cada mensaje del asegurado y la respuesta del "
        "asistente se muestra lo que ocurrió en medio —la decisión de enrutamiento con su "
        "justificación, las cláusulas que FAISS recuperó con su similitud, el deducible calculado "
        "en Python y los expedientes previos inyectados en el contexto.</p>"
        "<p>Cada conversación indica qué casos del set dorado ejercita, para poder ir de una fila "
        "de aquellas tablas a la conversación que la produjo.</p>"
    )

    if not data.conversaciones:
        return intro + _callout(
            "Sin conversaciones capturadas",
            "<p>No se encontró <code>data/transcripts.json</code>. Ejecuta <code>make eval</code> "
            "—que las captura al terminar— y vuelve a generar el reporte.</p>",
            "alerta",
        )

    proveedor = (data.transcripciones or {}).get("proveedor", "—")
    modelo = (data.transcripciones or {}).get("modelo", "—")
    contexto = (
        f"<p style='font-size:8.5pt;color:#5c6470'>Capturadas con el proveedor "
        f"<code>{escape(proveedor)}</code> · modelo <code>{escape(modelo)}</code>.</p>"
    )
    return intro + contexto + "".join(_conversacion(c) for c in data.conversaciones)


# ---------------------------------------------------------------------------
# Acceso al servicio (PRD §2, entregable 1)
# ---------------------------------------------------------------------------


def acceso() -> str:
    """Cómo levantar el servicio y con qué credenciales entrar."""
    from insuragent.config import get_settings
    from insuragent.data.synthetic import generate_claim_history, generate_customers

    settings = get_settings()
    customers = generate_customers(settings.synthetic_customers, settings.synthetic_seed)
    historial = generate_claim_history(customers, settings.synthetic_seed)
    con_historial = {c.customer_id for c in historial}

    # Un asegurado por paquete, priorizando los que tienen historial previo:
    # así quien prueba puede ver la memoria de largo plazo en el primer intento.
    elegidos = []
    for paquete in ("amplia", "basica", "rc"):
        del_paquete = [c for c in customers if c.coverage_type == paquete]
        con_previos = [c for c in del_paquete if c.customer_id in con_historial]
        if elegido := (con_previos or del_paquete):
            elegidos.append(elegido[0])

    filas = [
        [
            escape(c.full_name),
            f"<code>{escape(c.policy_number)}</code>",
            f"<code>{escape(c.rfc)}</code>",
            f"<code>{escape(c.curp)}</code>",
            f"<code>{escape(c.phone_last3)}</code>",
            escape(c.coverage_type),
            "sí" if c.customer_id in con_historial else "no",
        ]
        for c in elegidos
    ]

    sugerencias = _tabla(
        ["Qué probar", "Qué escribir", "Qué debería pasar"],
        [
            [
                "Consulta de cobertura",
                "«¿Cuál es mi deducible por robo total?»",
                "Ruta <code>policy</code>; cita la cláusula del paquete contratado y el importe exacto.",
            ],
            [
                "Discriminación entre paquetes",
                "«¿Mi póliza cubre la rotura de cristales?»",
                "Con Amplia responde la cobertura; con Básica, la cláusula de exclusión.",
            ],
            [
                "Memoria de largo plazo",
                "«Otra vez se me estrelló el parabrisas»",
                "Con un asegurado que tiene historial, menciona el folio del siniestro anterior.",
            ],
            [
                "Flujo FNOL completo",
                "«Quiero reportar un choque» y seguir las preguntas",
                "Ruta <code>fnol</code>; pide los datos faltantes y al final la fotografía del daño.",
            ],
            [
                "Red de talleres",
                "«¿Dónde hay un taller cerca de Polanco?»",
                "Ruta <code>network</code>; lista talleres reales del catálogo, sin inventar sucursales.",
            ],
        ],
    )

    if settings.public_url:
        encabezado = "<h2>Servicio en línea</h2>" + _callout(
            "La aplicación está publicada y no requiere instalar nada",
            f'<p style="font-size:12pt"><b><a href="{escape(settings.public_url)}">'
            f"{escape(settings.public_url)}</a></b></p>"
            "<p>Basta abrir el enlace e ingresar con cualquiera de las credenciales "
            "sintéticas de la tabla siguiente. La primera visita del día puede tardar unos "
            "segundos: el servicio escala a cero y arranca bajo demanda.</p>",
        )
    else:
        encabezado = "<h2>Servicio en línea</h2>" + _callout(
            "Aún no hay una URL publicada",
            "<p>Cuando el servicio se despliegue, basta con definir "
            "<code>INSURAGENT_PUBLIC_URL</code> y regenerar este reporte para que el enlace "
            "aparezca aquí. Mientras tanto, abajo están las instrucciones para levantarlo en "
            "local.</p>",
            "aviso",
        )

    return (
        encabezado + "<h2>Levantar el servicio en local</h2>"
        "<pre><code>git clone &lt;repositorio&gt; &amp;&amp; cd Practica_agente_seguros\n"
        "pip install -r requirements-dev.txt\n"
        "cp .env.example .env          # colocar ANTHROPIC_API_KEY\n"
        "make bootstrap                # datos sintéticos + índice FAISS\n"
        "make app                      # levanta la interfaz</code></pre>"
        "<p>La aplicación queda en <b><code>http://localhost:8501</code></b>. Sin "
        "<code>ANTHROPIC_API_KEY</code> el sistema arranca igual, pero con el proveedor "
        "determinista: útil para recorrer la interfaz, no para juzgar la calidad de las "
        "respuestas.</p>"
        "<h2>Servicio desplegado en GCP</h2>"
        "<p>Al aplicar el Terraform, la URL del servicio se obtiene de la salida "
        "<code>service_url</code>. Por omisión el servicio exige autenticación de IAM; para una "
        "demostración abierta hay que aplicar con <code>allow_public_access = true</code>, algo "
        "que conviene revertir al terminar.</p>"
        "<pre><code>cd infra/terraform\n"
        'export TF_VAR_anthropic_api_key="sk-ant-..."\n'
        "terraform apply\n"
        "terraform output service_url</code></pre>"
        "<h2>Credenciales de acceso</h2>"
        + _callout(
            "Estas credenciales son sintéticas y pueden publicarse",
            "<p>Los identificadores respetan el formato oficial mexicano pero llevan el marcador "
            "reservado (<code>XXX</code> en RFC, <code>XXXX</code> + entidad <code>NE</code> en "
            "CURP) que los hace inasignables a una persona real. Se regeneran idénticas con "
            "<code>make seed</code>, que además las imprime en la terminal.</p>",
        )
        + '<div class="credenciales">'
        + _tabla(
            ["Asegurado", "Póliza", "RFC", "CURP", "Cel.", "Paquete", "Historial"],
            filas,
            ["", "", "", "", "centro", "centro", "centro"],
        )
        + "</div>"
        + "<p>El acceso exige los <b>cuatro</b> factores; fallar uno solo lo rechaza. Los tres "
        "asegurados tienen paquetes distintos a propósito: la misma pregunta debe producir "
        "respuestas distintas según lo contratado.</p>"
        "<h2>Qué probar</h2>"
        + sugerencias
        + "<p>El detalle del despliegue —incluidos Hugging Face Spaces y Cloud Run como "
        "alternativas— está en <code>DESPLIEGUE.md</code> del repositorio.</p>"
    )


def documento(data: ReportData) -> str:
    """Ensambla el reporte completo."""
    return "".join(
        [
            portada(data),
            contenidos(),
            _capitulo("Resumen y métricas de aceptación", resumen(data)),
            _capitulo("Arquitectura agéntica", arquitectura(data)),
            _capitulo("Recuperación aumentada (RAG)", rag(data)),
            _capitulo("Conversaciones trazadas", conversaciones(data)),
            _capitulo("Contratos de datos y validación", contratos()),
            _capitulo("Aritmética fuera del modelo", aritmetica()),
            _capitulo("Gestión de memoria", memoria()),
            _capitulo("Observabilidad", observabilidad()),
            _capitulo("Latencia y costo", costos(data)),
            _capitulo("Seguridad y datos personales", seguridad()),
            _capitulo("Infraestructura en GCP", infraestructura()),
            _capitulo("Acceso al servicio y credenciales de prueba", acceso()),
            _capitulo("Limitaciones y siguientes pasos", limitaciones()),
        ]
    )
