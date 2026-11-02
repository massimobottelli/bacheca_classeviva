"""Estrazione del testo dai PDF scaricati."""
from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger(__name__)


def extract_pdf_text(path: Path, max_chars: int = 20000) -> str:
    """Restituisce il testo del PDF, troncato a max_chars.

    Restituisce stringa vuota se il PDF non contiene testo estraibile
    (es. scansioni immagine: servirebbe OCR, fuori scope per ora).
    """
    log.info("📄 Estrazione testo da %s", path.name)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # PDF corrotto o protetto
        log.warning("⚠️  Impossibile aprire %s: %s", path.name, exc)
        return ""

    parts: list[str] = []
    total = 0
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            log.warning("⚠️  Pagina %d di %s non leggibile: %s", page_num, path.name, exc)
            continue
        if text.strip():
            parts.append(text)
            total += len(text)
            log.debug("   pagina %d: %d caratteri estratti", page_num, len(text))
        if total >= max_chars:
            log.debug("   troncatura a %d caratteri", max_chars)
            break

    result = "\n".join(parts)[:max_chars]
    log.info("   → %d caratteri di testo estratti da %d pagine", len(result), len(parts))
    return result