# InsurAgent — PoC (Ramo Automóviles)

**Autor:** Diego Carrillo Mondragón

Asistente agéntico conversacional para el sector asegurador. Interpreta las
condiciones generales de una póliza de auto, cotiza deducibles, levanta el
reporte de un siniestro (FNOL) y localiza talleres en convenio — con datos
100 % sintéticos, infraestructura local y una arquitectura *cloud-ready*.

Implementación del [PRD](PRD_InsurAgent_v2.md).

---

## Arquitectura

```
                        ┌─────────────────────┐
   Streamlit  ────────► │  InsurAgentSession  │ ◄──── autenticación (Pydantic)
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  Grafo (LangGraph)  │
                        └──────────┬──────────┘
                                   │
                          ┌────────▼────────┐
                          │  Orquestador    │  structured output → RouteDecision
                          └───┬───┬───┬───┬─┘
              ┌───────────────┘   │   │   └───────────────┐
              ▼                   ▼   ▼                   ▼
     ┌────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐
     │ Agente Pólizas │   │  Agente FNOL │   │  Agente Red  │   │ Smalltalk │
     │  RAG + FAISS   │   │  Pydantic    │   │  catálogo    │   │  guion    │
     └───────┬────────┘   └──────┬───────┘   └──────────────┘   └───────────┘
             │                   │
             ▼                   ▼
      índice FAISS         SQLite + disco
   (3 variantes de        (siniestros, evidencia,
    condiciones)           memoria de largo plazo)
```

**Decisiones de diseño que vale la pena conocer antes de leer el código:**

| Decisión | Por qué |
|---|---|
| El deducible se calcula en Python, no en el LLM | Un modelo de lenguaje es un mal lugar para hacer aritmética sobre dinero. El importe se inyecta en el prompt como *hecho calculado* y el modelo sólo redacta. |
| La confirmación «¿deseas reportarlo?» se resuelve con reglas | Un sí/no no justifica una llamada al modelo: ni su latencia, ni su costo, ni su varianza. |
| El filtro por paquete se aplica **después** de la búsqueda ANN | Filtrar antes volvería trivial el retrieval. Recuperar sobre el corpus completo obliga a discriminar entre cláusulas casi idénticas, que es la prueba que pide el PRD §4.2. |
| Los datos sintéticos incluyen siniestros previos | Sin historial precargado la memoria de largo plazo del PRD §3.2 no se puede demostrar: el asistente no tendría nada que recordar. El Agente de Pólizas recibe ese historial y reconoce un siniestro recurrente citando su folio. |
| Las transcripciones corren contra una base propia | Si compartieran base con la evaluación, el historial de un asegurado incluiría expedientes que la propia corrida acaba de crear, y el ejemplo de memoria larga mostraría siniestros que el lector no puede rastrear. |
| Un borrador (`IncidentDraft`) distinto del expediente (`ClaimReport`) | Lo que el modelo extrae es un borrador con campos opcionales; sólo un borrador completo puede promoverse a expediente. Una alucinación no alcanza la base transaccional. |
| Tres proveedores LLM intercambiables | Claude API es la ruta principal; Ollama es la alternativa de costo cero; el stub determinista permite correr toda la suite sin red ni gasto. |
| El reporte se genera con WeasyPrint, no con Quarto | Quarto exigía un CLI externo más LaTeX o Chromium para llegar al PDF. Con HTML+CSS de impresión, `make report` corre en el mismo entorno que `make test`. |
| El proveedor se verifica al arrancar (`healthcheck`) | El SDK de Anthropic construye el cliente sin validar credenciales: sin esta comprobación el fallo aparecería a mitad de la primera conversación. Con ella, se degrada de forma ordenada y **ruidosa**. |

---

## Publicar la aplicación

Para que alguien use la app **sin instalar nada**, el proyecto ya trae el punto
de entrada (`streamlit_app.py`), la auto-inicialización del disco y un
`requirements.txt` ligero. Los pasos concretos están en
[DESPLIEGUE.md](DESPLIEGUE.md).

El manifiesto de la aplicación **no incluye PyTorch** a propósito: el modelo
denso lleva el proceso a 2 158 MB de RSS y un plan gratuito da ~1 GB. La
recuperación usa un diccionario del dominio que alcanza la misma precisión
medida —15/15— con 214 MB y arranque de 0.3 s.

## Puesta en marcha

Requiere Python 3.12.

```bash
# 1. Dependencias (dev = app + embeddings densos + reporte + pruebas)
pip install -r requirements-dev.txt
#    Sólo la app:            pip install -r requirements.txt
#    Sólo generar el PDF:    pip install -r requirements-report.txt

# 2. Configuración
cp .env.example .env
#    Editar .env y colocar ANTHROPIC_API_KEY.
#    Sin ella todo sigue funcionando, pero con el stub determinista.

# 3. Datos sintéticos + índice FAISS
make bootstrap        # equivale a: make seed && make index

# 4. Levantar la interfaz
make app
```

`make seed` imprime en la terminal las credenciales de tres asegurados de prueba
(póliza, RFC, CURP y últimos 3 dígitos del celular) para iniciar sesión.

### Comandos

```
make help        # lista todos los objetivos
make seed        # datos sintéticos → SQLite + corpus en data/raw/
make index       # vectoriza las condiciones generales en FAISS
make app         # interfaz Streamlit
make eval        # set dorado, métricas del PRD §5 y captura de conversaciones
make test        # suite de pruebas (198 casos, sin red ni costo)
make lint / fmt  # ruff
make report      # reporte técnico en PDF → docs/report.pdf
```

Todos los objetivos, `make report` incluido, corren con el entorno de Python del
proyecto: no hace falta ningún CLI externo.

## Estado de la verificación

| Comprobación | Resultado |
|---|---|
| `make test` | 198 pruebas, incluidas 5 de la interfaz con `AppTest`, 14 de importación en intérprete limpio, 30 que verifican el `.gitignore` con git real, 12 de memoria de largo plazo, 13 de captura de conversaciones y 9 de preparación para despliegue |
| `make lint` | `ruff check` y `ruff format --check` limpios sobre 55 archivos |
| `make eval` | **Claude Opus 5**: 15/15 RAG · 15/15 deducible · 16/16 enrutamiento · 3/3 FNOL · latencia media 4.5 s (p95 9.9 s) · **$0.032 USD por sesión completa** |
| `terraform validate` | Configuración válida |
| Interfaz | Arranca y responde; el flujo de login se ejercita en las pruebas |
| `make report` | PDF de 23 páginas generado y validado, con conversaciones reales trazadas |

---

## Configuración

Todo se controla por `.env` (prefijo `INSURAGENT_`). Los parámetros que más se
tocan:

| Variable | Valores | Notas |
|---|---|---|
| `INSURAGENT_LLM_PROVIDER` | `anthropic` · `ollama` · `stub` | Ruta principal, alternativa local, doble de pruebas. |
| `ANTHROPIC_API_KEY` | — | Si falta, el sistema **degrada al stub con una advertencia** en vez de reventar: la demo siempre levanta. La degradación se anuncia en el log, en la barra lateral y en el reporte de evaluación, para que nunca se confunda con una medición del modelo. |
| `INSURAGENT_ANTHROPIC_MODEL` | `claude-opus-5` | No se envía `temperature`: los modelos Opus 5 / Sonnet 5 rechazan parámetros de sampling con HTTP 400. El determinismo viene de los *structured outputs*. |
| `INSURAGENT_EFFORT` | `low` … `max` | Presupuesto de razonamiento. `low` basta para enrutar y mantiene el costo por sesión bajo. |
| `INSURAGENT_EMBEDDING_BACKEND` | `sentence-transformers` · `hash` | Ambos miden 15/15 en recuperación. `hash` usa un diccionario del dominio, no descarga nada y ocupa 214 MB frente a 2 158 MB: es el que corre en el despliegue. |
| `INSURAGENT_PUBLIC_URL` | — | URL del servicio desplegado. Definida, el reporte PDF la publica junto con las credenciales de prueba. |

---

## Estructura

```
src/insuragent/
├── config.py            configuración central (pydantic-settings)
├── observability.py     trazado JSONL por nodo del grafo (PRD §4.1)
├── session.py           fachada: autenticación + grafo + memoria
├── prompt_markers.py    constantes compartidas, sin dependencias
├── schemas/             contratos Pydantic (auth, policy, fnol, routing)
├── data/                corpus sintético y generador de asegurados
├── db/                  SQLite: esquema portable a PostgreSQL + repositorio
├── rag/                 embeddings intercambiables + índice FAISS
├── llm/                 proveedores: anthropic · ollama · stub
├── agents/              orquestador, pólizas, FNOL, red + herramientas y prompts
├── graph/               estado y grafo LangGraph
├── evaluation/          set dorado, métricas del PRD §5 y captura de conversaciones
├── reporting/           generador del reporte técnico en PDF
├── bootstrap.py         auto-inicialización para hosting (siembra + índice)
└── ui/                  interfaz Streamlit

tests/                   198 pruebas: contratos, RAG, grafo, FNOL, UI, memoria, .gitignore
Dockerfile               imagen para Cloud Run (faiss-cpu, usuario no-root)

infra/terraform/         infraestructura GCP (validada con `terraform validate`)
docs/report.pdf          reporte técnico (entregable 2 del PRD, sí se versiona)
DESPLIEGUE.md            guía para publicar la app en una URL
streamlit_app.py         punto de entrada para hosting gestionado
```

---

## Evaluación

`make eval` corre el set dorado y escribe `data/evaluation_report.json` con el
desglose por caso. Cubre las cinco métricas del PRD §5:

| Métrica | Casos |
|---|---|
| Precisión de recuperación RAG | 15 preguntas doradas sobre las tres variantes |
| Precisión del deducible | mismos 15 casos, verificando el importe |
| Precisión de enrutamiento | 16 consultas (tabla PRD §3.1 + variantes adversariales) |
| Tasa de éxito end-to-end FNOL | 3 guiones completos, incluido uno que **no** debe abrir expediente |
| Latencia y costo | promedio y p95 por turno; costo real de la sesión completa |

Al terminar, `make eval` captura además **tres conversaciones de ejemplo** con su
traza completa —decisión de enrutamiento, cláusulas recuperadas con su score,
deducible calculado y expedientes previos inyectados— en `data/transcripts.json`.
El reporte PDF las renderiza turno a turno para que la trazabilidad sea legible
por un humano y no sólo por `jq`.

**Resultados medidos con Claude Opus 5** (no con el stub):

| Métrica | Resultado | Umbral |
|---|---|---|
| Precisión de recuperación RAG | 15/15 · 100 % | ≥ 80 % |
| Precisión del deducible | 15/15 · 100 % | 100 % |
| Precisión de enrutamiento | 16/16 · 100 % | ≥ 85 % |
| Éxito end-to-end FNOL | 3/3 · 100 % | 100 % |
| Latencia media por turno | 4 535 ms (p95 9 885 ms) | < 5 000 ms |
| Costo por sesión completa | $0.032103 USD | < $0.10 USD |

> **Lectura honesta:** si la corrida usa el proveedor `stub`, la precisión de
> enrutamiento mide reglas deterministas escritas conociendo estos mismos casos.
> Eso es una **línea base**, no una medición del modelo — y tanto la salida por
> terminal como el reporte PDF lo marcan de forma explícita cuando ocurre.

---

## Datos sintéticos y protección de datos

RFC y CURP son datos personales regulados por la LFPDPPP en México. Todos los
identificadores generados respetan el **formato** oficial pero llevan un
marcador que los hace inasignables a una persona real:

* **RFC** → inicia con `XXX` (p. ej. `XXXJ860330FYB`)
* **CURP** → inicia con `XXXX` y usa la entidad `NE` (p. ej. `XXXX860330MNEYSTB7`)

`LoginRequest.is_synthetic()` verifica ese marcador, y la interfaz rechaza el
acceso si no está presente. La PoC no puede ingerir un identificador real por
accidente.

Las condiciones generales, los importes y el catálogo de talleres también son
ficticios y no corresponden a ningún producto comercial.

---

## Memoria de largo plazo

`make seed` genera, además de la cartera, **siniestros previos** para la mitad de
los asegurados. Sin ese historial la memoria de largo plazo no se puede
demostrar. El Agente de Pólizas recibe hasta tres expedientes anteriores en su
contexto y, ante un siniestro recurrente, lo menciona con su folio:

> «Otra vez se me estrelló el parabrisas, ¿cuánto pago de deducible?»
> → el asistente cita la cláusula, el deducible calculado en Python y el folio
> del siniestro de cristales anterior.

Se resumen tres expedientes, no todos: el historial completo crecería sin límite
y desplazaría del contexto a las cláusulas recuperadas, que son lo que el agente
necesita para responder.

## Seguridad y secretos

Nada sensible entra al repositorio. El `.gitignore` excluye credenciales
(`.env`, `*.pem`, `*.key`, `service-account*.json`), el estado de Terraform —que
guarda los secretos en texto plano—, la base de asegurados, las trazas
conversacionales y la evidencia de siniestros.

Eso no se deja a la buena fe: `tests/test_gitignore.py` crea un repositorio
desechable con el `.gitignore` real y le pregunta **a git** si cada ruta
sensible quedaría fuera, además de escanear el árbol en busca de patrones de
llaves. Un secreto sólo se filtra una vez —tras un `push` queda en el historial
para siempre—, así que es un control que merece prueba automatizada.

Si tu API key está ligada a una identidad, la API exige además declarar el
workspace: añade `ANTHROPIC_WORKSPACE_ID=wrkspc_...` a tu `.env` (consola de
Anthropic → Settings → Workspaces). Sin él la API responde 400 y el sistema
degrada al stub con el mensaje explicándolo.

El `healthcheck` valida credenciales con una petición gratuita, pero no puede
saber si la cuenta tiene saldo —no se gasta dinero para averiguar si se puede
gastar dinero—. Por eso `make eval` hace antes una petición mínima y aborta con
un mensaje accionable si la cuenta no puede generar.

## Alcance

Fuera del alcance de esta versión, conforme al PRD §8: visión computacional
sobre la evidencia (se simula el almacenamiento), IAM real (el login es
simulado), otros ramos (vida, hogar, gastos médicos) y la ejecución del
Terraform (queda documentado y validado, listo para provisionar).
