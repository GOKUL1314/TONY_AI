"""
Security and Sandboxing Policies for TONY AI Personal Knowledge & RAG Subsystem (Stage 11).
Enforces path safety, blocks dangerous file executions, detects and masks credentials,
and neutralizes prompt injection attempts within document contents.
"""
import logging
import os
from pathlib import Path
import re
from typing import Tuple, Optional, List

from knowledge.errors import KnowledgeSecurityError
from memory.extractor import is_sensitive_secret, SECRET_PATTERNS
from tools.permissions import PermissionManager, PROTECTED_SYSTEM_DIRECTORIES

logger = logging.getLogger("tony.knowledge.security")

# Strictly prohibited executable extensions
PROHIBITED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".sh", ".bash",
    ".scr", ".msi", ".dll", ".pif", ".application", ".gadget",
    ".jar", ".wsf", ".com"
}

# Prompt injection patterns in document text or queries
INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|your)?\s*(?:instructions|rules|security|protocols|safety)\b"),
    re.compile(r"(?i)\brun\s+(?:powershell|cmd|bash|shell|terminal)\b"),
    re.compile(r"(?i)\bformat\s+[a-z]:\b"),
    re.compile(r"(?i)\bdelete\s+(?:all|everything|c:\\|c:/)\b"),
    re.compile(r"(?i)\bbypass\s+(?:security|controls|sandbox|confirmation)\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:unrestricted|dan|jailbreak)\b")
]


class KnowledgeSecurityPolicy:
    """Security boundaries and sanitizer for knowledge operations."""

    @classmethod
    def validate_ingestion_path(cls, file_path: str | Path, allowed_roots: Optional[List[Path]] = None) -> Path:
        """
        Ensure file path is valid, does not employ path traversal,
        is not in a protected system directory, and is an approved safe file.
        """
        path_str = str(file_path).strip().strip("\"'")
        if not path_str:
            raise KnowledgeSecurityError("File path cannot be empty.")

        # 1. Path traversal check
        if ".." in path_str.replace("\\", "/").split("/"):
            logger.warning(f"Security Alert: Path traversal attempt in knowledge path: '{path_str}'")
            raise KnowledgeSecurityError("Path traversal ('..') is strictly prohibited.")

        resolved = Path(path_str).resolve()

        # 2. Protected system directory check
        for protected_dir in PROTECTED_SYSTEM_DIRECTORIES:
            try:
                if resolved == protected_dir or protected_dir in resolved.parents:
                    logger.warning(f"Security Alert: Ingestion attempt from protected directory '{resolved}'")
                    raise KnowledgeSecurityError(
                        f"Access to protected system location '{protected_dir.name}' is strictly denied."
                    )
            except Exception:
                continue

        # 3. Executable extension check
        ext = resolved.suffix.lower()
        if ext in PROHIBITED_EXTENSIONS:
            logger.warning(f"Security Alert: Prohibited executable format '{ext}' in knowledge ingestion.")
            raise KnowledgeSecurityError(
                f"Executable and script format '{ext}' is prohibited. Documents must be passive data only."
            )

        return resolved

    @classmethod
    def check_prompt_injection(cls, text: str) -> bool:
        """Check if text contains prompt injection or safety bypass patterns."""
        if not text:
            return False
        for pat in INJECTION_PATTERNS:
            if pat.search(text):
                return True
        return False

    @classmethod
    def sanitize_secrets(cls, text: str) -> str:
        """
        Redact sensitive secrets, API keys, and credentials from document text
        to prevent accidental exfiltration or prompt leakage.
        """
        if not text:
            return ""
        sanitized = text
        secret_regexes = [
            re.compile(r"sk-[a-zA-Z0-9_\-]{16,}"),
            re.compile(r"sk-ant-[a-zA-Z0-9_\-]{16,}"),
            re.compile(r"gh[pousr]_[a-zA-Z0-9]{30,}"),
            re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}"),
            re.compile(r"(?i)(?:api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([^\s'\"]{6,})['\"]?")
        ]
        for pat in secret_regexes:
            sanitized = pat.sub("[REDACTED_SECRET]", sanitized)
        for pat in SECRET_PATTERNS:
            sanitized = pat.sub("[REDACTED_SECRET]", sanitized)
        return sanitized

    @classmethod
    def wrap_untrusted_context(cls, chunk_text: str, filename: str, page_number: Optional[int] = None) -> str:
        """
        Wrap document text with clear untrusted content demarcation
        so the LLM treats it as passive data rather than executable instructions.
        """
        clean_text = cls.sanitize_secrets(chunk_text)
        loc = f" (Page {page_number})" if page_number is not None else ""
        return (
            f"--- BEGIN RETRIEVED PASSIVE DATA [{filename}{loc}] ---\n"
            f"{clean_text}\n"
            f"--- END RETRIEVED PASSIVE DATA [{filename}] ---"
        )


def validate_knowledge_path(file_path: str | Path, allowed_base_dir: Optional[Path] = None) -> Path:
    return KnowledgeSecurityPolicy.validate_ingestion_path(file_path)


def is_supported_extension(filename: str) -> bool:
    from knowledge.loaders import SUPPORTED_EXTENSIONS
    ext = Path(filename).suffix.lower()
    return ext in SUPPORTED_EXTENSIONS


def is_prohibited_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in PROHIBITED_EXTENSIONS


def sanitize_secrets(text: str) -> str:
    return KnowledgeSecurityPolicy.sanitize_secrets(text)


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    has_inj = KnowledgeSecurityPolicy.check_prompt_injection(text)
    return has_inj, "instruction_override" if has_inj else None


def wrap_untrusted_context(text: str, doc_name: str = "untrusted.txt", page_number: Optional[int] = None) -> str:
    return KnowledgeSecurityPolicy.wrap_untrusted_context(text, filename=doc_name, page_number=page_number)


KnowledgeSecurityValidator = KnowledgeSecurityPolicy

