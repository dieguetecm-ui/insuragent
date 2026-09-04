"""Auditoría de seguridad de la aplicación.

Cubre las fugas que sólo aparecen con la app publicada y varios visitantes
simultáneos: aislamiento entre sesiones, filtrado de datos entre asegurados y
qué información personal acaba en disco.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from insuragent.config import get_settings
from insuragent.data.synthetic import generate_claim_history, generate_customers
from insuragent.db.repository import Repository
from insuragent.rag.index import ClauseIndex
from insuragent.schemas.policy import CoverageType

APP = Path(__file__).resolve().parents[1] / "src" / "insuragent" / "ui" / "app.py"

# Credencial ficticia para las pruebas. El marcador la excluye del escáner de
# secretos del repositorio, que se aplica línea por línea.
LLAVE_FICTICIA = "sk-ant-api03-llave-de-prueba-no-real"  # pragma: allowlist secret
FRAGMENTO_FICTICIO = "llave-de-prueba-no-real"
TIMEOUT = 180


@pytest.fixture
def entorno(tmp_path: Path, monkeypatch):
    """Aplicación aislada con la cartera sintética y su historial ya sembrados."""
    import streamlit as st

    for clave, valor in {
        "INSURAGENT_LLM_PROVIDER": "stub",
        "INSURAGENT_EMBEDDING_BACKEND": "hash",
        "INSURAGENT_DATA_DIR": str(tmp_path),
        "INSURAGENT_CORPUS_DIR": str(tmp_path / "raw"),
        "INSURAGENT_INDEX_DIR": str(tmp_path / "index"),
        "INSURAGENT_UPLOADS_DIR": str(tmp_path / "uploads"),
        "INSURAGENT_DB_PATH": str(tmp_path / "seg.db"),
        "INSURAGENT_TRACE_FILE": str(tmp_path / "traces.jsonl"),
    }.items():
        monkeypatch.setenv(clave, valor)

    get_settings.cache_clear()
    st.cache_resource.clear()

    settings = get_settings()
    settings.ensure_dirs()
    repository = Repository(settings.db_path)
    repository.reset()
    clientes = generate_customers(6, settings.synthetic_seed)
    for cliente in clientes:
        repository.upsert_customer(cliente)
    for siniestro in generate_claim_history(clientes, settings.synthetic_seed):
        repository.save_claim(siniestro)
    return settings, clientes


def _credenciales(cliente):
    return [cliente.policy_number, cliente.rfc, cliente.curp, cliente.phone_last3]


def _entrar(app: AppTest, cliente) -> AppTest:
    app.run()
    for indice, valor in enumerate(_credenciales(cliente)):
        app.sidebar.text_input[indice].set_value(valor)
    return app.sidebar.button[0].click().run()


# ---------------------------------------------------------------------------
# Aislamiento entre visitantes
# ---------------------------------------------------------------------------


def test_un_visitante_no_hereda_la_sesion_de_otro(entorno):
    """Regresión de una fuga real y grave.

    La sesión se guardaba con `st.cache_resource`, que es un caché **global al
    proceso**, no por visitante. Como la sesión contiene la identidad del
    asegurado, su historial de siniestros y el borrador del reporte, cualquiera
    que abriera la aplicación pública heredaba la sesión de la persona anterior:
    veía sus datos y podía levantar siniestros en su nombre.
    """
    _, clientes = entorno
    elena = clientes[0]

    visitante_a = _entrar(AppTest.from_file(str(APP), default_timeout=TIMEOUT), elena)
    assert any(elena.full_name in s.value for s in visitante_a.sidebar.success)

    visitante_b = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    visitante_b.run()

    assert not visitante_b.sidebar.success, "el segundo visitante heredó una sesión ajena"
    assert len(visitante_b.sidebar.text_input) == 4, "debería ver la pantalla de acceso"


def test_dos_asegurados_simultaneos_no_se_mezclan(entorno):
    """Cada pestaña conserva su propio asegurado aunque compartan proceso."""
    _, clientes = entorno
    elena, carmen = clientes[0], clientes[1]

    a = _entrar(AppTest.from_file(str(APP), default_timeout=TIMEOUT), elena)
    b = _entrar(AppTest.from_file(str(APP), default_timeout=TIMEOUT), carmen)
    a.run()  # el visitante A vuelve a interactuar después de que B entró

    assert any(elena.full_name in s.value for s in a.sidebar.success)
    assert any(carmen.full_name in s.value for s in b.sidebar.success)
    assert not any(carmen.full_name in s.value for s in a.sidebar.success)


def test_la_sesion_no_vive_en_el_cache_global():
    """Guardia estructural: el caché de recursos no debe contener estado mutable."""
    codigo = APP.read_text(encoding="utf-8")
    bloque = codigo.split("def sesion_del_visitante")[0]
    assert "st.session_state" in codigo
    assert "InsurAgentSession(" not in bloque.split("@st.cache_resource")[-1], (
        "la sesión del asegurado no puede construirse dentro de st.cache_resource"
    )


def test_cerrar_sesion_borra_los_datos_del_visitante(entorno):
    _, clientes = entorno
    elena = clientes[0]
    app = _entrar(AppTest.from_file(str(APP), default_timeout=TIMEOUT), elena)

    salir = [b for b in app.sidebar.button if "Cerrar" in b.label]
    assert salir, "debe existir el botón de cierre de sesión"
    salir[0].click().run()

    assert not app.sidebar.success, "tras salir no debe seguir mostrando al asegurado"
    # Streamlit reejecuta el script y crea una sesión nueva: lo correcto es que
    # exista pero esté vacía, no que desaparezca.
    nueva = app.session_state["insuragent_session"]
    assert not nueva.authenticated
    assert nueva.customer is None
    assert app.session_state["messages"] == []


# ---------------------------------------------------------------------------
# Aislamiento de datos entre asegurados
# ---------------------------------------------------------------------------


def test_no_se_recuperan_clausulas_de_paquetes_ajenos(entorno):
    """Un asegurado nunca debe ver las condiciones de un producto que no compró."""
    settings, _ = entorno
    indice = ClauseIndex.build(settings=settings)
    for paquete in CoverageType:
        recuperadas = indice.search(
            "responsabilidad civil deducible cristales robo", top_k=8, coverage_types=(paquete,)
        )
        assert recuperadas
        assert all(r.clause.coverage_type is paquete for r in recuperadas)


def test_el_historial_es_solo_del_asegurado_autenticado(entorno):
    """`list_claims` nunca debe devolver expedientes de otra persona."""
    settings, clientes = entorno
    repository = Repository(settings.db_path)
    for cliente in clientes:
        for siniestro in repository.list_claims(cliente.customer_id):
            assert siniestro["customer_id"] == cliente.customer_id


def test_la_evidencia_de_un_siniestro_no_se_mezcla_con_otro(entorno, png_bytes):
    """Cada expediente escribe en su propio directorio."""
    from insuragent.agents.fnol_agent import FNOLAgent
    from insuragent.llm.stub_provider import StubProvider

    settings, _ = entorno
    agente = FNOLAgent(StubProvider(), Repository(settings.db_path), settings.uploads_dir)
    uno = agente.store_evidence("SIN-A", "foto.png", png_bytes, "image/png")
    otro = agente.store_evidence("SIN-B", "foto.png", png_bytes, "image/png")
    assert uno.stored_path.parent != otro.stored_path.parent


# ---------------------------------------------------------------------------
# Datos personales en disco
# ---------------------------------------------------------------------------


def test_las_trazas_no_registran_identificadores_regulados(entorno):
    """RFC y CURP están regulados por la LFPDPPP: no deben acabar en los logs.

    Las trazas se escriben en claro y se comparten al depurar; un RFC ahí es
    una fuga aunque el archivo nunca se versione.
    """
    from insuragent.llm import get_provider
    from insuragent.observability import TraceWriter
    from insuragent.session import InsurAgentSession

    settings, clientes = entorno
    elena = clientes[0]
    sesion = InsurAgentSession(
        provider=get_provider(settings),
        index=ClauseIndex.build(settings=settings),
        repository=Repository(settings.db_path),
        settings=settings,
    )
    sesion.customer = elena
    sesion.reset_conversation()
    sesion.send("¿Cuál es mi deducible por robo total?")

    eventos = TraceWriter(settings.trace_file).read_all()
    assert eventos, "la corrida debió dejar trazas"
    volcado = json.dumps(eventos, ensure_ascii=False)
    assert elena.rfc not in volcado, "el RFC no debe aparecer en las trazas"
    assert elena.curp not in volcado, "la CURP no debe aparecer en las trazas"


# ---------------------------------------------------------------------------
# Manejo de la credencial
# ---------------------------------------------------------------------------


def test_la_llave_no_aparece_al_representar_la_configuracion():
    """`repr(Settings)` acaba en trazas de error, logs y fallos de prueba.

    Con la llave como `str`, pytest la imprimía completa al fallar cualquier
    prueba que recibiera `settings` como fixture — y esa salida se pega en
    issues y en registros de CI.
    """
    from pydantic import SecretStr

    settings = get_settings()
    assert isinstance(settings.anthropic_api_key, SecretStr)

    con_llave = settings.model_copy(update={"anthropic_api_key": SecretStr(LLAVE_FICTICIA)})
    for representacion in (repr(con_llave), str(con_llave), str(con_llave.model_dump())):
        assert FRAGMENTO_FICTICIO not in representacion


def test_la_llave_no_se_serializa_al_volcar_la_configuracion():
    """Un `model_dump()` volcado a un log tampoco debe revelarla."""
    from pydantic import SecretStr

    con_llave = get_settings().model_copy(update={"anthropic_api_key": SecretStr(LLAVE_FICTICIA)})
    assert FRAGMENTO_FICTICIO not in json.dumps(con_llave.model_dump(), default=str)


def test_los_mensajes_de_error_del_proveedor_no_llevan_la_llave():
    """Los errores del proveedor se muestran al usuario en la interfaz."""
    import anthropic
    from pydantic import SecretStr

    from insuragent.llm.anthropic_provider import AnthropicProvider

    proveedor = AnthropicProvider.__new__(AnthropicProvider)
    proveedor._errors = anthropic
    proveedor.model = "claude-opus-5"
    proveedor._settings = get_settings().model_copy(
        update={"anthropic_api_key": SecretStr(LLAVE_FICTICIA)}
    )

    for excepcion in (
        anthropic.AuthenticationError.__new__(anthropic.AuthenticationError),
        TypeError("Could not resolve authentication method."),
        RuntimeError("fallo genérico"),
    ):
        assert FRAGMENTO_FICTICIO not in str(proveedor._translate(excepcion))


# ---------------------------------------------------------------------------
# Saneamiento de las trazas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "no_debe_contener"),
    [
        ("Mi RFC es XXXJ860330FYB", "XXXJ860330FYB"),
        ("Mi CURP XXXX860330MNEYSTB7", "XXXX860330MNEYSTB7"),
        ("Escríbeme a diego@ejemplo.mx", "diego@ejemplo.mx"),
        ("Llámame al 5512345678", "5512345678"),
        ("Tarjeta 4111 1111 1111 1111", "4111 1111 1111 1111"),
        (f"La llave es {LLAVE_FICTICIA}", FRAGMENTO_FICTICIO),
    ],
)
def test_el_texto_libre_se_sanea_antes_de_registrarse(entrada, no_debe_contener):
    """El mensaje del asegurado es el único campo donde cabe cualquier cosa."""
    from insuragent.observability import redactar

    assert no_debe_contener not in redactar(entrada)


def test_el_saneamiento_conserva_el_sentido_del_mensaje():
    """Redactar no puede volver inútil la traza para depurar el enrutamiento."""
    from insuragent.observability import redactar

    original = "Se rompió el parabrisas ayer en Avenida Insurgentes"
    assert redactar(original) == original


def test_el_texto_muy_largo_se_trunca():
    """Un mensaje enorme no debe inflar el archivo de trazas sin límite."""
    from insuragent.observability import LONGITUD_MAXIMA_TEXTO, redactar

    salida = redactar("a" * 5000)
    assert len(salida) < LONGITUD_MAXIMA_TEXTO + 40
    assert salida.endswith("[truncado]")


def test_las_trazas_reales_no_llevan_identificadores(entorno):
    """Comprobación de extremo a extremo sobre el archivo que se escribe."""
    from insuragent.llm import get_provider
    from insuragent.observability import TraceWriter
    from insuragent.session import InsurAgentSession

    settings, clientes = entorno
    elena = clientes[0]
    sesion = InsurAgentSession(
        provider=get_provider(settings),
        index=ClauseIndex.build(settings=settings),
        repository=Repository(settings.db_path),
        settings=settings,
    )
    sesion.customer = elena
    sesion.reset_conversation()
    sesion.send(f"Mi RFC es {elena.rfc} y mi CURP {elena.curp}, ¿cuál es mi deducible?")

    volcado = json.dumps(TraceWriter(settings.trace_file).read_all(), ensure_ascii=False)
    assert elena.rfc not in volcado
    assert elena.curp not in volcado
    assert "[RFC]" in volcado


# ---------------------------------------------------------------------------
# Permisos de los archivos con datos de asegurados
# ---------------------------------------------------------------------------


def test_la_base_nace_sin_permisos_para_otros_usuarios(tmp_path):
    """`make seed` recrea la base: ajustar los permisos a mano no basta.

    El umask habitual crea archivos `644`, legibles por cualquier usuario de la
    máquina. La base contiene RFC, CURP y el historial de siniestros.
    """
    import stat

    repositorio = Repository(tmp_path / "nueva.db")
    repositorio.initialize()
    modo = stat.S_IMODE((tmp_path / "nueva.db").stat().st_mode)
    assert modo & (stat.S_IRGRP | stat.S_IROTH) == 0, f"la base nació con {oct(modo)}"


def test_las_trazas_nacen_sin_permisos_para_otros_usuarios(tmp_path):
    import stat

    from insuragent.observability import TraceWriter

    destino = tmp_path / "traces.jsonl"
    TraceWriter(destino)
    modo = stat.S_IMODE(destino.stat().st_mode)
    assert modo & (stat.S_IRGRP | stat.S_IROTH) == 0


def test_la_evidencia_nace_sin_permisos_para_otros_usuarios(entorno, png_bytes):
    """Es la fotografía del vehículo de una persona concreta."""
    import stat

    from insuragent.agents.fnol_agent import FNOLAgent
    from insuragent.llm.stub_provider import StubProvider

    settings, _ = entorno
    agente = FNOLAgent(StubProvider(), Repository(settings.db_path), settings.uploads_dir)
    evidencia = agente.store_evidence("SIN-PERM", "dano.png", png_bytes, "image/png")

    for ruta in (evidencia.stored_path, evidencia.stored_path.parent):
        modo = stat.S_IMODE(ruta.stat().st_mode)
        assert modo & (stat.S_IRGRP | stat.S_IROTH) == 0, f"{ruta.name} nació con {oct(modo)}"


def test_restringir_no_revienta_en_rutas_inexistentes():
    """En un contenedor de sólo lectura el servicio debe seguir funcionando."""
    from insuragent.fs import restringir

    restringir(Path("/ruta/que/no/existe/archivo.db"))
