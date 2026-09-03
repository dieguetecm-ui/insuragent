"""Preparación para hosting gestionado (entregable 1 del PRD §2).

La app desplegada debe arrancar sola: nadie ejecuta `make bootstrap` en
Streamlit Community Cloud. Estas pruebas verifican que el arranque en frío
funcione y que el manifiesto de dependencias siga siendo desplegable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from insuragent.bootstrap import ensure_ready
from insuragent.db.repository import Repository

RAIZ = Path(__file__).resolve().parents[1]


def _paquetes(manifiesto: Path) -> list[str]:
    """Nombres de paquete de un requirements, ignorando comentarios e includes.

    Leer el archivo entero daría falsos positivos: el propio comentario que
    explica por qué NO se incluye PyTorch contiene la palabra «PyTorch».
    """
    lineas = manifiesto.read_text(encoding="utf-8").lower().splitlines()
    return [
        linea.split("==")[0].split(">=")[0].strip()
        for linea in lineas
        if linea.strip() and not linea.lstrip().startswith(("#", "-r "))
    ]


def test_arranque_en_frio_siembra_todo(settings):
    """Disco vacío: la app debe dejarse lista sin intervención."""
    estado = ensure_ready(settings)
    assert estado["base"].startswith("sembrada")
    assert estado["indice"].startswith("construido")
    assert Repository(settings.db_path).list_customers()


def test_el_arranque_es_idempotente_y_barato(settings):
    ensure_ready(settings)
    segundo = ensure_ready(settings)
    assert segundo == {"corpus": "listo", "base": "existente", "indice": "existente"}


def test_el_arranque_siembra_historial(settings):
    """Sin historial, la demo publicada no puede mostrar memoria de largo plazo."""
    ensure_ready(settings)
    repository = Repository(settings.db_path)
    con_historial = [
        c for c in repository.list_customers() if repository.list_claims(c.customer_id)
    ]
    assert con_historial


def test_existe_el_punto_de_entrada_del_hosting():
    """Streamlit Cloud y HF Spaces ejecutan el archivo de la raíz."""
    entrada = RAIZ / "streamlit_app.py"
    assert entrada.exists()
    contenido = entrada.read_text(encoding="utf-8")
    assert "ensure_ready" in contenido
    assert "st.secrets" in contenido


def test_requirements_no_arrastra_pytorch():
    """PyTorch son ~2 GB de RSS: no cabe en el plan gratuito.

    Si alguien reintroduce `sentence-transformers` en el manifiesto de la
    aplicación, el despliegue deja de arrancar — y el fallo aparecería en
    producción, no aquí. Por eso se prueba.
    """
    paquetes = _paquetes(RAIZ / "requirements.txt")
    for pesado in ("torch", "sentence-transformers", "nvidia", "faiss-gpu"):
        assert not any(pesado in nombre for nombre in paquetes), (
            f"{pesado} no debe estar en requirements.txt; está en {paquetes}"
        )
    assert any("faiss-cpu" in n for n in paquetes)
    assert any("streamlit" in n for n in paquetes)


def test_los_extras_declaran_lo_pesado():
    """Lo que no cabe en el despliegue tiene que seguir siendo instalable aparte."""
    embeddings = _paquetes(RAIZ / "requirements-embeddings.txt")
    reporte = _paquetes(RAIZ / "requirements-report.txt")
    assert any("sentence-transformers" in n for n in embeddings)
    assert any("weasyprint" in n for n in reporte)


def test_la_plantilla_de_secretos_no_lleva_valores_reales():
    plantilla = (RAIZ / ".streamlit" / "secrets.toml.example").read_text(encoding="utf-8")
    assert "sk-ant-..." in plantilla
    assert "sk-ant-api" not in plantilla


@pytest.mark.parametrize("backend", ["hash", "sentence-transformers"])
def test_ambos_backends_recuperan_la_clausula_de_cristales(settings, backend):
    """El despliegue usa `hash`; el equivalente denso debe seguir funcionando."""
    from insuragent.rag.index import ClauseIndex
    from insuragent.schemas.policy import CoverageType

    indice = ClauseIndex.build(settings=settings.model_copy(update={"embedding_backend": backend}))
    recuperadas = indice.search(
        "se me rompió el parabrisas", top_k=3, coverage_types=(CoverageType.AMPLIA,)
    )
    assert "AMP-4.2" in [r.clause.clause_id for r in recuperadas]


def test_el_backend_ligero_no_pisa_la_configuracion_local():
    """`streamlit_app.py` sólo fuerza el backend léxico si falta la librería densa.

    pydantic-settings lee el `.env` como archivo, no lo vuelca al entorno, así
    que un `setdefault` incondicional ganaría siempre y silenciaría la elección
    del desarrollador al correr este mismo archivo en local.
    """
    contenido = (RAIZ / "streamlit_app.py").read_text(encoding="utf-8")
    assert 'find_spec("sentence_transformers") is None' in contenido
    indice_condicion = contenido.index("find_spec")
    indice_default = contenido.index('setdefault("INSURAGENT_EMBEDDING_BACKEND"')
    assert indice_condicion < indice_default, "el default debe estar dentro de la condición"


# ---------------------------------------------------------------------------
# Verificación de los pines contra PyPI
# ---------------------------------------------------------------------------

MANIFIESTOS = (
    "requirements.txt",
    "requirements-embeddings.txt",
    "requirements-report.txt",
    "requirements-dev.txt",
)


def _pines(manifiesto: Path) -> list[tuple[str, str]]:
    """Pares (paquete, versión) de un requirements."""
    import re

    pares = []
    for linea in manifiesto.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"\s*([A-Za-z0-9_.\-]+)==([^\s;#]+)", linea):
            pares.append((m.group(1), m.group(2)))
    return pares


@pytest.mark.parametrize("nombre_manifiesto", MANIFIESTOS)
def test_las_versiones_fijadas_existen_en_pypi(nombre_manifiesto: str):
    """Un pin inexistente rompe el despliegue, no la máquina de desarrollo.

    Ocurrió: `faiss-cpu` se fijó en `1.14.1` por analogía con
    `faiss-gpu-cu12==1.14.1.post1`, que es otro paquete con su propia
    numeración. En local nada falló —faiss-gpu ya estaba instalado— y el error
    apareció al desplegar, con un mensaje que no decía qué paquete era.
    """
    import json
    import urllib.error
    import urllib.request

    inexistentes = []
    for paquete, version in _pines(RAIZ / nombre_manifiesto):
        try:
            with urllib.request.urlopen(
                f"https://pypi.org/pypi/{paquete}/json", timeout=15
            ) as respuesta:
                publicadas = json.load(respuesta)["releases"]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            pytest.skip(f"sin acceso a PyPI: {exc}")
        if version not in publicadas:
            inexistentes.append(f"{paquete}=={version}")

    assert not inexistentes, (
        f"{nombre_manifiesto} fija versiones que no existen en PyPI: {', '.join(inexistentes)}"
    )


def test_faiss_cpu_tiene_rueda_para_linux():
    """La rueda es abi3 (`cp310-abi3-manylinux`), válida para 3.10+.

    Comprobarlo por el nombre exacto `cp312` daría un falso negativo y llevaría
    a descartar una versión que sí sirve.
    """
    import json
    import urllib.error
    import urllib.request

    version = dict(_pines(RAIZ / "requirements.txt"))["faiss-cpu"]
    try:
        with urllib.request.urlopen(
            "https://pypi.org/pypi/faiss-cpu/json", timeout=15
        ) as respuesta:
            archivos = json.load(respuesta)["releases"][version]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"sin acceso a PyPI: {exc}")

    ruedas_linux = [
        a["filename"]
        for a in archivos
        if "manylinux" in a["filename"] and "x86_64" in a["filename"]
    ]
    assert ruedas_linux, f"faiss-cpu {version} no publica rueda manylinux x86_64"
