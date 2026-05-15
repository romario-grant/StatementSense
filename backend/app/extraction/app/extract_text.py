"""Raw text extraction from bank-statement PDFs using pdfplumber."""

import logging
from pathlib import Path
from typing import Union

import pdfplumber

from .utils import clean_text

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
    """Return the cleaned raw text contained in the PDF at ``pdf_path``, or an empty string when extraction yields no usable content."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    logger.info(f"Extracting text from PDF: {pdf_path}")
    try:
        text = extract_with_pdfplumber(pdf_path)
        if text and len(text.strip()) > 10:
            logger.info(f"Successfully extracted {len(text)} characters using pdfplumber")
            return clean_text(text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
    logger.warning("No text could be extracted from the PDF")
    return ""

def extract_with_pdfplumber(pdf_path: Path) -> str:
    """Iterate over every page of the PDF and concatenate the extracted text with a per-page header for downstream parsing."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        logger.info(f"PDF has {len(pdf.pages)} pages")
        for page_num, page in enumerate(pdf.pages, 1):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}\n")
                    logger.debug(f"Extracted {len(page_text)} characters from page {page_num}")
                else:
                    logger.warning(f"No text found on page {page_num}")
            except Exception as e:
                logger.error(f"Failed to extract text from page {page_num}: {e}")
                continue
    return '\n'.join(text_parts)
