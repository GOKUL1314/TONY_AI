"""
Intelligent and Structure-Aware Document Chunker for TONY AI (Stage 11).
Segments documents into semantic chunks preserving headings, paragraphs, page numbers,
and function boundaries with configurable size and overlap.
"""
import logging
import re
from typing import List, Tuple, Optional, Dict, Any

from knowledge.models import Chunk

logger = logging.getLogger("tony.knowledge.chunker")


class IntelligentChunker:
    """Chunks text intelligently based on document type and structural hierarchy."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        min_chunk_len: int = 20,
        overlap: Optional[int] = None,
        chunk_size_tokens: Optional[int] = None,
        chunk_overlap_tokens: Optional[int] = None
    ):
        eff_size = chunk_size_tokens if chunk_size_tokens is not None else chunk_size
        self.chunk_size = max(50, eff_size)
        eff_overlap = chunk_overlap_tokens if chunk_overlap_tokens is not None else (overlap if overlap is not None else chunk_overlap)
        self.chunk_overlap = max(0, min(eff_overlap, self.chunk_size // 2))
        self.min_chunk_len = min_chunk_len

    def chunk_text(self, text: str, doc_id: str = "doc") -> List[Chunk]:
        return self.chunk_document(doc_id, ".txt", [(None, None, text)])

    def chunk_markdown(self, text: str, doc_id: str = "doc") -> List[Chunk]:
        return self.chunk_document(doc_id, ".md", [(None, None, text)])

    def chunk_code(self, text: str, doc_id: str = "doc", language: str = "py") -> List[Chunk]:
        return self.chunk_document(doc_id, f".{language}", [(None, None, text)])

    def chunk_document(
        self,
        document_id: str,
        file_type: str,
        loaded_units: List[Tuple[Optional[int], Optional[str], str]]
    ) -> List[Chunk]:
        """
        Segment loaded units (page_number, section_header, text) into semantic Chunks.
        """
        all_chunks: List[Chunk] = []
        global_idx = 0

        for page_num, section_hdr, text in loaded_units:
            if not text or not text.strip():
                continue

            clean_text = text.strip()

            if file_type in (".md", ".markdown"):
                unit_chunks = self._chunk_markdown(clean_text, section_hdr)
            elif file_type in (".py", ".js", ".ts", ".java", ".c", ".cpp", ".dart", ".go", ".rs", ".sql"):
                unit_chunks = self._chunk_code(clean_text, section_hdr)
            else:
                unit_chunks = self._chunk_prose(clean_text, section_hdr)

            for u_text, u_sec in unit_chunks:
                if len(u_text.strip()) < self.min_chunk_len:
                    continue
                cid = f"{document_id}_chk_{global_idx:04d}"
                chunk = Chunk(
                    chunk_id=cid,
                    document_id=document_id,
                    chunk_index=global_idx,
                    text=u_text.strip(),
                    page_number=page_num,
                    section_header=u_sec or section_hdr,
                    metadata={"char_length": len(u_text.strip())}
                )
                all_chunks.append(chunk)
                global_idx += 1

        if not all_chunks and loaded_units:
            # Fallback if text was below min_chunk_len
            for page_num, section_hdr, text in loaded_units:
                if text and text.strip():
                    cid = f"{document_id}_chk_0000"
                    all_chunks.append(Chunk(
                        chunk_id=cid,
                        document_id=document_id,
                        chunk_index=0,
                        text=text.strip(),
                        page_number=page_num,
                        section_header=section_hdr,
                        metadata={"char_length": len(text.strip())}
                    ))
                    break

        return all_chunks

    def _chunk_markdown(self, text: str, default_sec: Optional[str]) -> List[Tuple[str, Optional[str]]]:
        """Split markdown by headings, preserving section context."""
        # Find heading lines (# Heading)
        heading_re = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
        parts = heading_re.split(text)

        chunks: List[Tuple[str, Optional[str]]] = []
        curr_heading = default_sec

        i = 0
        while i < len(parts):
            part = parts[i].strip()
            if not part:
                i += 1
                continue

            if heading_re.match(part):
                curr_heading = part.lstrip("#").strip()
                if i + 1 < len(parts):
                    body = parts[i + 1].strip()
                    i += 1
                else:
                    body = ""
                full_section = f"{part}\n\n{body}" if body else part
            else:
                full_section = part

            if len(full_section) <= self.chunk_size:
                chunks.append((full_section, curr_heading))
            else:
                sub_chunks = self._chunk_prose(full_section, curr_heading)
                chunks.extend(sub_chunks)

            i += 1

        return chunks if chunks else self._chunk_prose(text, default_sec)

    def _chunk_code(self, text: str, default_sec: Optional[str]) -> List[Tuple[str, Optional[str]]]:
        """Split code by function or class declarations where practical."""
        # Detect function or class starts: def, class, function, async function, pub fn, etc.
        func_re = re.compile(r"\n(?=(?:def\s+|class\s+|function\s+|async\s+function\s+|pub\s+fn\s+))", re.MULTILINE)
        blocks = func_re.split(text)

        chunks: List[Tuple[str, Optional[str]]] = []
        for block in blocks:
            blk = block.strip()
            if not blk:
                continue

            # Extract signature as section hint
            first_line = blk.split("\n", 1)[0].strip()
            sec_hint = first_line[:60] if any(first_line.startswith(k) for k in ("def ", "class ", "function ")) else default_sec

            if len(blk) <= self.chunk_size:
                chunks.append((blk, sec_hint))
            else:
                sub = self._chunk_prose(blk, sec_hint)
                chunks.extend(sub)

        return chunks if chunks else self._chunk_prose(text, default_sec)

    def _chunk_prose(self, text: str, sec_hdr: Optional[str]) -> List[Tuple[str, Optional[str]]]:
        """Sliding window chunking over paragraph and sentence boundaries."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        chunks: List[Tuple[str, Optional[str]]] = []
        current_chunk = ""

        for para in paragraphs:
            # If paragraph itself exceeds chunk_size, split by sentences
            if len(para) > self.chunk_size:
                if current_chunk:
                    chunks.append((current_chunk.strip(), sec_hdr))
                    current_chunk = ""
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 <= self.chunk_size:
                        current_chunk = f"{current_chunk} {sent}".strip()
                    else:
                        if current_chunk:
                            chunks.append((current_chunk.strip(), sec_hdr))
                            # Keep overlap from previous text
                            current_chunk = current_chunk[-self.chunk_overlap:] + " " + sent
                        else:
                            # Single sentence exceeds chunk size: hard split
                            for k in range(0, len(sent), self.chunk_size - self.chunk_overlap):
                                chunks.append((sent[k:k + self.chunk_size], sec_hdr))
            else:
                if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                    current_chunk = f"{current_chunk}\n\n{para}".strip()
                else:
                    if current_chunk:
                        chunks.append((current_chunk.strip(), sec_hdr))
                        # Retain overlap from end of current chunk
                        overlap_text = current_chunk[-self.chunk_overlap:]
                        current_chunk = f"{overlap_text}\n\n{para}".strip()
                    else:
                        current_chunk = para

        if current_chunk and current_chunk.strip():
            chunks.append((current_chunk.strip(), sec_hdr))

        return chunks
