"""
Preference Management Layer for TONY AI Personalization Subsystem (Stage 12).
Handles granular user preferences with source and confidence attribution.
"""
import re
import logging
from typing import Dict, Any, List, Optional

from personalization.models import UserPreference
from personalization.storage import PersonalizationDatabase
from personalization.errors import PersonalizationError, PreferenceNotFoundError
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.personalization.preferences")


class PreferencesManager:
    """Manages individual user preferences with metadata and confidence scoring."""

    def __init__(self, db: PersonalizationDatabase):
        self.db = db

    def get_preference(self, key: str) -> Optional[UserPreference]:
        """Fetch a specific preference by its unique key."""
        return self.db.get_preference(key)

    def set_preference(
        self,
        key: str,
        value: Any,
        category: str = "general",
        source: str = "explicit_user",
        confidence: float = 1.0
    ) -> UserPreference:
        """
        Store or update a user preference.
        Validates that secrets or command injections are rejected.
        """
        clean_key = key.strip().lower()
        if not clean_key:
            raise PersonalizationError("Preference key cannot be empty.")

        # Validate security
        if isinstance(value, str):
            if is_sensitive_secret(value):
                raise PersonalizationError(f"Preference '{clean_key}' contains sensitive credentials and cannot be saved.")
            if re.search(r"(?i)\b(?:format\s+[a-z]:|rmdir\s+/s|powershell|cmd\.exe|bash)\b", value):
                raise PersonalizationError(f"Preference '{clean_key}' contains prohibited system command tokens.")

        conf = max(0.0, min(1.0, float(confidence)))

        pref = UserPreference(
            key=clean_key,
            value=value,
            category=category.strip().lower(),
            source=source.strip().lower(),
            confidence=conf
        )

        saved = self.db.set_preference(pref)
        self.db.log_audit("preference_set", {"key": clean_key, "category": category, "source": source})
        logger.info(f"Stored preference '{clean_key}' ({category}) from {source} with confidence {conf}")
        return saved

    def delete_preference(self, key: str) -> bool:
        """Remove a preference by key."""
        clean_key = key.strip().lower()
        deleted = self.db.delete_preference(clean_key)
        if deleted:
            self.db.log_audit("preference_deleted", {"key": clean_key})
            logger.info(f"Deleted preference '{clean_key}'.")
        return deleted

    def list_preferences(self, category: Optional[str] = None) -> List[UserPreference]:
        """List all stored preferences, optionally filtered by category."""
        return self.db.list_preferences(category=category)

    def clear_preferences(self) -> int:
        """Clear all stored preferences."""
        count = self.db.clear_preferences()
        self.db.log_audit("preferences_cleared", {"count": count})
        logger.info(f"Cleared {count} stored preferences.")
        return count
