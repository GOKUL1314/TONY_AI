"""
Safety guardrails, credential filtering, and path sandboxing for TONY AI Video Generation (Stage 7).
Protects against sensitive token leaks, malicious prompts, and filesystem traversal attacks.
"""
import re
from pathlib import Path
from typing import Tuple, Optional
from video_generation.errors import SafetyViolationError

# Disallowed prompt content patterns (harmful, violent, explicit, illegal)
_HARMFUL_PATTERNS = [
    re.compile(r"\b(?:csam|child\s+porn|underage\s+sexual|pedophil)\b", re.IGNORECASE),
    re.compile(r"\b(?:nsfw|nude|nudity|naked|porn|pornography|erotic|sexually\s+explicit|hentai)\b", re.IGNORECASE),
    re.compile(r"\b(?:decapitat|mutilat|dismember|gore|torture|blood\s+bath|snuff)\b", re.IGNORECASE),
    re.compile(r"\b(?:suicide|self-harm|cut\s+wrists|hang\s+myself)\b", re.IGNORECASE),
    re.compile(r"\b(?:bomb\s+making|create\s+explosive|how\s+to\s+poison|bioweapon)\b", re.IGNORECASE),
    re.compile(r"\b(?:hate\s+speech|ethnic\s+cleansing|genocide|nazi\s+propaganda|white\s+supremacy)\b", re.IGNORECASE),
]

# Sensitive credentials patterns (Hugging Face tokens, API keys, passwords, private keys)
_SECRET_PATTERNS = [
    re.compile(r"hf_[a-zA-Z0-9]{30,}", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),
    re.compile(r"(?:bearer\s+[a-zA-Z0-9\._\-]{20,})", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"(?:password|passwd|api_key|secret_key|hf_token)\s*[:=]\s*['\"]?[^\s'\"]{6,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),
]


def mask_secret(secret: Optional[str], visible_chars: int = 4) -> str:
    """Mask a token or credential for safe logging and telemetry display."""
    if not secret or not isinstance(secret, str):
        return "[NOT SET]"
    if len(secret) <= visible_chars * 2:
        return "***"
    return f"{secret[:visible_chars]}...{secret[-visible_chars:]}"


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
        raise SafetyViolationError(f"I cannot generate that video: {reason}")
    return prompt.strip()


def validate_safe_filename(filename: str, allowed_extensions: Tuple[str, ...] = (".mp4", ".webm", ".jpg", ".png")) -> str:
    """
    Ensure filename contains only safe alphanumeric and standard characters.
    Prevents path traversal, null-byte injection, and invalid Windows filename characters.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Invalid filename.")

    # Disallow path separators, traversal dots, null bytes, UNC prefixes
    if "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise ValueError(f"Path traversal detected in filename: '{filename}'")

    # Sanitize to safe basename characters: letters, digits, underscores, dashes, dots
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
        raise ValueError(f"Filename contains illegal characters: '{filename}'")

    # Check extension
    lower_name = filename.lower()
    if not any(lower_name.endswith(ext) for ext in allowed_extensions):
        raise ValueError(f"Disallowed file extension for '{filename}'. Allowed: {allowed_extensions}")

    return filename


def validate_safe_output_path(target_path: Path, allowed_dir: Path) -> Path:
    """
    Verify that target_path resolves strictly within allowed_dir.
    Prevents directory traversal or redirection to arbitrary system folders.
    """
    allowed_resolved = allowed_dir.resolve()
    target_resolved = target_path.resolve()

    try:
        target_resolved.relative_to(allowed_resolved)
    except ValueError:
        raise SafetyViolationError("Access violation: Target path is outside allowed storage directory.")

    return target_resolved


def validate_safe_image_source(image_path: Path, allowed_dirs: list[Path]) -> Path:
    """
    Verify that an input image source for image-to-video resides inside approved storage directories.
    """
    target_resolved = image_path.resolve()
    if not target_resolved.is_file():
        raise SafetyViolationError(f"Source image file does not exist: '{image_path}'")

    is_allowed = False
    for allowed in allowed_dirs:
        try:
            target_resolved.relative_to(allowed.resolve())
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise SafetyViolationError("Access violation: Source image must be an approved TONY generated asset.")

    return target_resolved
