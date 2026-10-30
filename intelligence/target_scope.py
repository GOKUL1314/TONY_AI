"""
Target Scope & Local Storage Classifier for TONY AI.
Analyzes natural-language requests to determine whether they target:
1. Local storage (files, folders, documents on the local computer)
2. External topics (research, courses, tutorials, products, recipes, news, etc.)
3. Compound / multi-goal requests requiring decomposition into sub-goals.

Strictly enforces that 'search_files' requires positive evidence of a local target.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any

logger = logging.getLogger("tony.intelligence.target_scope")

# File extensions recognized as direct evidence of local file references
KNOWN_FILE_EXTENSIONS = {
    "py", "txt", "pdf", "docx", "doc", "json", "csv", "xlsx", "xls",
    "md", "png", "jpg", "jpeg", "gif", "mp4", "mp3", "wav", "zip",
    "tar", "gz", "7z", "log", "env", "ini", "xml", "html", "css",
    "js", "ts", "jsx", "tsx", "c", "cpp", "h", "java", "sql", "sh", "bat"
}

# Regex to detect file extension in tokens, e.g. "report.pdf", "script.py", "*.mp4"
FILE_EXT_RE = re.compile(
    r"\b[a-zA-Z0-9_\-\*]+\.(" + "|".join(KNOWN_FILE_EXTENSIONS) + r")\b",
    re.IGNORECASE
)

# Explicit local container phrases
LOCAL_CONTAINER_RE = re.compile(
    r"\b(?:on\s+(?:my\s+)?(?:computer|pc|machine|laptop|desktop|system|drive)|"
    r"in\s+(?:my\s+)?(?:documents?|downloads?|desktop|folder|directory|storage|files?)|"
    r"on\s+this\s+(?:computer|pc|machine)|locally|on\s+disk)\b",
    re.IGNORECASE
)

# Local document / file nouns with personal ownership or file specification
LOCAL_NOUN_RE = re.compile(
    r"\b(?:my|local|saved|stored)\s+(?:[a-zA-Z0-9_\-]+\s+)?(?:"
    r"notes?|resume|cv|files?|documents?|docs?|scripts?|code|spreadsheets?|"
    r"records?|tax\s+records?|presentations?|photos?|receipts?|invoices?|"
    r"paper|essay|draft|homework|project)\b|"
    r"\b(?:files?|documents?)\s+(?:called|named|matching|containing)\b|"
    r"\b(?:python\s+scripts?|text\s+files?|pdf\s+files?|word\s+documents?)\b",
    re.IGNORECASE
)

# External / research / recommendation markers
EXTERNAL_MARKER_RE = re.compile(
    r"\b(?:the\s+best|best|top|good|great|latest|newest|cheapest|popular|recommended|"
    r"course|courses|tutorial|tutorials|class|classes|curriculum|"
    r"news|headline|headlines|article|articles|"
    r"laptop|laptops|phone|phones|gadget|gadgets|deal|deals|price|under\s+\$?\d+|"
    r"recipe|recipes|restaurant|restaurants|hotel|hotels|flight|flights|"
    r"online|on\s+the\s+web|on\s+the\s+internet|on\s+youtube|on\s+google|"
    r"available\s+right\s+now|for\s+sale)\b",
    re.IGNORECASE
)

# Leading conversational prefixes to remove
CLEAN_PREFIX_RE = re.compile(
    r"^(?:tony[,!:]?\s*|hey\s+tony[,!:]?\s*|hi\s+tony[,!:]?\s*|please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?)+",
    re.IGNORECASE
)

# Conjunctions followed by action verbs that signal compound / multi-step requests
ACTION_VERBS = {
    "create", "make", "summarize", "explain", "compare", "turn", "open",
    "tell", "save", "remember", "build", "write", "develop", "analyze",
    "generate", "design", "draft", "formulate", "recommend", "evaluate",
    "find", "search", "look", "review", "organize", "plan", "structure"
}

COMPOUND_SPLIT_RE = re.compile(
    r",\s*(?:and|then)\s+|\s+(?:and|then)\s+|(?:,\s*)",
    re.IGNORECASE
)


@dataclass
class TargetScope:
    """Diagnostic outcome of target-scope analysis."""
    is_local_file: bool
    is_compound: bool = False
    clauses: List[str] = field(default_factory=list)
    query: Optional[str] = None
    location: str = "all"
    primary_goal: Optional[str] = None
    sub_goals: List[str] = field(default_factory=list)
    rejected_tool: Optional[str] = None
    rejection_reason: Optional[str] = None
    confidence: float = 0.95


def split_compound_request(text: str) -> List[str]:
    """
    Split a request into constituent action clauses if compound conjunctions
    or comma-separated phrases are followed by recognized action verbs.
    """
    clean = text.strip()
    clean = CLEAN_PREFIX_RE.sub("", clean).strip()
    if not clean:
        return []

    # First, test for multi-part pattern with commas and conjunctions:
    # e.g. "Find X, compare Y, and create Z"
    # or "Find X, compare Y and create Z"
    three_part_match = re.match(
        r"^(.+?),\s*([a-zA-Z]+(?:\s+.+?)?),\s*(?:and|then)\s+([a-zA-Z]+.+)$",
        clean,
        re.IGNORECASE
    )
    if three_part_match:
        c1 = three_part_match.group(1).strip()
        c2 = three_part_match.group(2).strip()
        c3 = three_part_match.group(3).strip()
        v2 = c2.split()[0].lower() if c2 else ""
        v3 = c3.split()[0].lower() if c3 else ""
        if (v2 in ACTION_VERBS or any(v2.startswith(v) for v in ACTION_VERBS)) and \
           (v3 in ACTION_VERBS or any(v3.startswith(v) for v in ACTION_VERBS)):
            return [c1, c2, c3]

    # Two-part splitting by ", and", " and", " then", or ", then"
    parts = re.split(r",\s*(?:and|then)\s+|\s+(?:and|then)\s+", clean, flags=re.IGNORECASE)
    if len(parts) > 1:
        # Check if the subsequent parts start with action verbs
        valid_compound = True
        for part in parts[1:]:
            first_word = part.strip().split()[0].lower() if part.strip() else ""
            if first_word not in ACTION_VERBS and not any(part.lower().strip().startswith(v) for v in ACTION_VERBS):
                valid_compound = False
                break
        if valid_compound:
            # Check if parts[0] itself has a comma-separated action clause (e.g. "Find X, compare Y")
            if "," in parts[0]:
                sub_parts = [p.strip() for p in parts[0].split(",") if p.strip()]
                if len(sub_parts) > 1:
                    v_sub = sub_parts[-1].split()[0].lower() if sub_parts[-1] else ""
                    if v_sub in ACTION_VERBS or any(v_sub.startswith(v) for v in ACTION_VERBS):
                        return sub_parts + [p.strip() for p in parts[1:]]
            return [p.strip() for p in parts if p.strip()]

    return [clean]


def analyze_target_scope(text: str) -> TargetScope:
    """
    Analyze natural language input to determine if it refers to local filesystem storage,
    an external research/knowledge topic, or a compound multi-goal request.
    """
    clean = text.strip()
    clean = CLEAN_PREFIX_RE.sub("", clean).strip()
    if not clean:
        return TargetScope(
            is_local_file=False,
            rejected_tool="search_files",
            rejection_reason="Empty input"
        )

    clauses = split_compound_request(clean)
    is_compound = len(clauses) > 1

    # Evaluate the first clause (or single text) for local file evidence
    first_clause = clauses[0].strip().rstrip(".!?,")
    has_file_ext = bool(FILE_EXT_RE.search(first_clause))
    has_local_container = bool(LOCAL_CONTAINER_RE.search(first_clause))
    has_local_noun = bool(LOCAL_NOUN_RE.search(first_clause))
    has_external_markers = bool(EXTERNAL_MARKER_RE.search(first_clause))

    # Check explicit search directives
    explicit_search_match = re.search(
        r"^(?:search|find)\s+(?:my\s+)?(?:computer|pc|machine|laptop|desktop|disk|files?|documents?|folder)\s+for\s+(.+)$",
        first_clause,
        re.IGNORECASE
    )
    explicit_file_search_match = re.search(
        r"^(?:search|find)\s+(?:for\s+)?(?:files?\s+)?(?:called|named|matching)\s+(.+)$",
        first_clause,
        re.IGNORECASE
    )

    is_local = False
    query = None
    location = "all"
    rejection_reason = None

    if explicit_search_match:
        is_local = True
        query = explicit_search_match.group(1).strip().strip("'\"")
        # Extract location if mentioned
        if re.search(r"\bdocuments?\b", first_clause, re.IGNORECASE):
            location = "documents"
        elif re.search(r"\bdesktop\b", first_clause, re.IGNORECASE):
            location = "desktop"
        elif re.search(r"\bdownloads?\b", first_clause, re.IGNORECASE):
            location = "downloads"
    elif explicit_file_search_match:
        is_local = True
        query = explicit_file_search_match.group(1).strip().strip("'\"")
    elif has_file_ext:
        is_local = True
        # Extract filename or search token
        ext_match = FILE_EXT_RE.search(first_clause)
        query = ext_match.group(0).strip() if ext_match else first_clause
    elif has_local_noun and not has_external_markers:
        is_local = True
        # Extract target noun
        m = re.search(
            r"^(?:find\s+(?:my\s+)?|search\s+(?:for\s+)?|where\s+is\s+(?:my\s+)?)(.+?)(?:\s+(?:in|on)\s+(.+))?$",
            first_clause,
            re.IGNORECASE
        )
        if m:
            query = m.group(1).strip().strip("'\"")
            if m.group(2):
                loc_raw = m.group(2).lower()
                if "doc" in loc_raw:
                    location = "documents"
                elif "desk" in loc_raw:
                    location = "desktop"
                elif "down" in loc_raw:
                    location = "downloads"
        else:
            query = first_clause
    elif has_local_container and not has_external_markers:
        is_local = True
        m = re.search(
            r"^(?:find\s+(?:my\s+)?|search\s+(?:for\s+)?|where\s+is\s+(?:my\s+)?)(.+?)(?:\s+(?:in|on)\s+(.+))?$",
            first_clause,
            re.IGNORECASE
        )
        if m:
            query = m.group(1).strip().strip("'\"")
            if m.group(2):
                loc_raw = m.group(2).lower()
                if "doc" in loc_raw:
                    location = "documents"
                elif "desk" in loc_raw:
                    location = "desktop"
                elif "down" in loc_raw:
                    location = "downloads"
        else:
            query = first_clause
    else:
        # Not a local file target
        is_local = False
        rejection_reason = "No local file target detected; request is for general research, recommendation, or external knowledge."

    # If compound, extract sub-goals
    sub_goals = []
    primary_goal = None
    if is_compound:
        primary_goal = _infer_primary_goal(clauses, is_local)
        for i, c in enumerate(clauses):
            sub_goals.append(_infer_sub_goal(c, i, is_local))
    elif not is_local:
        primary_goal = _infer_primary_goal([first_clause], is_local=False)
        sub_goals.append(_infer_sub_goal(first_clause, 0, is_local=False))

    rejected_tool = "search_files" if not is_local else None
    if query:
        query = query.strip(" '\"").rstrip(".!?,")

    return TargetScope(
        is_local_file=is_local,
        is_compound=is_compound,
        clauses=clauses,
        query=query,
        location=location,
        primary_goal=primary_goal,
        sub_goals=sub_goals,
        rejected_tool=rejected_tool,
        rejection_reason=rejection_reason,
        confidence=0.95
    )


def _infer_primary_goal(clauses: List[str], is_local: bool) -> str:
    """Infer high-level primary goal label from clauses."""
    full = " ".join(clauses).lower()
    if "python" in full and ("course" in full or "learn" in full or "plan" in full):
        return "learn_python"
    if "course" in full or "study" in full:
        return "education_planning"
    if is_local:
        return "local_file_processing"
    if "laptop" in full or "product" in full:
        return "product_research"
    if "news" in full:
        return "news_research"
    if "recipe" in full:
        return "recipe_discovery"
    return "general_task"


def _infer_sub_goal(clause: str, index: int, is_local: bool) -> str:
    """Infer structured sub-goal label for a specific clause."""
    lower = clause.lower().strip()
    if index == 0:
        if is_local:
            return "search_local_files"
        if "course" in lower:
            return "research_python_courses" if "python" in lower else "research_courses"
        if "news" in lower:
            return "research_news"
        if "laptop" in lower:
            return "research_laptops"
        if "recipe" in lower:
            return "find_recipe"
        return "research_topic"

    if "compare" in lower:
        return "compare_courses" if "course" in lower or index == 1 else "compare_options"
    if "plan" in lower:
        return "create_learning_plan" if "learn" in lower or "month" in lower else "create_study_plan"
    if "summarize" in lower:
        return "summarize_content"
    if "explain" in lower:
        return "explain_content"

    return f"execute_step_{index + 1}"


def is_live_web_search_available(tool_registry: Any = None) -> bool:
    """
    Check whether a real, verified live web-search tool is registered and available.
    Returns False unless a verified tool 'web_search' is actively registered.
    """
    if tool_registry:
        if hasattr(tool_registry, "is_registered") and tool_registry.is_registered("web_search"):
            return True
        if hasattr(tool_registry, "get_tool_names") and "web_search" in tool_registry.get_tool_names():
            return True
    return False


def get_research_grounding_directive(tool_registry: Any = None) -> str:
    """
    Construct operational grounding guidelines for research steps.
    If live web search is unavailable, strictly prevents hallucinations of live search,
    real-time checking, fabricated ratings, and dynamic pricing.
    """
    if is_live_web_search_available(tool_registry):
        return (
            "LIVE WEB RESEARCH DIRECTIVE:\n"
            "- Perform verified live web search using the registered search tool.\n"
            "- Retrieve and compare relevant sources, extracting concrete facts.\n"
            "- Clearly distinguish source facts from your own synthesis.\n"
            "- Provide direct source links and cite where information may change."
        )
    return (
        "RESEARCH GROUNDING DIRECTIVE (CAPABILITY BOUNDARY):\n"
        "- Live web search and real-time internet browsing are CURRENTLY UNAVAILABLE in this environment.\n"
        "- You MUST explicitly state that live web search is unavailable before or during your answer.\n"
        "- Provide recommendations and information based STRICTLY on your internal training/knowledge base.\n"
        "- NEVER claim you 'researched the web', 'checked websites', or verified current live availability.\n"
        "- NEVER fabricate real-time ratings (e.g. do not invent '4.8/5 on Coursera'), current prices, or live enrollment status.\n"
        "- Explicitly note that course details, pricing, and ratings are subject to change over time."
    )
