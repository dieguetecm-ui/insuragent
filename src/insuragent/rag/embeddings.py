"""Backends de embeddings.

Dos implementaciones intercambiables:

* ``SentenceTransformerEmbedder`` — calidad semántica real, modelo multilingüe.
* ``HashingEmbedder`` — proyección hash de n-gramas de palabra y de carácter.
  Es determinista, no descarga nada y corre en milisegundos; existe para que la
  suite de pruebas y un entorno sin salida a internet puedan ejercitar el mismo
  código de indexado y búsqueda.

Ambos devuelven vectores **normalizados L2**, de modo que el producto interno
que calcula FAISS es directamente la similitud coseno.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from collections import Counter

import numpy as np

from insuragent.config import Settings, get_settings
from insuragent.rag.lexicon import expandir

_LOGGER = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]+")


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(text))


class Embedder(ABC):
    """Convierte texto en vectores densos normalizados."""

    name: str
    dimension: int

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Devuelve una matriz float32 de forma (len(texts), dimension)."""

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype("float32")


class HashingEmbedder(Embedder):
    """Bolsa de n-gramas proyectada por hashing (*hashing trick*).

    Combina unigramas y bigramas de palabra con trigramas de carácter: los
    primeros capturan el vocabulario asegurador ("deducible", "robo total") y
    los segundos dan tolerancia a errores de dedo y variantes morfológicas.
    """

    name = "hashing"

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    @staticmethod
    def _bucket(feature: str, dimension: int) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        # El bit menos significativo fija el signo: reduce el sesgo por colisión.
        return value % dimension, 1.0 if value & 1 else -1.0

    # Peso por tipo de característica. Los trigramas de carácter son decenas por
    # frase y ahogarían cualquier otra señal si pesaran igual; los términos
    # canónicos del dominio son pocos y muy informativos, así que pesan más.
    PESOS = {"canonico": 3.0, "palabra": 1.0, "bigrama": 1.0, "trigrama": 0.3}

    def _features(self, text: str) -> Counter[str]:
        """Características ponderadas del texto.

        Cada clave lleva un prefijo de tipo para que un trigrama nunca colisione
        con una palabra idéntica y para poder ponderarlos por separado.
        """
        tokens = tokenize(text)
        features: Counter[str] = Counter()

        for token in tokens:
            features[f"w:{token}"] += 1
        # Términos canónicos del dominio: acercan el habla del asegurado
        # («choqué») a la redacción contractual («colisión»).
        for canonico in expandir(tokens):
            features[f"c:{canonico}"] += 1
        for primero, segundo in zip(tokens, tokens[1:], strict=False):
            features[f"b:{primero}_{segundo}"] += 1

        compact = " ".join(tokens)
        for i in range(max(len(compact) - 2, 0)):
            features[f"t:{compact[i : i + 3]}"] += 1
        return features

    def _peso(self, feature: str) -> float:
        return {
            "w": self.PESOS["palabra"],
            "c": self.PESOS["canonico"],
            "b": self.PESOS["bigrama"],
            "t": self.PESOS["trigrama"],
        }[feature[0]]

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype="float32")
        for row, text in enumerate(texts):
            for feature, count in self._features(text).items():
                index, sign = self._bucket(feature, self.dimension)
                # Ponderación sublineal en la frecuencia: una palabra repetida
                # aporta, pero no domina.
                matrix[row, index] += sign * self._peso(feature) * (1.0 + np.log(count))
        return _l2_normalize(matrix)


class SentenceTransformerEmbedder(Embedder):
    """Modelo multilingüe de `sentence-transformers`."""

    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        # sentence-transformers 5.x renombró el método; se soportan ambas versiones.
        get_dim = getattr(self._model, "get_embedding_dimension", None) or (
            self._model.get_sentence_embedding_dimension
        )
        self.dimension = int(get_dim())
        self.model_name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.astype("float32")


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Instancia el backend configurado, con degradación a `hashing`.

    Si el modelo de HuggingFace no puede cargarse (sin red, sin caché local), se
    avisa y se continúa con el embedder determinista en lugar de abortar: el
    índice se reconstruye igual, con menor calidad semántica.
    """
    settings = settings or get_settings()
    if settings.embedding_backend == "hash":
        return HashingEmbedder()
    try:
        return SentenceTransformerEmbedder(settings.embedding_model)
    except Exception as exc:  # noqa: BLE001 — degradación deliberada
        _LOGGER.warning(
            "No se pudo cargar '%s' (%s). Se usará el embedder hashing determinista.",
            settings.embedding_model,
            exc,
        )
        return HashingEmbedder()
