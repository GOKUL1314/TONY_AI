"""
Source Citation and Attribution Manager for TONY AI Personal Knowledge (Stage 11).
Generates verifiable, transparent source references linking answers directly to
specific documents, pages, sections, and chunk IDs without fabrication.
"""
import logging
from typing import List, Optional, Any

from knowledge.models import Chunk, Document, Citation
from knowledge.security import KnowledgeSecurityPolicy

logger = logging.getLogger("tony.knowledge.citations")


class CitationManager:
    """Creates and formats verifiable source citations from retrieved knowledge chunks."""

    @classmethod
    def create_citation(
        cls,
        index: int,
        chunk: Chunk,
        document: Document,
        snippet_len: int = 150
    ) -> Citation:
        """Create a single grounded Citation record."""
        # Clean snippet of credentials
        clean_text = KnowledgeSecurityPolicy.sanitize_secrets(chunk.text)
        snippet = clean_text[:snippet_len].replace("\n", " ").strip()
        if len(clean_text) > snippet_len:
            snippet += "..."

        return Citation(
            citation_id=f"[{index}]",
            filename=document.filename,
            document_id=document.document_id,
            chunk_id=chunk.chunk_id,
            page_number=chunk.page_number,
            section_header=chunk.section_header,
            snippet=snippet
        )

    @classmethod
    def format_citations_block(cls, citations: List[Citation]) -> str:
        """Format list of citations into a clean, markdown-friendly block."""
        if not citations:
            return ""

        lines = ["\n\nSources:"]
        for c in citations:
            loc = []
            if c.page_number is not None:
                loc.append(f"Page {c.page_number}")
            if c.section_header and c.section_header != c.filename:
                loc.append(f"Section: {c.section_header}")

            loc_str = f" — {', '.join(loc)}" if loc else ""
            lines.append(f"{c.citation_id} {c.filename}{loc_str}")

        return "\n".join(lines)

    @classmethod
    def generate_citations(cls, search_results: List[Any]) -> List[Citation]:
        citations = []
        for idx, r in enumerate(search_results, 1):
            doc_name = getattr(r, "document_name", "Document")
            doc_id = getattr(r, "document_id", "")
            chunk_id = getattr(r, "chunk_id", "")
            page_no = getattr(r, "page_number", None)
            sec = getattr(r, "section_title", getattr(r, "section_header", None))
            text = getattr(r, "text", "")
            snippet = text[:150].replace("\n", " ").strip()
            if len(text) > 150:
                snippet += "..."
            citations.append(Citation(
                citation_id=f"[{idx}]",
                filename=doc_name,
                document_id=doc_id,
                chunk_id=chunk_id,
                page_number=page_no,
                section_header=sec,
                snippet=snippet
            ))
        return citations

    @classmethod
    def format_citations_markdown(cls, citations: List[Citation]) -> str:
        return cls.format_citations_block(citations)


CitationGenerator = CitationManager

