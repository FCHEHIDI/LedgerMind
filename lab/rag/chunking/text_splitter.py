"""Invariant 4 — RAG: recursive character text splitter.

Pure-Python implementation — no external dependencies.  Mirrors the behaviour
of LangChain's ``RecursiveCharacterTextSplitter`` at a fraction of the import
cost, which keeps lab tests fast and dependency-free.

Strategy
--------
1. Try each separator in order (default: paragraph → newline → space → char).
2. Split the text at the *first* separator that produces pieces within
   ``chunk_size``.
3. Reassemble pieces into chunks respecting ``chunk_size`` and ``chunk_overlap``.

Complexity: O(n · s) where n = len(text) and s = len(separators).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]


@dataclass(frozen=True)
class Chunk:
    """A contiguous slice of source text produced by :class:`TextSplitter`.

    Attributes:
        text: The chunk content (already stripped of leading/trailing whitespace).
        index: Zero-based position of this chunk within the document.
        start_char: Inclusive start offset in the *original* text.
        end_char: Exclusive end offset in the *original* text.
    """

    text: str
    index: int
    start_char: int
    end_char: int

    def __len__(self) -> int:
        """Return the number of characters in this chunk."""
        return len(self.text)


class TextSplitter:
    """Recursive character text splitter.

    Splits a document into overlapping chunks suitable for embedding and
    retrieval.  Chunk boundaries follow natural language breaks (paragraphs,
    then lines, then words, then characters as last resort).

    Args:
        chunk_size: Maximum number of characters per chunk.
        chunk_overlap: Number of characters shared between consecutive chunks.
            Must be strictly less than ``chunk_size``.
        separators: Ordered list of separator strings to try.  Falls back to
            splitting on individual characters when all separators fail.

    Raises:
        ValueError: If ``chunk_overlap >= chunk_size`` or ``chunk_size < 1``.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: list[str] | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})"
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators: list[str] = separators if separators is not None else _DEFAULT_SEPARATORS
        logger.debug(
            "TextSplitter init: chunk_size=%d, chunk_overlap=%d, separators=%r",
            chunk_size,
            chunk_overlap,
            self._separators,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(self, text: str) -> list[Chunk]:
        """Split *text* into overlapping :class:`Chunk` objects.

        Args:
            text: The source document text to split.

        Returns:
            Ordered list of chunks.  Returns an empty list when *text* is
            empty or whitespace-only.
        """
        if not text or not text.strip():
            return []

        raw_chunks = self._recursive_split(text)
        merged = self._merge(raw_chunks, text)

        logger.debug("TextSplitter.split: %d chunks from %d chars", len(merged), len(text))
        return merged

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recursive_split(self, text: str) -> list[str]:
        """Return a flat list of text pieces smaller than ``chunk_size``."""
        # Base case: text already fits in one chunk.
        if len(text) <= self._chunk_size:
            return [text]

        for sep in self._separators:
            if sep == "":
                # Last resort: hard-split every character.
                return [text[i : i + self._chunk_size] for i in range(0, len(text), self._chunk_size)]

            if sep not in text:
                continue

            parts = text.split(sep)
            result: list[str] = []
            for part in parts:
                if not part:
                    continue
                if len(part) <= self._chunk_size:
                    result.append(part)
                else:
                    result.extend(self._recursive_split(part))
            return result

        # Fallback (should not be reached with default separators ending in "").
        return [text[i : i + self._chunk_size] for i in range(0, len(text), self._chunk_size)]

    def _merge(self, pieces: list[str], original: str) -> list[Chunk]:
        """Reassemble *pieces* into chunks with overlap, tracking char offsets."""
        chunks: list[Chunk] = []
        current_parts: list[str] = []
        current_len = 0
        # We rebuild offsets by scanning original text linearly.
        scan_pos = 0
        chunk_index = 0

        def _flush(parts: list[str]) -> None:
            nonlocal chunk_index
            joined = " ".join(parts).strip()
            if not joined:
                return
            # Locate joined text in original starting from scan_pos (approx).
            start = original.find(parts[0].strip(), scan_pos)
            if start == -1:
                start = scan_pos
            end = start + len(joined)
            chunks.append(Chunk(text=joined, index=chunk_index, start_char=start, end_char=end))
            chunk_index += 1

        for piece in pieces:
            piece_len = len(piece)
            if current_len + piece_len > self._chunk_size and current_parts:
                _flush(current_parts)
                # Keep overlap: drop leading parts until within overlap budget.
                overlap_budget = self._chunk_overlap
                while current_parts and overlap_budget < sum(len(p) for p in current_parts):
                    current_parts.pop(0)
                current_len = sum(len(p) for p in current_parts)

            current_parts.append(piece)
            current_len += piece_len

        if current_parts:
            _flush(current_parts)

        return chunks
