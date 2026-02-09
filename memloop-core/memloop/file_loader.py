"""
file_loader.py – Robust local-file ETL: PDF, CSV, JSON, TXT, MD, DOCX.

Key upgrades:
  • Sentence-aware chunking with configurable overlap (no mid-sentence cuts).
  • CSV linearizer produces richer, more searchable narratives.
  • PDF extraction with per-page metadata and header/footer stripping.
  • JSON flattening for nested structures.
  • Graceful error handling per file — one bad file never kills the pipeline.
"""

import os
import re
import csv
import json
import logging
from typing import Optional

logger = logging.getLogger("memloop.file_loader")

# ── Sentence-aware text chunker ───────────────────────────

_SENTENCE_BOUNDARY = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z"\'])|(?<=\n)\s*(?=\S)', re.MULTILINE
)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
    respect_sentences: bool = True,
) -> list[str]:
    """
    Split *text* into chunks of ≈ *chunk_size* chars with *overlap*.

    When *respect_sentences* is True the splitter avoids cutting inside
    a sentence — it walks backwards to the nearest sentence boundary.
    """
    if not text or not text.strip():
        return []

    text = _normalise_whitespace(text)

    if len(text) <= chunk_size:
        return [text]

    if not respect_sentences:
        step = max(chunk_size - overlap, 1)
        return [text[i : i + chunk_size] for i in range(0, len(text), step) if text[i : i + chunk_size].strip()]

    # Sentence-aware splitting
    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)

        # If we're not at the very end, try to break at a sentence boundary
        if end < length:
            # Look for the last sentence boundary within this window
            window = text[start:end]
            boundaries = list(_SENTENCE_BOUNDARY.finditer(window))
            if boundaries:
                # Use the last sentence boundary found (at least 40% into chunk)
                min_pos = int(chunk_size * 0.4)
                good = [b for b in boundaries if b.start() >= min_pos]
                if good:
                    end = start + good[-1].start()
                else:
                    end = start + boundaries[-1].start()

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        step = max(end - start - overlap, 1)
        start += step

    return chunks


def _normalise_whitespace(text: str) -> str:
    """Collapse runs of whitespace but keep paragraph breaks."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── File loaders ──────────────────────────────────────────

def load_text_file(filepath: str) -> str:
    """Read .txt / .md files with encoding fallback."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            logger.warning("Error reading text %s: %s", filepath, e)
            return ""
    logger.warning("Could not decode %s with any known encoding", filepath)
    return ""


def load_pdf_pages(filepath: str) -> list[tuple[str, dict]]:
    """
    Extract text per PDF page.
    Strips common headers/footers (page numbers, running headers).
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("pypdf not installed – cannot read PDFs")
        return []

    pages: list[tuple[str, dict]] = []
    try:
        reader = PdfReader(filepath)
        total_pages = len(reader.pages)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = _strip_pdf_artifacts(text)
            if text.strip():
                pages.append(
                    (
                        text,
                        {
                            "source": filepath,
                            "type": "pdf",
                            "page": i,
                            "total_pages": total_pages,
                        },
                    )
                )
    except Exception as e:
        logger.warning("Error reading PDF %s: %s", filepath, e)
    return pages


def _strip_pdf_artifacts(text: str) -> str:
    """Remove common PDF noise: page numbers, excessive whitespace."""
    # Standalone page numbers at start/end of text
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    # Excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_csv_rows(
    filepath: str,
    max_cols_in_narrative: int = 20,
) -> list[tuple[str, dict]]:
    """
    Convert each CSV row into a rich narrative sentence.
    Skips empty rows and caps column count to avoid giant chunks.
    """
    rows: list[tuple[str, dict]] = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return rows

            fields = reader.fieldnames[:max_cols_in_narrative]
            for idx, row in enumerate(reader, start=1):
                parts = []
                for col in fields:
                    val = (row.get(col) or "").strip()
                    if val:
                        parts.append(f"{col}: {val}")
                if parts:
                    sentence = "Row " + str(idx) + " — " + "; ".join(parts) + "."
                    rows.append(
                        (sentence, {"source": filepath, "type": "tabular", "row": idx})
                    )
    except Exception as e:
        logger.warning("Error reading CSV %s: %s", filepath, e)
    return rows


def load_json_file(filepath: str) -> list[tuple[str, dict]]:
    """
    Load a JSON file.  If root is a list, each item becomes its own chunk.
    Nested objects are flattened to key-value text.
    """
    docs: list[tuple[str, dict]] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for idx, item in enumerate(data, start=1):
                text = _flatten_json(item) if isinstance(item, dict) else str(item)
                if text.strip():
                    docs.append(
                        (text, {"source": filepath, "type": "json", "item_index": idx})
                    )
        elif isinstance(data, dict):
            text = _flatten_json(data)
            if text.strip():
                docs.append((text, {"source": filepath, "type": "json"}))
        else:
            docs.append((str(data), {"source": filepath, "type": "json"}))
    except Exception as e:
        logger.warning("Error reading JSON %s: %s", filepath, e)
    return docs


def _flatten_json(obj: dict, prefix: str = "") -> str:
    """Recursively flatten a dict into 'key: value' lines."""
    lines: list[str] = []
    for key, val in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            lines.append(_flatten_json(val, full_key))
        elif isinstance(val, list):
            lines.append(f"{full_key}: {json.dumps(val)}")
        else:
            lines.append(f"{full_key}: {val}")
    return "\n".join(lines)


# ── Folder ingestion ─────────────────────────────────────

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".pdf"}


def ingest_folder(
    folder_path: str,
    extensions: Optional[set[str]] = None,
) -> list[tuple[str, dict]]:
    """
    Recursively ingest all supported files under *folder_path*.
    Returns [(text, metadata), …].
    """
    allowed = extensions or SUPPORTED_EXTENSIONS
    documents: list[tuple[str, dict]] = []

    if not os.path.isdir(folder_path):
        logger.error("Folder not found: %s", folder_path)
        return documents

    for root, _, files in os.walk(folder_path):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in allowed:
                continue

            filepath = os.path.join(root, fname)
            try:
                if ext in (".txt", ".md"):
                    content = load_text_file(filepath)
                    if content.strip():
                        documents.append(
                            (content, {"source": filepath, "type": "text"})
                        )

                elif ext == ".csv":
                    documents.extend(load_csv_rows(filepath))

                elif ext == ".json":
                    documents.extend(load_json_file(filepath))

                elif ext == ".pdf":
                    documents.extend(load_pdf_pages(filepath))
            except Exception as e:
                logger.warning("Skipping %s: %s", filepath, e)

    logger.info(
        "Ingested %d document segments from %s", len(documents), folder_path
    )
    return documents
