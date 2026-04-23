"""Invariant 4 — RAG: text-embedding layer.

Design
------
* ``EmbedderProtocol`` — structural interface (typing.Protocol).  Any object
  that implements ``embed(texts) -> np.ndarray`` is a valid embedder.
* ``SentenceTransformerEmbedder`` — production implementation backed by
  `sentence-transformers <https://www.sbert.net/>`_ (all-MiniLM-L6-v2 by
  default, 384-dim, ~22 MB).
* ``StubEmbedder`` — deterministic fake for unit tests.  It hashes each text
  to a reproducible float32 vector — no model download required.

Lazy import
-----------
``sentence_transformers`` is imported inside ``SentenceTransformerEmbedder``
methods so that the module can be imported in environments where the package
is not installed (tests use ``StubEmbedder`` instead).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Structural interface for text embedders.

    Any class implementing ``embed`` conforms to this protocol without
    explicit inheritance.
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode *texts* into a float32 embedding matrix.

        Args:
            texts: Non-empty list of input strings.

        Returns:
            A float32 ``ndarray`` of shape ``(len(texts), dim)`` where all
            rows are L2-normalised (unit vectors).
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class SentenceTransformerEmbedder:
    """Embedder backed by a ``sentence-transformers`` model.

    The underlying model is loaded lazily on the first call to :meth:`embed`
    so that importing this module has zero startup cost.

    Args:
        model_name: HuggingFace model identifier.  Defaults to
            ``"all-MiniLM-L6-v2"`` (384 dimensions, Apache-2.0 licence).
        device: PyTorch device string (``"cpu"``, ``"cuda"``…).  ``None``
            lets sentence-transformers pick automatically.

    Raises:
        ImportError: If ``sentence-transformers`` is not installed.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None  # loaded lazily

    # ------------------------------------------------------------------
    # EmbedderProtocol
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode *texts* and return L2-normalised float32 embeddings.

        Args:
            texts: List of strings to embed.  Must not be empty.

        Returns:
            ndarray of shape ``(len(texts), dim)`` with float32 dtype.

        Raises:
            ImportError: If ``sentence-transformers`` is not installed.
            ValueError: If *texts* is empty.
        """
        if not texts:
            raise ValueError("texts must not be empty")
        self._ensure_model()
        logger.debug("SentenceTransformerEmbedder.embed: %d texts", len(texts))
        embeddings: np.ndarray = self._model.encode(  # type: ignore[union-attr]
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)

    @property
    def dim(self) -> int:
        """Embedding dimension (requires model to be loaded first)."""
        self._ensure_model()
        return self._model.get_sentence_embedding_dimension()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Load the sentence-transformers model if not already loaded."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required. "
                "Install it with: pip install sentence-transformers"
            ) from exc

        logger.info("Loading sentence-transformers model: %s", self._model_name)
        kwargs: dict = {}
        if self._device is not None:
            kwargs["device"] = self._device
        self._model = SentenceTransformer(self._model_name, **kwargs)
        logger.info(
            "Model loaded: %s (dim=%d)",
            self._model_name,
            self._model.get_sentence_embedding_dimension(),
        )


# ---------------------------------------------------------------------------
# Test stub (deterministic, no model download)
# ---------------------------------------------------------------------------


class StubEmbedder:
    """Deterministic embedder for unit tests.

    Each text is hashed with SHA-256 and the resulting bytes are reshaped into
    a float32 vector of size *dim*.  The vector is L2-normalised so it behaves
    identically to a real embedder w.r.t. cosine similarity.

    Two identical strings always produce the same vector; two different strings
    almost certainly produce different vectors (collision probability ≈ 2⁻²⁵⁶).

    Args:
        dim: Embedding dimension.  Defaults to 16 (enough for lab tests).
    """

    def __init__(self, dim: int = 16) -> None:
        if dim < 1:
            raise ValueError(f"dim must be >= 1, got {dim}")
        self._dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return deterministic L2-normalised float32 embeddings.

        Args:
            texts: List of strings to embed.

        Returns:
            ndarray of shape ``(len(texts), self.dim)`` with float32 dtype.
        """
        if not texts:
            raise ValueError("texts must not be empty")
        rows: list[np.ndarray] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            # Repeat digest bytes until we have enough, then reshape.
            repeated = (digest * ((self._dim // len(digest)) + 1))[: self._dim]
            vec = np.frombuffer(repeated, dtype=np.uint8).astype(np.float32)
            norm = np.linalg.norm(vec)
            vec = vec / norm if norm > 0 else vec
            rows.append(vec)
        return np.stack(rows, axis=0)

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        return self._dim
