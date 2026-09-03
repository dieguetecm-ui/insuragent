"""Recuperación sobre las condiciones generales (PRD §4.2)."""

from __future__ import annotations

import numpy as np
import pytest

from insuragent.data.corpus import CLAUSES
from insuragent.rag.embeddings import HashingEmbedder
from insuragent.rag.index import ClauseIndex, format_context
from insuragent.schemas.policy import CoverageType


def test_embedder_produce_vectores_normalizados():
    vectors = HashingEmbedder(dimension=256).encode(
        ["robo total del vehículo", "rotura de cristales"]
    )
    assert vectors.shape == (2, 256)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_embedder_es_determinista():
    embedder = HashingEmbedder()
    assert np.array_equal(embedder.encode(["deducible"]), embedder.encode(["deducible"]))


def test_indice_contiene_todas_las_clausulas(clause_index: ClauseIndex):
    assert clause_index.size == len(CLAUSES)


def test_filtro_por_paquete_no_devuelve_otras_variantes(clause_index: ClauseIndex):
    """Nunca se le cita al asegurado un producto que no contrató."""
    results = clause_index.search(
        "responsabilidad civil", top_k=5, coverage_types=(CoverageType.RC,)
    )
    assert results
    assert all(r.clause.coverage_type is CoverageType.RC for r in results)


def test_misma_pregunta_recupera_clausulas_distintas_por_paquete(clause_index: ClauseIndex):
    """El caso duro del corpus traslapado: RC vive en las tres variantes."""
    question = "límite de responsabilidad civil por daños a terceros"
    per_package = {
        coverage: clause_index.search(question, top_k=1, coverage_types=(coverage,))[
            0
        ].clause.clause_id
        for coverage in CoverageType
    }
    assert len(set(per_package.values())) == 3


def test_indice_persiste_y_se_recarga(clause_index: ClauseIndex, settings, tmp_path):
    clause_index.save(settings.index_dir)
    reloaded = ClauseIndex.load(settings.index_dir, settings=settings)
    assert reloaded.size == clause_index.size
    original = clause_index.search("deducible por robo total", top_k=3)
    restored = reloaded.search("deducible por robo total", top_k=3)
    assert [r.clause.clause_id for r in original] == [r.clause.clause_id for r in restored]


def test_consulta_vacia_no_revienta(clause_index: ClauseIndex):
    assert clause_index.search("   ") == []


def test_contexto_incluye_identificadores_citables(clause_index: ClauseIndex):
    results = clause_index.search(
        "rotura de cristales", top_k=2, coverage_types=(CoverageType.AMPLIA,)
    )
    context = format_context(results)
    assert all(f"[{r.clause.clause_id}]" in context for r in results)


@pytest.mark.parametrize(
    ("question", "coverage", "expected"),
    [
        ("¿cuál es mi deducible por robo total?", CoverageType.AMPLIA, "AMP-3.1"),
        ("se rompió el parabrisas de mi auto", CoverageType.AMPLIA, "AMP-4.2"),
        ("¿cuántos servicios de grúa tengo?", CoverageType.BASICA, "BAS-6.1"),
    ],
)
def test_casos_de_recuperacion_representativos(
    clause_index: ClauseIndex, question, coverage, expected
):
    results = clause_index.search(question, top_k=4, coverage_types=(coverage,))
    assert expected in [r.clause.clause_id for r in results]


# ---------------------------------------------------------------------------
# Léxico del dominio (recuperación sin modelo denso)
# ---------------------------------------------------------------------------


def test_el_lexico_acerca_el_habla_del_cliente_a_la_poliza():
    """«Choqué» y «colisión» deben compartir el término canónico."""
    from insuragent.rag.embeddings import tokenize
    from insuragent.rag.lexicon import expandir

    assert "#colision" in expandir(tokenize("Si choco mi auto"))
    assert "#colision" in expandir(tokenize("daños por colisión o volcadura"))


def test_los_terminos_canonicos_no_colisionan_con_palabras_reales():
    """El prefijo `#` evita que un canónico se confunda con una palabra del texto."""
    from insuragent.rag.lexicon import expandir

    assert all(t.startswith("#") for t in expandir(["choque", "cristal", "robo"]))


def test_el_lexico_no_tiene_variantes_ambiguas():
    """Una variante en dos grupos haría impredecible la expansión."""
    from collections import Counter

    from insuragent.rag.lexicon import GRUPOS

    todas = [v for variantes in GRUPOS.values() for v in variantes]
    repetidas = {v: n for v, n in Counter(todas).items() if n > 1}
    ambiguas = {v for v in repetidas if len({g for g, vs in GRUPOS.items() if v in vs}) > 1}
    assert not ambiguas, f"variantes en más de un grupo: {ambiguas}"


@pytest.mark.parametrize(
    ("pregunta", "coverage", "esperada"),
    [
        # El caso que el embedder léxico fallaba antes del diccionario.
        ("Si choco mi auto, ¿me cubren la reparación?", CoverageType.BASICA, "BAS-2.2"),
        ("Se me estrelló el parabrisas", CoverageType.AMPLIA, "AMP-4.2"),
        ("¿Me mandan una grúa?", CoverageType.BASICA, "BAS-6.1"),
    ],
)
def test_recuperacion_lexica_resuelve_sinonimos_del_dominio(pregunta, coverage, esperada):
    from insuragent.rag.embeddings import HashingEmbedder

    indice = ClauseIndex.build(embedder=HashingEmbedder())
    recuperadas = indice.search(pregunta, top_k=4, coverage_types=(coverage,))
    assert esperada in [r.clause.clause_id for r in recuperadas]


def test_los_trigramas_no_ahogan_al_lexico():
    """Los pesos deben priorizar la señal del dominio sobre el ruido de caracteres."""
    from insuragent.rag.embeddings import HashingEmbedder

    pesos = HashingEmbedder.PESOS
    assert pesos["canonico"] > pesos["palabra"] > pesos["trigrama"]
