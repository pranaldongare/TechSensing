"""
Document Source — converts an uploaded document's text into pseudo-RawArticle
instances for the sensing classification pipeline.

When a user uploads a document, this module replaces the normal ingest stage.
The document text is split into overlapping chunks, each treated as a
"pseudo-article" that flows through classify → report → verify as normal.
"""

import logging
import re
from datetime import datetime, timezone
from typing import List

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.document_source")

CHUNK_SIZE = 2000  # characters per pseudo-article
CHUNK_OVERLAP = 200  # overlap between chunks
MAX_CHUNKS = 80  # safety cap for very large documents


def document_to_articles(
    full_text: str,
    file_name: str,
    title: str = "",
) -> List[RawArticle]:
    """Split a parsed document's full text into pseudo-articles for
    classification.

    Each chunk becomes a ``RawArticle`` with:

    - title: derived from the first line or heading in the chunk
    - source: ``"Uploaded Document: {file_name}"``
    - url: ``"document://{file_name}#chunk-{N}"``
    - content: the chunk text
    """
    if not full_text or not full_text.strip():
        logger.warning("Empty document text, returning no articles")
        return []

    chunks = _split_into_chunks(full_text, CHUNK_SIZE, CHUNK_OVERLAP)
    if len(chunks) > MAX_CHUNKS:
        logger.info(
            f"Capping {len(chunks)} chunks to {MAX_CHUNKS} for '{file_name}'"
        )
        chunks = chunks[:MAX_CHUNKS]

    articles: List[RawArticle] = []
    source_name = f"Uploaded Document: {file_name}"
    now_iso = datetime.now(timezone.utc).isoformat()

    for i, chunk in enumerate(chunks):
        chunk_title = _extract_title(
            chunk, fallback=f"{title or file_name} (Section {i + 1})"
        )
        articles.append(
            RawArticle(
                title=chunk_title,
                url=f"document://{file_name}#chunk-{i + 1}",
                source=source_name,
                published_date=now_iso,
                content=chunk,
                snippet=chunk[:500],
            )
        )

    logger.info(
        f"Document '{file_name}' split into {len(articles)} pseudo-articles "
        f"({len(full_text)} chars, chunk_size={CHUNK_SIZE})"
    )
    return articles


def _split_into_chunks(text: str, size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds chunk size, force-split it
            if len(para) > size:
                for j in range(0, len(para), size - overlap):
                    chunks.append(para[j : j + size])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:size]]


def _extract_title(chunk: str, fallback: str) -> str:
    """Extract a title from the first line or heading of a chunk."""
    lines = chunk.strip().split("\n")
    for line in lines[:3]:
        clean = line.strip().lstrip("#").strip()
        if 10 < len(clean) < 150:
            return clean
    return fallback
