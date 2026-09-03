"""Interfaz Streamlit de InsurAgent (PRD §2.1, Fase 4).

Se ejecuta con:

    make app        # o: streamlit run src/insuragent/ui/app.py

La pantalla se divide en autenticación (barra lateral) y conversación (cuerpo).
El panel de trazas de la barra lateral expone la decisión de enrutamiento de
cada turno, que es el requisito de observabilidad del PRD §4.1 llevado a la UI:
quien hace la demo puede ver *por qué* el orquestador eligió cada agente.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite `streamlit run src/insuragent/ui/app.py` sin instalar el paquete.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from insuragent.config import get_settings  # noqa: E402
from insuragent.graph.state import Stage  # noqa: E402
from insuragent.observability import configure_logging  # noqa: E402
from insuragent.schemas.auth import LoginRequest  # noqa: E402
from insuragent.session import InsurAgentSession  # noqa: E402

st.set_page_config(page_title="InsurAgent — Asistente de Autos", page_icon="🚗", layout="wide")

WELCOME = (
    "Hola, soy **InsurAgent**. Puedo consultar las coberturas y deducibles de tu póliza de auto, "
    "levantar el reporte de un siniestro o ubicarte talleres en convenio. ¿En qué te ayudo?"
)


@st.cache_resource(show_spinner="Inicializando agentes, índice FAISS y base de datos…")
def bootstrap() -> InsurAgentSession:
    """Construye la sesión una sola vez por proceso de Streamlit."""
    configure_logging()
    return InsurAgentSession.create(get_settings())


def render_provider_banner(session: InsurAgentSession) -> None:
    """Avisa en pantalla si la app NO está hablando con el modelo real.

    Importa especialmente en una demo publicada: si la API key caduca o se queda
    sin saldo, el sistema degrada al proveedor determinista y sigue respondiendo.
    Sin este aviso, quien abra el enlace vería respuestas plausibles y las
    tomaría por salida del modelo, que es justo la confusión que hay que evitar.
    """
    configurado = session.settings.llm_provider
    efectivo = session.provider.name
    if efectivo != "stub":
        return

    if configurado == "stub":
        st.warning(
            "**Modo demostración sin modelo.** Las respuestas las genera un componente "
            "determinista, no un modelo de lenguaje: sirven para recorrer el flujo, no para "
            "juzgar la calidad de la redacción.",
            icon="🧪",
        )
    else:
        st.error(
            f"**El proveedor `{configurado}` no está disponible** (credencial ausente, caducada, "
            "sin saldo o sin red), así que se está usando el componente determinista. "
            "Las respuestas **no** provienen del modelo.",
            icon="⚠️",
        )


def render_login(session: InsurAgentSession) -> None:
    """Autenticación simulada del PRD §6.1."""
    st.sidebar.subheader("Acceso del asegurado")
    with st.sidebar.form("login"):
        policy_number = st.text_input("Número de póliza", placeholder="AUT-2026-100000")
        rfc = st.text_input("RFC", placeholder="XXXA850312A11")
        curp = st.text_input("CURP", placeholder="XXXX850312HNEBCD A1".replace(" ", ""))
        phone_last3 = st.text_input("Últimos 3 dígitos del celular", max_chars=3)
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if not submitted:
        return

    try:
        credentials = LoginRequest(
            policy_number=policy_number, rfc=rfc, curp=curp, phone_last3=phone_last3
        )
    except ValueError as exc:
        # Pydantic detiene el dato malformado antes de tocar la base (PRD §4.3).
        st.sidebar.error(
            "\n".join(f"• {err['msg']}" for err in getattr(exc, "errors", lambda: [])()) or str(exc)
        )
        return

    if not credentials.is_synthetic():
        st.sidebar.error(
            "Estos identificadores no llevan el marcador de dato sintético (XXX/XXXX). "
            "Esta PoC sólo opera con datos de prueba."
        )
        return

    customer = session.login(credentials)
    if customer is None:
        st.sidebar.error("Credenciales incorrectas. Verifica los cuatro datos.")
        return

    st.session_state.messages = [{"role": "assistant", "content": WELCOME}]
    st.session_state.traces = []
    st.rerun()


def render_customer_panel(session: InsurAgentSession) -> None:
    customer = session.customer
    assert customer is not None
    vehicle = customer.vehicle

    st.sidebar.success(f"Sesión activa: **{customer.full_name}**")
    st.sidebar.markdown(
        f"""
        **Póliza** `{customer.policy_number}`
        **Paquete** `{customer.coverage_type}`
        **Vigencia** {customer.policy_start:%d/%m/%Y} – {customer.policy_end:%d/%m/%Y}
        **Vehículo** {vehicle.brand} {vehicle.model} {vehicle.year} · placas `{vehicle.plates}`
        **Ciudad** {customer.city}
        """
    )

    claims = session.past_claims()
    if claims:
        with st.sidebar.expander(f"Historial de siniestros ({len(claims)})"):
            for claim in claims:
                st.markdown(
                    f"`{claim['claim_id']}` · {claim['incident_type']} · {claim['incident_date']}"
                )

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        session.logout()
        st.session_state.clear()
        st.rerun()


def render_diagnostics(session: InsurAgentSession) -> None:
    """Observabilidad en pantalla (PRD §4.1)."""
    st.sidebar.divider()
    st.sidebar.caption(
        f"Proveedor `{session.provider.name}` · modelo `{session.provider.model}` · "
        f"índice `{session.index.size}` cláusulas ({session.index.embedder_name})"
    )

    usage = session.total_usage
    left, right = st.sidebar.columns(2)
    left.metric("Tokens entrada", f"{usage.input_tokens:,}")
    right.metric("Tokens salida", f"{usage.output_tokens:,}")
    st.sidebar.metric("Costo acumulado", f"${usage.cost_usd:.5f} USD")

    traces = st.session_state.get("traces", [])
    if traces:
        with st.sidebar.expander("Trazas de enrutamiento", expanded=False):
            for entry in reversed(traces[-8:]):
                st.markdown(
                    f"`{entry['run_id']}` → **{entry['route']}** "
                    f"({entry['confidence']:.0%}, {entry['latency_ms']:.0f} ms)  \n"
                    f"<span style='font-size:0.85em;opacity:0.8'>{entry['reasoning']}</span>",
                    unsafe_allow_html=True,
                )


def render_evidence_uploader(session: InsurAgentSession) -> None:
    """Carga de evidencia; sólo visible en la etapa que la requiere (PRD §6.5)."""
    st.info("Adjunta una fotografía del daño para cerrar tu reporte.")
    uploaded = st.file_uploader(
        "Evidencia del siniestro",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        key=f"evidence_{len(st.session_state.messages)}",
    )
    if uploaded is None:
        return

    try:
        claim = session.attach_evidence(uploaded.name, uploaded.getvalue(), uploaded.type)
    except (ValueError, RuntimeError) as exc:
        st.error(f"No se pudo adjuntar la evidencia: {exc}")
        return

    confirmation = (
        f"✅ Reporte registrado con folio **{claim.claim_id}**.\n\n"
        f"- Tipo: {claim.incident_type.value}\n"
        f"- Fecha: {claim.incident_date:%d/%m/%Y}\n"
        f"- Lugar: {claim.location}\n"
        f"- Evidencia: `{claim.evidence[0].stored_path.name}`\n"
        + (
            f"- Deducible estimado: ${claim.deductible_quoted_mxn:,.2f} MXN\n"
            if claim.deductible_quoted_mxn
            else ""
        )
        + "\nUn ajustador se pondrá en contacto contigo."
    )
    st.session_state.messages.append({"role": "assistant", "content": confirmation})
    st.rerun()


def render_chat(session: InsurAgentSession) -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    stage = (session.state or {}).get("stage")
    if stage == Stage.AWAITING_EVIDENCE.value:
        render_evidence_uploader(session)

    prompt = st.chat_input("Escribe tu consulta…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"), st.spinner("Consultando…"):
        try:
            turn = session.send(prompt)
        except Exception as exc:  # noqa: BLE001 — la UI nunca debe romperse
            st.error(f"Ocurrió un error procesando tu consulta: {exc}")
            return
        st.markdown(turn.answer)
        if turn.citations:
            st.caption("Cláusulas citadas: " + ", ".join(f"`{c}`" for c in turn.citations))

    st.session_state.messages.append({"role": "assistant", "content": turn.answer})
    st.session_state.traces.append(
        {
            "run_id": turn.run_id,
            "route": turn.route,
            "confidence": turn.route_confidence,
            "reasoning": turn.route_reasoning,
            "latency_ms": turn.latency_ms,
        }
    )
    st.rerun()


def main() -> None:
    st.title("🚗 InsurAgent")
    st.caption(
        "Asistente agéntico para el ramo de automóviles — PoC con datos sintéticos. "
        "No constituye asesoría ni oferta de seguro."
    )

    session = bootstrap()
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("traces", [])
    render_provider_banner(session)

    if not session.authenticated:
        render_login(session)
        st.info(
            "Ingresa con las credenciales de un asegurado sintético para comenzar. "
            "Corre `make seed` para generarlas e imprimirlas en la terminal."
        )
        render_diagnostics(session)
        return

    render_customer_panel(session)
    render_diagnostics(session)
    render_chat(session)


main()
