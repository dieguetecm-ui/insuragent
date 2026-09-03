"""Marcadores de prompt compartidos.

Módulo deliberadamente sin dependencias internas. Tanto `agents.prompts` (que
los escribe) como `llm.stub_provider` (que los lee) necesitan estas constantes;
si vivieran en cualquiera de los dos, `insuragent.llm` e `insuragent.agents`
quedarían importándose mutuamente.
"""

from __future__ import annotations

USER_MESSAGE_MARKERS: tuple[str, ...] = (
    "Mensaje del asegurado:",
    "Último mensaje del asegurado:",
    "Pregunta del asegurado:",
)
"""Delimitadores con los que los agentes marcan el texto literal del asegurado
dentro del prompt, para poder distinguirlo del contexto que lo rodea."""
