"""Disk-backed text extraction and bounded chunks; no page or text truncation."""
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pymupdf

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_to_file(source: str, destination: str, content_type: str) -> int:
    characters = 0
    with open(destination, "w", encoding="utf-8") as output:
        if content_type == DOCX_TYPE:
            # Stream the XML instead of loading a potentially large DOCX tree.
            with ZipFile(source) as archive, archive.open("word/document.xml") as xml:
                parents = []
                for event, element in ElementTree.iterparse(xml, events=("start", "end")):
                    if event == "start":
                        parents.append(element)
                        continue
                    if element.tag == "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t":
                        text = (element.text or "") + " "
                        output.write(text)
                        characters += len(text)
                    parents.pop()
                    if parents:
                        parents[-1].remove(element)
        else:
            with pymupdf.open(source) as document:
                for page in document:
                    text = page.get_text() + "\n"
                    output.write(text)
                    characters += len(text)
    if not characters or not has_text(destination):
        raise ValueError("No readable text found. Scanned documents need OCR before upload.")
    return characters


def has_text(path: str) -> bool:
    return any(chunk.strip() for chunk in text_chunks(path))


def text_chunks(path: str | Path, size: int = 3000, overlap: int = 200):
    """Yield ordered chunks without dropping text, retaining nearby context."""
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must exceed nonnegative overlap")
    with open(path, encoding="utf-8") as source:
        chunk = source.read(size)
        while chunk:
            yield chunk
            tail = source.read(size - overlap)
            if not tail:
                break
            chunk = (chunk[-overlap:] if overlap else "") + tail
