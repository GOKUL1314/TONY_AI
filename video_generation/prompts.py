"""
Natural language prompt processing, intent recognition, parameter extraction,
and prompt refinement for TONY AI Video Generation (Stage 7).
"""
import re
from typing import Dict, Any, Optional, Tuple

# Positive triggers for Text-to-Video generation
_T2V_PATTERNS = [
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:create|generate|make|render|produce)\s+(?:an?\s+)?(?:cinematic\s+|short\s+|realistic\s+)?(?:video|animation|clip)\s+(?:of|showing|about|depicting)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:create|generate|make)\s+(?:a\s+)?(\d+)\s*(?:second|sec)\s+video\s+(?:of|showing|about|depicting)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:video\s+of|generate\s+video:?)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?create\s+(?:a\s+)?cinematic\s+scene\s+(?:of|with)\s+(.+)$", re.IGNORECASE),
]

# Positive triggers for Image-to-Video generation
_I2V_PATTERNS = [
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?animate\s+(?:this|the|the\s+previous|the\s+last|the\s+generated)\s+image(?:[.!?,]?)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?turn\s+(?:this|the|the\s+previous|the\s+generated)\s+(?:image|picture|photo)\s+into\s+(?:a\s+)?(?:short\s+)?(?:moving\s+)?video(?:[.!?,]?)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?make\s+(?:this|the|the\s+previous|the\s+generated)\s+(?:image|picture)\s+(?:come\s+alive|move)(?:[.!?,]?)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:make|create|generate)\s+(?:a\s+)?video\s+from\s+(?:this|the|the\s+previous|the\s+generated)\s+image(?:[.!?,]?)$", re.IGNORECASE),
    re.compile(r"^(?:tony[,!:]?\s*)?(?:please\s+)?turn\s+the\s+generated\s+image\s+into\s+a\s+moving\s+video(?:[.!?,]?)$", re.IGNORECASE),
]

# Negative patterns (conversational/informational queries that must NOT trigger generation)
_INFORMATIONAL_PATTERNS = [
    re.compile(r"^(?:what|how|why|tell\s+me|can\s+you\s+explain|explain)\b.*(?:video\s+generation|video\s+model|video\s+editing)", re.IGNORECASE),
    re.compile(r"\b(?:what\s+is\s+video\s+generation|how\s+does\s+video\s+generation\s+work)\b", re.IGNORECASE),
    re.compile(r"\b(?:do\s+you\s+support\s+video|can\s+you\s+make\s+videos\??)\b", re.IGNORECASE),
]


def detect_video_intent(text: str, has_active_image: bool = False) -> Dict[str, Any]:
    """
    Detect whether conversational user input requests video generation.

    :param text: Raw user message.
    :param has_active_image: Whether an active Stage 6 image exists in memory.
    :return: Dict containing intent ('text_to_video', 'image_to_video', 'none'),
             extracted prompt, duration, aspect_ratio, and parameters.
    """
    if not text or not isinstance(text, str):
        return {"intent": "none"}

    cleaned = text.strip()

    # 1. Check for informational/conversational questions about video
    for pattern in _INFORMATIONAL_PATTERNS:
        if pattern.search(cleaned):
            return {"intent": "none"}

    # 2. Check Image-to-Video patterns
    for pattern in _I2V_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return {
                "intent": "image_to_video",
                "raw_query": cleaned,
                "has_active_image": has_active_image
            }

    # 3. Check Text-to-Video patterns
    for pattern in _T2V_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            groups = match.groups()
            duration = 5
            extracted_prompt = ""

            if len(groups) == 2:
                # Group 1: duration digits, Group 2: prompt
                try:
                    duration = int(groups[0])
                except (ValueError, TypeError):
                    duration = 5
                extracted_prompt = groups[1].strip()
            elif len(groups) == 1:
                extracted_prompt = groups[0].strip()

            # Further extract duration / resolution embedded in extracted_prompt
            extracted_prompt, duration_override, width, height = parse_prompt_parameters(extracted_prompt)
            if duration_override:
                duration = duration_override

            return {
                "intent": "text_to_video",
                "prompt": extracted_prompt,
                "duration": duration,
                "width": width,
                "height": height,
                "raw_query": cleaned
            }

    return {"intent": "none"}


def parse_prompt_parameters(prompt: str) -> Tuple[str, Optional[int], int, int]:
    """
    Parse inline duration and aspect ratio keywords from a prompt.
    Returns: (cleaned_prompt, duration, width, height)
    """
    cleaned = prompt
    duration = None
    width = 512
    height = 512

    # Check duration like "5 seconds", "10s", "2 minutes"
    dur_match = re.search(r"\b(\d+)\s*(?:seconds?|secs?)\b", cleaned, re.IGNORECASE)
    if dur_match:
        try:
            duration = int(dur_match.group(1))
            cleaned = re.sub(r"\b\d+\s*(?:seconds?|secs?)\b", "", cleaned, flags=re.IGNORECASE).strip()
        except ValueError:
            pass

    # Check for minutes (e.g. 2 minutes -> 120s)
    min_match = re.search(r"\b(\d+)\s*(?:minutes?|mins?)\b", cleaned, re.IGNORECASE)
    if min_match:
        try:
            duration = int(min_match.group(1)) * 60
            cleaned = re.sub(r"\b\d+\s*(?:minutes?|mins?)\b", "", cleaned, flags=re.IGNORECASE).strip()
        except ValueError:
            pass

    # Check aspect ratios
    if re.search(r"\b(?:cinematic|16:9|widescreen|landscape)\b", cleaned, re.IGNORECASE):
        width = 768
        height = 432
        cleaned = re.sub(r"\b(?:cinematic|16:9|widescreen|landscape)\b", "", cleaned, flags=re.IGNORECASE).strip()
    elif re.search(r"\b(?:vertical|portrait|9:16|reels|tiktok)\b", cleaned, re.IGNORECASE):
        width = 432
        height = 768
        cleaned = re.sub(r"\b(?:vertical|portrait|9:16|reels|tiktok)\b", "", cleaned, flags=re.IGNORECASE).strip()

    # Clean redundant punctuation / spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".,;:!")
    return cleaned, duration, width, height


def enhance_video_prompt(prompt: str) -> str:
    """
    Apply subtle cinematic prompt enhancement for video diffusion models.
    Preserves subjects, colors, and camera motion without changing user intent.
    """
    cleaned = prompt.strip()
    if not cleaned:
        return cleaned

    # Check if prompt already has cinematic keywords
    keywords = ["cinematic", "photorealistic", "motion", "smooth", "4k", "detailed", "lighting"]
    has_keywords = any(kw in cleaned.lower() for kw in keywords)

    if not has_keywords:
        return f"{cleaned}, smooth cinematic camera motion, highly detailed, photorealistic lighting"
    return cleaned
