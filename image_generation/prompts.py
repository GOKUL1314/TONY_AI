"""
Intent detection, prompt extraction, refinement, and enhancement for TONY AI Image Generation (Stage 6).
Handles natural speech/text parsing and follow-up edit prompt merging.
"""
import re
from typing import Optional, Tuple, Dict, Any

# Regex patterns for stripping conversational address prefixes
_ADDRESS_PREFIX_PATTERN = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay)?\s*tony[,!:]?\s*|(?:please\s+)?(?:can\s+you\s+)?(?:could\s+you\s+)?)+",
    re.IGNORECASE
)

# Regex patterns for stripping trailing address suffixes
_ADDRESS_SUFFIX_PATTERN = re.compile(
    r"(?:[,!:]?\s*(?:tony|please|for\s+me))+[.!?,]?$",
    re.IGNORECASE
)

# Words indicating programming/document creation rather than image generation
_CODE_DOCUMENT_EXCLUDES = {
    "script", "code", "file", "folder", "directory", "function", "class",
    "program", "plan", "summary", "list", "table", "story", "poem", "essay", "report", "conclusion"
}

# Image creation trigger regexes
_IMAGE_CREATE_PATTERNS = [
    re.compile(
        r"^(?:create|generate|make|draw|paint|produce|render|sketch)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|photograph|wallpaper|portrait|illustration|artwork|graphic|visual|scene|art)\s+(?:of|showing|depicting|with)\s+(.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:create|generate|make|draw|paint|produce|render|sketch)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|photograph|wallpaper|portrait|illustration|artwork|graphic|visual|scene|art)\s*[:\-]\s*(.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:create|generate|make|draw|paint)\s+(?:me\s+)?(?:an?\s+)?((?:cinematic|realistic|futuristic|photorealistic)\s+.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:draw|paint|sketch)\s+(?:me\s+)?(?:an?\s+)?(.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:picture|image|photo)\s+of\s+(.+)$",
        re.IGNORECASE
    ),
]

# Image edit & refinement trigger regexes
_IMAGE_EDIT_PATTERNS = [
    re.compile(
        r"^(?:make|turn|modify|edit|change|transform)\s+(?:the\s+)?(?:previous|last|that)?\s*(?:image|picture|photo)?\s+(?:into\s+|to\s+|look\s+like\s+)?(.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:make\s+it|make\s+this|make\s+that)\s+(.+)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:add|put)\s+(.+?)\s+(?:to|in|into)\s+(?:the\s+)?(?:previous|last|that)?\s*(?:image|picture|photo|scene|background)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:change|switch)\s+(?:the\s+)?(?:background|lighting|setting|style)\s+to\s+(.+)$",
        re.IGNORECASE
    ),
]

# Image regeneration trigger regexes
_IMAGE_REGEN_PATTERNS = [
    re.compile(
        r"^(?:regenerate|remake|re-generate|redo|re-render|generate\s+again)\s*(?:the\s+)?(?:previous|last|that)?\s*(?:image|picture|photo)?$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?:try\s+again|another\s+one|generate\s+another\s+one)\s*(?:for\s+the\s+last\s+image)?$",
        re.IGNORECASE
    ),
]


def clean_conversational_text(text: str) -> str:
    """Strip conversational prefixes (e.g. 'Hey Tony', 'Tony, please') and trailing punctuation."""
    cleaned = text.strip()
    cleaned = _ADDRESS_PREFIX_PATTERN.sub("", cleaned).strip()
    cleaned = _ADDRESS_SUFFIX_PATTERN.sub("", cleaned).strip()
    return cleaned.rstrip(".!?")


def detect_image_intent(text: str, has_active_image: bool = False) -> Dict[str, Any]:
    """
    Analyze user text to determine if it is an image generation, edit, or regeneration command.

    :param text: Raw input text from chat or voice.
    :param has_active_image: Whether a previous image exists in session context.
    :return: Dict containing intent info:
             {
               "intent": "create" | "edit" | "regenerate" | "none",
               "prompt": str,
               "instruction": str
             }
    """
    cleaned = clean_conversational_text(text)
    if not cleaned:
        return {"intent": "none", "prompt": "", "instruction": ""}

    # 1. Check for regeneration intent
    for pattern in _IMAGE_REGEN_PATTERNS:
        if pattern.search(cleaned):
            return {
                "intent": "regenerate" if has_active_image else "none",
                "prompt": "",
                "instruction": "regenerate"
            }

    # 2. Check for edit / refinement intent (if active image exists)
    if has_active_image:
        for pattern in _IMAGE_EDIT_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                instruction = match.group(1).strip()
                return {
                    "intent": "edit",
                    "prompt": "",
                    "instruction": instruction
                }

    # 3. Check for image creation intent
    for pattern in _IMAGE_CREATE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            extracted_prompt = match.group(1).strip()
            # Avoid false positives like "draw a conclusion" or "generate a python script"
            if extracted_prompt.lower() in ("a conclusion", "conclusions", "health", "mind"):
                continue
            words = set(re.findall(r"\b\w+\b", extracted_prompt.lower()))
            if words & _CODE_DOCUMENT_EXCLUDES:
                continue
            return {
                "intent": "create",
                "prompt": extracted_prompt,
                "instruction": ""
            }

    # 4. Standalone direct prompt fallback if user says e.g. "Create an image: a red sports car"
    if cleaned.lower().startswith("image:") or cleaned.lower().startswith("generate:"):
        direct_prompt = re.sub(r"^(?:image|generate)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        if direct_prompt:
            return {
                "intent": "create",
                "prompt": direct_prompt,
                "instruction": ""
            }

    return {"intent": "none", "prompt": "", "instruction": ""}


def merge_edit_prompt(base_prompt: str, instruction: str) -> str:
    """
    Intelligently combine a parent image prompt with a refinement or edit instruction.
    e.g., base="a red sports car in the rain", instruction="more cinematic with neon lighting"
    -> "a red sports car in the rain, more cinematic with neon lighting"
    """
    clean_base = base_prompt.strip().rstrip(".,")
    clean_inst = instruction.strip().lstrip(".,")

    # If instruction starts with "make it ", strip it
    clean_inst = re.sub(r"^(?:make\s+it|make\s+this|make\s+that)\s+", "", clean_inst, flags=re.IGNORECASE).strip()

    # If instruction says "nighttime", make it "in a nighttime setting"
    if clean_inst.lower() in ("nighttime", "night", "darker"):
        clean_inst = "nighttime atmosphere, dramatic low-key lighting"
    elif clean_inst.lower() in ("cinematic", "more cinematic"):
        clean_inst = "cinematic lighting, photorealistic composition, anamorphic flare"

    return f"{clean_base}, {clean_inst}"


def enhance_prompt(prompt: str) -> str:
    """
    Lightly enhance an image prompt with high-aesthetic fidelity keywords
    if they are not already present, preserving user subject intact.
    """
    cleaned = prompt.strip().rstrip(".,")
    lower = cleaned.lower()

    # If the user already gave a detailed prompt (> 120 chars) or specified lighting/resolution, keep it as is
    if len(cleaned) > 120 or any(kw in lower for kw in ("photorealistic", "cinematic", "octane", "8k", "detailed")):
        return cleaned

    # Append gentle quality keywords
    enhancements = "highly detailed, professional composition, cinematic lighting"
    return f"{cleaned}, {enhancements}"
