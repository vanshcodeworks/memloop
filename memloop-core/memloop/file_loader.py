import os
import csv
import json
from pypdf import PdfReader


def load_text_file(filepath):
    """Reads .txt or .md files."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading text {filepath}: {e}")
        return ""


def load_csv_file(filepath):
    """Converts tabular data to vector-ready narrative text."""
    narratives = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sentence = ". ".join(
                    [f"The {col} is {val}" for col, val in row.items()]
                )
                narratives.append(sentence)
    except Exception as e:
        print(f"Error reading CSV {filepath}: {e}")
    return "\n".join(narratives)


def load_csv_rows(filepath):
    """Return list of (sentence, meta) per CSV row."""
    rows = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                sentence = ". ".join([f"The {col} is {val}" for col, val in row.items()])
                rows.append((sentence, {"source": filepath, "type": "tabular", "row": idx}))
    except Exception as e:
        print(f"Error reading CSV {filepath}: {e}")
    return rows


def load_pdf_pages(filepath):
    """Return list of (page_text, meta) per PDF page."""
    pages = []
    try:
        reader = PdfReader(filepath)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((text, {"source": filepath, "type": "pdf", "page": i}))
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return pages


def ingest_folder(folder_path):
    """Recursively finds and loads supported files in a folder."""
    documents = []

    for root, _, files in os.walk(folder_path):
        for file in files:
            filepath = os.path.join(root, file)

            if file.endswith(".txt") or file.endswith(".md"):
                content = load_text_file(filepath)
                if content:
                    documents.append((content, {"source": filepath, "type": "text"}))

            elif file.endswith(".csv"):
                documents.extend(load_csv_rows(filepath))

            elif file.endswith(".json"):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = json.dumps(json.load(f))
                    if content:
                        documents.append((content, {"source": filepath, "type": "json"}))
                except Exception as e:
                    print(f"Error reading JSON {filepath}: {e}")

            elif file.endswith(".pdf"):
                documents.extend(load_pdf_pages(filepath))

    return documents
