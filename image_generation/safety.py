"""
Safety, guardrails, and filesystem validation for TONY AI Image Generation (Stage 6).
Blocks dangerous prompts, sensitive secrets, and directory traversal attacks.
"""
import re
from pathlib import Path
from typing import Tuple, Optional
from image_generation.errors import SafetyViolationError

# Disallowed prompt content patterns (harmful, violent, explicit, illegal)
_HARMFUL_PATTERNS = [
    re.compile(r"\b(?:csam|child\s+porn|underage\s+sexual|pedophil)\b", re.IGNORECASE),
    re.compile(r"\b(?:nsfw|nude|nudity|naked|porn|pornography|erotic|sexually\s+explicit|hentai)\b", re.IGNORECASE),
    re.compile(r"\b(?:decapitat|mutilat|dismember|gore|torture|blood\s+bath|snuff)\b", re.IGNORECASE),
    re.compile(r"\b(?:suicide|self-harm|cut\s+wrists|hang\s+myself)\b", re.IGNORECASE),
    re.compile(r"\b(?:bomb\s+making|create\s+explosive|how\s+to\s+poison|bioweapon)\b", re.IGNORECASE),
    re.compile(r"\b(?:hate\s+speech|ethnic\s+cleansing|genocide|nazi\s+propaganda|white\s+supremacy)\b", re.IGNORECASE),
]

# Sensitive credentials patterns (API keys, passwords, private keys)
_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),
    re.compile(r"(?:bearer\s+[a-zA-Z0-9\._\-]{20,})", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"(?:password|passwd|api_key|secret_key)\s*[:=]\s*['\"]?[^\s'\"]{6,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),
]


def check_prompt_safety(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Validate prompt text against content safety policies and sensitive secret filters.

    :param prompt: User-provided prompt text.
    :return: Tuple of (is_safe: bool, rejection_reason: Optional[str])
    """
    if not prompt or not prompt.strip():
        return False, "Prompt is empty."

    cleaned = prompt.strip()

    # 1. Secret / Credential screening
    for pattern in _SECRET_PATTERNS:
        if pattern.search(cleaned):
            return False, "Prompt contains sensitive credentials, API keys, or private tokens."

    # 2. Harmful / Prohibited content screening
    for pattern in _HARMFUL_PATTERNS:
        if pattern.search(cleaned):
            return False, "Prompt violates content safety policies (restricted keywords detected)."

    return True, None


def validate_prompt_or_raise(prompt: str) -> str:
    """
    Validate prompt text and raise SafetyViolationError if safety policy is violated.

    :param prompt: User prompt to validate.
    :return: Cleaned prompt string.
    :raises SafetyViolationError: If prompt is unsafe.
    """
    is_safe, reason = check_prompt_safety(prompt)
    if not is_safe:
        raise SafetyViolationError(f"I cannot generate that image: {reason}")
    return prompt.strip()


def validate_safe_filename(filename: str, allowed_extensions: Optional[Tuple[str, ...]] = None) -> str:
    """
    Ensure filename contains only safe alphanumeric and standard characters.
    Prevents path traversal, null-byte injection, and invalid Windows filename characters.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Invalid filename.")

    # Disallow path separators, traversal dots, null bytes
    if "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise ValueError(f"Path traversal detected in filename: '{filename}'")

    if allowed_extensions is None:
        pattern = r"^[a-zA-Z0-9_\-\.]+\.png$"
    else:
        ext_pattern = "|".join(re.escape(ext.lstrip(".")) for ext in allowed_extensions)
        pattern = rf"^[a-zA-Z0-9_\-\.]+\.(?:{ext_pattern})$"

    # Sanitize to safe basename characters: letters, digits, underscores, dashes, dots
    if not re.match(pattern, filename, re.IGNORECASE):
        raise ValueError(f"Filename contains illegal characters or unsupported extension: '{filename}'")

    return filename


def validate_safe_output_path(target_path: Path, allowed_dir: Path) -> Path:
    """
    Verify that target_path resolves strictly within allowed_dir.
    Prevents directory traversal or redirection to Windows system folders.
    """
    allowed_resolved = allowed_dir.resolve()
    target_resolved = target_path.resolve()

    try:
        # relative_to will raise ValueError if target_resolved is not inside allowed_resolved
        target_resolved.relative_to(allowed_resolved)
    except ValueError:
        raise SafetyViolationError(f"Access violation: Target path is outside allowed storage directory.")

    return target_resolved
