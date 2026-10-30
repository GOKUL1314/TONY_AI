"""
Document Loaders and Text Normalizers for TONY AI Personal Knowledge & RAG Subsystem (Stage 11).
Safely extracts text, preserves page and section boundaries for PDF, DOCX, Markdown,
plain text, and multi-language source code files without executing any code.
"""
from abc import ABC, abstractmethod
import logging
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from typing import List, Tuple, Optional, Dict, Any

from knowledge.errors import UnsupportedFileError, CorruptedDocumentError

logger = logging.getLogger("tony.knowledge.loaders")

# Supported file extension categories
TEXT_EXTENSIONS = {
    ".txt", ".text", ".log", ".csv", ".tsv", ".ini", ".cfg", ".conf", ".toml"
}

MARKDOWN_EXTENSIONS = {
    ".md", ".markdown", ".mdown", ".mkdn"
}

CODE_EXTENSIONS = {
    ".py", ".pyw",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx",
    ".html", ".htm",
    ".css", ".scss", ".sass",
    ".json", ".jsonl",
    ".yaml", ".yml",
    ".xml",
    ".sql",
    ".dart",
    ".java", ".kt", ".kts",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh",
    ".go", ".rs", ".rb", ".php", ".swift", ".cs"
}

PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}

ALL_SUPPORTED_EXTENSIONS = (
    TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | CODE_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS
)
SUPPORTED_EXTENSIONS = ALL_SUPPORTED_EXTENSIONS


class BaseLoader(ABC):
    """Abstract base class for document text extractors."""

    @abstractmethod
    def load(self, file_path: str | Path) -> List[Tuple[Optional[int], Optional[str], str]]:
        """
        Load and extract text units from file.
        Returns a list of tuples: (page_number, section_header, text_content).
        """
        pass


class TextAndCodeLoader(BaseLoader):
    """Extracts text from plain text and source code files with encoding fallbacks."""

    def load(self, file_path: str | Path) -> List[Tuple[Optional[int], Optional[str], str]]:
        p = Path(file_path)
        encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
        content = None
        for enc in encodings:
            try:
                content = p.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if content is None:
            raise CorruptedDocumentError(f"Unable to decode text file '{p.name}' with supported encodings.")

        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        return [(None, p.name, normalized)]


class MarkdownLoader(BaseLoader):
    """Extracts text from Markdown files preserving heading hints."""

    def load(self, file_path: str | Path) -> List[Tuple[Optional[int], Optional[str], str]]:
        p = Path(file_path)
        encodings = ["utf-8", "utf-8-sig", "latin-1"]
        content = None
        for enc in encodings:
            try:
                content = p.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise CorruptedDocumentError(f"Unable to decode Markdown file '{p.name}'.")

        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        return [(None, None, normalized)]


class PDFLoader(BaseLoader):
    """Extracts text from PDF documents preserving page boundaries and page numbers."""

    def load(self, file_path: str | Path) -> List[Tuple[Optional[int], Optional[str], str]]:
        p = Path(file_path)
        try:
            import pypdf
        except ImportError:
            raise CorruptedDocumentError("pypdf library is required for PDF parsing.")

        pages_data: List[Tuple[Optional[int], Optional[str], str]] = []
        try:
            reader = pypdf.PdfReader(str(p))
            total_pages = len(reader.pages)
            if total_pages == 0:
                logger.warning(f"PDF '{p.name}' contains 0 pages.")
                return [(1, "Page 1", "")]

            for idx, page in enumerate(reader.pages):
                page_num = idx + 1
                try:
                    text = page.extract_text() or ""
                except Exception as extract_err:
                    logger.warning(f"Error extracting text from page {page_num} in '{p.name}': {extract_err}")
                    text = ""
                normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
                pages_data.append((page_num, f"Page {page_num}", normalized))

        except Exception as e:
            logger.error(f"Failed to read PDF '{p.name}': {e}")
            raise CorruptedDocumentError(f"Corrupted or unreadable PDF document '{p.name}': {str(e)}")

        return pages_data


class DocxLoader(BaseLoader):
    """Extracts text from Microsoft Word (.docx) documents via OpenXML parsing."""

    def load(self, file_path: str | Path) -> List[Tuple[Optional[int], Optional[str], str]]:
        p = Path(file_path)
        if not zipfile.is_zipfile(str(p)):
            raise CorruptedDocumentError(f"File '{p.name}' is not a valid Word (.docx) archive.")

        paragraphs = []
        try:
            with zipfile.ZipFile(str(p), "r") as z:
                if "word/document.xml" not in z.namelist():
                    raise CorruptedDocumentError(f"Missing 'word/document.xml' in '{p.name}'.")
                xml_data = z.read("word/document.xml")
                root = ET.fromstring(xml_data)

                namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                for p_node in root.findall(".//w:p", namespaces):
                    texts = [node.text for node in p_node.findall(".//w:t", namespaces) if node.text]
                    if texts:
                        para_text = "".join(texts).strip()
                        if para_text:
                            paragraphs.append(para_text)

        except zipfile.BadZipFile:
            raise CorruptedDocumentError(f"Corrupted or invalid ZIP structure in '{p.name}'.")
        except ET.ParseError as pe:
            raise CorruptedDocumentError(f"Invalid XML structure in '{p.name}': {pe}")
        except Exception as e:
            raise CorruptedDocumentError(f"Failed to parse DOCX document '{p.name}': {e}")

        full_text = "\n\n".join(paragraphs)
        return [(None, "Document Body", full_text)]


class DocumentLoaderFactory:
    """Selects and instantiates the appropriate loader based on file extension."""

    @classmethod
    def get_loader(cls, file_path: str | Path) -> BaseLoader:
        p = Path(file_path)
        ext = p.suffix.lower()
        if ext in PDF_EXTENSIONS:
            return PDFLoader()
        elif ext in DOCX_EXTENSIONS:
            return DocxLoader()
        elif ext in MARKDOWN_EXTENSIONS:
            return MarkdownLoader()
        elif ext in TEXT_EXTENSIONS or ext in CODE_EXTENSIONS:
            return TextAndCodeLoader()
        else:
            raise UnsupportedFileError(
                f"Unsupported document format '{ext}'. Supported formats include: "
                f"PDF, DOCX, TXT, MD, HTML, CSS, JSON, YAML, SQL, XML, Python, JS, TS, Java, C/C++, Dart."
            )
