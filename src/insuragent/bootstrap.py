"""Auto-inicialización para entornos gestionados.

En local, `make bootstrap` siembra la base y construye el índice antes de
levantar la aplicación. En un hosting gestionado —Streamlit Community Cloud,
Hugging Face Spaces, Cloud Run— nadie ejecuta comandos: el proceso arranca y
tiene que encontrarse todo listo, o prepararlo él mismo en el primer arranque.

Esta función es idempotente y barata cuando ya está todo: comprueba la
existencia de los artefactos antes de generarlos.
"""

from __future__ import annotations

import logging

from insuragent.config import Settings, get_settings

_LOGGER = logging.getLogger(__name__)


def ensure_ready(settings: Settings | None = None) -> dict[str, str]:
    """Garantiza que existan la base sembrada y el índice FAISS.

    Devuelve un resumen de qué se encontró y qué hubo que crear, para poder
    mostrarlo en el arranque y saber si un despliegue está reutilizando el disco
    o partiendo de cero.
    """
    settings = settings or get_settings()
    settings.ensure_dirs()
    estado: dict[str, str] = {}

    from insuragent.data.corpus import CoverageType, render_markdown
    from insuragent.data.synthetic import generate_claim_history, generate_customers
    from insuragent.db.repository import Repository

    # -- corpus legible ------------------------------------------------------
    for coverage_type in CoverageType:
        destino = settings.corpus_dir / f"condiciones_generales_{coverage_type.value}.md"
        if not destino.exists():
            destino.write_text(render_markdown(coverage_type), encoding="utf-8")
    estado["corpus"] = "listo"

    # -- base transaccional --------------------------------------------------
    repository = Repository(settings.db_path)
    repository.initialize()
    if repository.list_customers():
        estado["base"] = "existente"
    else:
        _LOGGER.info("Base vacía: sembrando cartera sintética e historial.")
        customers = generate_customers(settings.synthetic_customers, settings.synthetic_seed)
        for customer in customers:
            repository.upsert_customer(customer)
        for claim in generate_claim_history(customers, settings.synthetic_seed):
            repository.save_claim(claim)
        estado["base"] = f"sembrada ({len(customers)} asegurados)"

    # -- índice vectorial ----------------------------------------------------
    from insuragent.rag.index import INDEX_FILENAME, ClauseIndex

    if (settings.index_dir / INDEX_FILENAME).exists():
        estado["indice"] = "existente"
    else:
        _LOGGER.info("Sin índice FAISS: construyéndolo en el arranque.")
        indice = ClauseIndex.build(settings=settings)
        indice.save(settings.index_dir)
        estado["indice"] = f"construido ({indice.size} cláusulas)"

    return estado
