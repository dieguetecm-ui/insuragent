"""Índice vectorial FAISS sobre las cláusulas de las condiciones generales.

Decisiones de diseño:

* ``IndexFlatIP`` sobre vectores normalizados L2 ⇒ el score es coseno exacto.
  Con ~20 cláusulas, un índice aproximado (IVF/HNSW) sólo añadiría error e
  hiperparámetros sin ganancia de latencia medible.
* Cada cláusula es un chunk. Las cláusulas de una póliza ya son la unidad
  semántica natural del documento: partirlas por ventana fija cortaría el
  deducible de su cobertura.
* El filtro por variante de póliza se aplica **después** de la búsqueda ANN
  (sobre-recuperando `top_k * OVERSAMPLE`), no antes. Así el recuperador tiene
  que discriminar de verdad entre cláusulas casi idénticas, que es la prueba
  que pide el PRD §4.2, y la métrica de recuperación es honesta.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss

from insuragent.config import Settings, get_settings
from insuragent.data.corpus import CLAUSES
from insuragent.rag.embeddings import Embedder, get_embedder
from insuragent.schemas.policy import Clause, CoverageType, RetrievedClause

_LOGGER = logging.getLogger(__name__)

INDEX_FILENAME = "clauses.faiss"
METADATA_FILENAME = "clauses.json"
OVERSAMPLE = 5


class ClauseIndex:
    """Envoltura de FAISS con la metadata de las cláusulas."""

    def __init__(self, index: faiss.Index, clauses: list[Clause], embedder: Embedder) -> None:
        self._index = index
        self._clauses = clauses
        self._embedder = embedder

    # -- construcción y persistencia ---------------------------------------

    @staticmethod
    def _embed_text(clause: Clause) -> str:
        """Texto que se vectoriza.

        Se antepone el paquete y el título para que la variante forme parte de
        la señal: sin eso, las tres versiones de la cláusula de RC producen
        vectores casi idénticos y el recuperador elige al azar.
        """
        return f"Paquete {clause.coverage_type.value}. {clause.title}. {clause.text}"

    @classmethod
    def build(
        cls,
        clauses: list[Clause] | None = None,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
    ) -> ClauseIndex:
        settings = settings or get_settings()
        clauses = list(clauses if clauses is not None else CLAUSES)
        embedder = embedder or get_embedder(settings)

        vectors = embedder.encode([cls._embed_text(c) for c in clauses])
        index = faiss.IndexFlatIP(embedder.dimension)
        index.add(vectors)
        _LOGGER.info(
            "Índice construido: %d cláusulas, dim=%d, backend=%s",
            len(clauses),
            embedder.dimension,
            embedder.name,
        )
        return cls(index, clauses, embedder)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / INDEX_FILENAME))
        payload = {
            "embedder": self._embedder.name,
            "dimension": self._embedder.dimension,
            "clauses": [c.model_dump(mode="json") for c in self._clauses],
        }
        (directory / METADATA_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path | None = None, settings: Settings | None = None) -> ClauseIndex:
        """Carga el índice del disco; lo reconstruye si no existe o quedó obsoleto."""
        settings = settings or get_settings()
        directory = directory or settings.index_dir
        index_path = directory / INDEX_FILENAME
        metadata_path = directory / METADATA_FILENAME

        if not (index_path.exists() and metadata_path.exists()):
            _LOGGER.info("No hay índice en %s; se construye al vuelo.", directory)
            return cls.build(settings=settings)

        embedder = get_embedder(settings)
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            payload.get("embedder") != embedder.name
            or payload.get("dimension") != embedder.dimension
        ):
            _LOGGER.warning(
                "El índice se generó con '%s' (dim=%s) y el embedder activo es '%s' (dim=%d). "
                "Se reconstruye para evitar comparar vectores incompatibles.",
                payload.get("embedder"),
                payload.get("dimension"),
                embedder.name,
                embedder.dimension,
            )
            return cls.build(embedder=embedder, settings=settings)

        clauses = [Clause.model_validate(item) for item in payload["clauses"]]
        return cls(faiss.read_index(str(index_path)), clauses, embedder)

    # -- consulta -----------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 4,
        coverage_types: tuple[CoverageType, ...] | None = None,
    ) -> list[RetrievedClause]:
        """Recupera las `top_k` cláusulas más cercanas a la consulta.

        `coverage_types` restringe el resultado a las variantes indicadas —
        normalmente la del paquete contratado por el asegurado, para que nunca
        se le cite una cláusula de un producto que no compró.
        """
        if not query.strip() or self._index.ntotal == 0:
            return []

        vector = self._embedder.encode([query])
        limit = min(top_k * OVERSAMPLE if coverage_types else top_k, self._index.ntotal)
        scores, indices = self._index.search(vector, limit)

        results: list[RetrievedClause] = []
        for score, position in zip(scores[0], indices[0], strict=True):
            if position < 0:
                continue
            clause = self._clauses[int(position)]
            if coverage_types and clause.coverage_type not in coverage_types:
                continue
            results.append(RetrievedClause(clause=clause, score=float(score)))
            if len(results) == top_k:
                break
        return results

    @property
    def size(self) -> int:
        return int(self._index.ntotal)

    @property
    def embedder_name(self) -> str:
        return self._embedder.name

    def clause_by_id(self, clause_id: str) -> Clause | None:
        return next((c for c in self._clauses if c.clause_id == clause_id), None)


def format_context(results: list[RetrievedClause]) -> str:
    """Serializa las cláusulas recuperadas para inyectarlas en el prompt.

    Cada bloque lleva su `clause_id` para que el modelo pueda citarlo y para que
    la evaluación pueda verificar la cita contra la respuesta esperada.
    """
    if not results:
        return "No se encontraron cláusulas aplicables."
    return "\n\n".join(
        f"[{item.clause.clause_id}] {item.clause.title} (paquete {item.clause.coverage_type.value})\n"
        f"{item.clause.text}"
        for item in results
    )
