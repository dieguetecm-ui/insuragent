# Product Requirements Document (PRD)
## Proyecto: InsurAgent (PoC – Ramo Automóviles)

**Autor:** Diego Carrillo Mondragón
**Fecha:** Septiembre 2026
**Estado:** Listo para Desarrollo
**Objetivo del Documento:** Definir la arquitectura, componentes y plan de ejecución para la Prueba de Concepto (PoC) del asistente agéntico del sector asegurador.

---

## 1. Resumen Ejecutivo

**InsurAgent** es un sistema agéntico conversacional diseñado para el sector asegurador. Su propósito es interpretar normativas complejas de pólizas y asistir a los asegurados de manera personalizada, aislando estrictamente la información confidencial. Esta PoC demostrará la viabilidad del sistema enfocándose exclusivamente en el **ramo de seguros de automóviles**, utilizando infraestructura 100% local con datos sintéticos, pero con una arquitectura *cloud-ready* para un despliegue futuro en Google Cloud Platform (GCP) vía Terraform, manteniendo costos operativos por debajo de los $10 USD.

---

## 2. Entregables de la PoC

1. **URL del Servicio Activo:** Interfaz funcional (Streamlit/Gradio) desplegada localmente o en el Free Tier de GCP.
2. **Documentación técnica:** Reporte en **PDF** que detalla el razonamiento, la arquitectura agéntica, las métricas de evaluación obtenidas, transcripciones de conversaciones reales con su traza de enrutamiento y recuperación, las instrucciones de acceso al servicio para probarlo, y el esquema de Terraform para la futura infraestructura en la nube.

   El reporte se genera **desde el propio proyecto** (`make report`), con las mismas dependencias de Python que ejecutan la aplicación: HTML con CSS de impresión renderizado a PDF. Se descartó Quarto porque obligaba a instalar un CLI externo más una cadena LaTeX o un navegador headless sólo para producir el PDF, de modo que el entregable no podía generarse en el mismo entorno que corre y prueba el sistema. Las cifras del reporte se leen del artefacto de evaluación, no se transcriben a mano: el documento no puede quedar desfasado respecto de la última corrida.

---

## 3. Arquitectura del Sistema Agéntico

El sistema se compone de un orquestador central y agentes especializados, comunicados mediante un grafo de estados (LangGraph).

* **Agente Orquestador (Enrutador):** Analiza la intención del usuario y decide si la consulta debe dirigirse a revisión de póliza (RAG), reporte de siniestro (FNOL), o búsqueda en red.
* **Agente de Pólizas (RAG):** Conectado a una base vectorial. Recupera cláusulas exactas, condiciones generales y calcula deducibles.
* **Agente FNOL (First Notice of Loss):** Toma control cuando hay un siniestro. Recolecta datos del incidente, solicita carga de evidencia (fotos) y guarda la metadata.
* **Agente de Red:** Consulta ubicaciones de talleres con convenio según la ubicación del incidente.

### 3.1. Reglas de Enrutamiento del Orquestador

Para que el nodo condicional del grafo no quede indefinido, se documentan ejemplos de intención → ruta esperada, que sirven además como criterio de aceptación del componente:

| Consulta de ejemplo | Ruta esperada |
|---|---|
| "¿Qué cubre mi póliza de RC?" | Agente de Pólizas (RAG) |
| "Se me rompió el cristal ayer" | Agente de Pólizas → confirmación → Agente FNOL |
| "¿Cuál es mi deducible por robo total?" | Agente de Pólizas (RAG) |
| "¿Dónde hay un taller cerca de Polanco?" | Agente de Red |
| "Quiero reportar un choque" | Agente FNOL directo |

La clasificación puede resolverse con function-calling estructurado sobre el LLM elegido (ver 4.2), sin necesidad de un clasificador adicional para el alcance de la PoC.

### 3.2. Gestión de Memoria

* **Corto Plazo:** Mantiene el contexto de la sesión actual (ID de cliente, estado del reporte paso a paso).
* **Largo Plazo:** Historial persistente en base de datos transaccional (siniestros pasados, deducibles contratados, vehículos registrados). Los datos sintéticos incluyen **siniestros previos** para una parte de la cartera: sin historial precargado la memoria de largo plazo no se puede demostrar, porque el asistente no tendría nada que recordar. El Agente de Pólizas recibe ese historial en su contexto y debe reconocer un siniestro recurrente citando su folio.

---

## 4. Stack Tecnológico y Controles de Calidad

### 4.1. Entorno y Orquestación

* **Lenguaje y Entorno:** Python 3.12 (entornos virtuales aislados), optimizado para desarrollo local en VS Code.
* **Framework Agéntico:** LangGraph (para control estricto del estado y los flujos entre agentes).
* **Frontend:** Streamlit o Gradio.
* **Observabilidad:** Trazado de cada nodo del grafo (LangSmith o logging estructurado propio) — indispensable para depurar por qué el Orquestador enrutó una consulta de cierta forma, dado que es un sistema multiagente.

### 4.2. Modelos y Datos

* **Modelos de Lenguaje (LLMs):**
  * *Principal (desarrollo y demo):* API de un modelo con soporte robusto de tool-calling (Claude API o Gemini/Vertex AI free tier). Se usa desde el inicio, no solo para la comparativa final, porque el flujo agéntico (Orquestador y FNOL) depende de invocación de herramientas confiable.
  * *Local (opcional / roadmap):* Ollama queda documentado como alternativa de costo cero solo si se dispone de GPU con VRAM suficiente para tool-calling estable; no se usa como ruta principal en esta PoC para evitar bloquear el desarrollo por limitaciones de hardware.
* **Base de Datos Vectorial (RAG):** **FAISS**. Se indexan **al menos 2–3 variantes de condiciones generales** (ej. cobertura básica, amplia, y responsabilidad civil) con cláusulas parcialmente traslapadas, para que el sistema de recuperación tenga que discriminar entre condiciones similares y la prueba sea representativa (un solo documento no estresa el retrieval de forma realista).
* **Base de Datos Transaccional (Memoria/Auth):** SQLite para la PoC local, emulando la estructura que tendrá PostgreSQL en GCP.

### 4.3. Calidad y Seguridad (Data Contracts)

* **Pydantic:** Obligatorio para validar esquemas de datos entrantes. Toda la información de autenticación (RFC, CURP, Póliza) y la metadata del agente FNOL debe pasar por contratos estrictos para evitar alucinaciones y registros inválidos.
* **Datos sintéticos:** Los identificadores simulados (RFC, CURP, número de póliza) deben generarse con formato válido pero claramente no correspondiente a personas reales, dado que RFC/CURP son datos regulados bajo la LFPDPPP en México. Esto evita ambigüedad si la PoC se comparte como demo o portafolio.

---

## 5. Métricas de Éxito / Criterios de Aceptación

La PoC se considera exitosa si cumple, sobre un set de prueba definido (mínimo 10–15 preguntas doradas):

* **Precisión de recuperación RAG:** porcentaje de preguntas donde el agente cita la cláusula/deducible correcto.
* **Precisión de enrutamiento:** porcentaje de consultas de prueba (tabla 3.1 y variantes) dirigidas al agente correcto.
* **Latencia promedio por turno** de conversación.
* **Costo real medido** por sesión completa (autenticación + consulta + FNOL), no solo el techo de $10 USD.
* **Tasa de éxito end-to-end** del flujo FNOL completo (desde intención hasta metadata guardada).

---

## 6. Flujo de Trabajo del Usuario (User Journey)

1. **Autenticación Simulada:** El cliente ingresa su Número de Póliza, RFC, CURP y últimos 3 dígitos del celular. El sistema valida vía Pydantic contra la base de clientes sintéticos (SQLite).
2. **Consulta:** El usuario pregunta sobre un siniestro (ej. *"Ayer se rompió el cristal de mi auto..."*).
3. **Evaluación de Póliza:** El Orquestador delega al *Agente de Pólizas*. Mediante RAG (FAISS), busca las cláusulas. Responde con la cobertura y el deducible aplicable.
4. **Confirmación:** El agente pregunta si desea reportar el siniestro. Si es negativo, cierra ofreciendo más ayuda.
5. **Registro y FNOL:** Si el cliente acepta, el *Agente FNOL* toma el control:
   * Solicita detalles del evento.
   * Solicita la subida de una imagen del daño.
   * *Acción PoC:* El sistema guarda el archivo de imagen en el disco local y registra la metadata (fecha, ruta, asegurado) en la memoria transaccional.

---

## 7. Plan de Ejecución (por Fases)

Las fases están ordenadas por dependencia técnica, no por tiempo fijo — cada una avanza en cuanto la anterior está lista.

**Fase 1 — Datos y validación**
Generación de datos sintéticos (clientes, pólizas de auto, 2–3 variantes de condiciones generales). Esquemas Pydantic para login y clientes. Entorno Python 3.12 configurado.

**Fase 2 — RAG**
Vectorización en FAISS de las variantes de póliza. Definición del set de preguntas doradas. Pruebas de recuperación contra el LLM principal (API).

**Fase 3 — Orquestación agéntica**
Grafo LangGraph: Orquestador con reglas de enrutamiento explícitas (tabla 3.1), Agente de Pólizas, Agente FNOL. Observabilidad activada.

**Fase 4 — Interfaz y flujo FNOL**
Streamlit/Gradio. Carga de archivos de evidencia (guardado local + metadata en SQLite).

**Fase 5 — Pruebas end-to-end y documentación**
Medición de las métricas de la sección 5. Captura de conversaciones de ejemplo con su traza completa (enrutamiento, cláusulas recuperadas y deducible calculado). Reporte técnico en PDF generado por el propio proyecto, con arquitectura, reasoning, resultados de evaluación, instrucciones de acceso al servicio y el esquema Terraform documentado.

---

## 8. Limitaciones de la PoC y Roadmap (Versión 2.0)

Esta PoC excluye deliberadamente características que se implementarán en fases futuras:

* **Visión Computacional:** La inspección multimodal (evaluación de daños en imágenes) no se ejecuta en la PoC; se simula el almacenamiento del archivo.
* **Gestión de Identidades (IAM):** El login es simulado localmente y no está conectado a Auth0 o Google IAM.
* **Otros Ramos:** Gastos Médicos, Hogar y Vida quedan fuera del alcance actual.
* **Despliegue Terraform:** El código de infraestructura como código estará documentado en el reporte, listo para ejecutarse al provisionar la cuenta de GCP.
* **LLM local con tool-calling:** Migrar a Ollama en local queda condicionado a contar con GPU de VRAM suficiente; se documenta como opción de costo cero para una fase posterior, no como bloqueador de esta PoC.
