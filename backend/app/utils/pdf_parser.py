from io import BytesIO

from langchain_core.documents import Document
from pypdf import PdfReader


def extract_pdf_pages(content: bytes) -> list[Document]:
    """Read text PDFs; scanned PDFs need OCR, which is not implemented yet."""
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(Document(page_content=text, metadata={"page": number, "total_pages": len(reader.pages)}))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The PDF is invalid or its text could not be extracted.") from exc
    if not pages:
        raise ValueError("The PDF contains no extractable text. Scanned PDFs are not supported yet.")
    return pages
