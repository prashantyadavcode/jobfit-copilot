from pathlib import Path

import pdfplumber
from docx import Document


def parse_file(file_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        return parse_pdf_bytes(file_bytes)
    if suffix == '.docx':
        return parse_docx_bytes(file_bytes)
    return file_bytes.decode('utf-8', errors='ignore')


def parse_pdf_bytes(file_bytes: bytes) -> str:
    import io

    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or '')
    return '\n'.join(text_parts)


def parse_docx_bytes(file_bytes: bytes) -> str:
    import io

    doc = Document(io.BytesIO(file_bytes))
    return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
