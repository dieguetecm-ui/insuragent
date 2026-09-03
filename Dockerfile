# Imagen del servicio para Cloud Run (PRD §8).
# Build en dos etapas: las ruedas se compilan en la etapa `builder` y la imagen
# final sólo lleva el runtime, sin toolchain de compilación.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .
# En Cloud Run no hay GPU: se sustituye faiss-gpu por faiss-cpu, misma API.
RUN sed -i 's/^faiss-gpu-cu12==.*/faiss-cpu==1.14.1/' requirements.txt \
    && pip install --prefix=/install -r requirements.txt


FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    INSURAGENT_LLM_PROVIDER=anthropic \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY --from=builder /install /usr/local

WORKDIR /app
COPY src/ ./src/
COPY scripts/ ./scripts/

# El corpus y el índice FAISS se hornean en la imagen: son estáticos y pequeños,
# así que el arranque en frío no paga descarga ni vectorización.
RUN python scripts/build_index.py

# Cloud Run exige un usuario no-root y respeta $PORT.
RUN useradd --create-home --uid 1001 insuragent \
    && mkdir -p /app/data/uploads \
    && chown -R insuragent:insuragent /app
USER insuragent

EXPOSE 8080

CMD ["sh", "-c", "streamlit run src/insuragent/ui/app.py --server.port=${PORT:-8080}"]
