"""
Profile Management Layer for TONY AI Personalization Subsystem (Stage 12).
Handles non-sensitive user profile attributes, learning preferences, and style settings.
"""
import re
import logging
from typing import Dict, Any, Optional

from personalization.models import UserProfile
from personalization.storage import PersonalizationDatabase
from personalization.errors import ProfileValidationError
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.personalization.profile")

VALID_RESPONSE_LENGTHS = {"short", "medium", "detailed", "concise", "verbose"}
VALID_RESPONSE_STYLES = {"clear_and_direct", "concise", "detailed", "step_by_step", "casual", "formal", "friendly"}
VALID_LEARNING_STYLES = {"step_by_step", "hands_on", "theoretical", "visual", "project_based"}


class ProfileManager:
    """Manages reading, updating, and validating the structured user profile."""

    def __init__(self, db: PersonalizationDatabase):
        self.db = db

    def get_profile(self) -> UserProfile:
        """Fetch the current persisted user profile."""
        return self.db.get_profile()

    def update_profile(self, updates: Dict[str, Any]) -> UserProfile:
        """
        Validate and apply updates to the user profile.
        Rejects sensitive data and maintains data integrity.
        """
        self.validate_profile_updates(updates)

        current = self.get_profile()
        for k, v in updates.items():
            if hasattr(current, k):
                setattr(current, k, v)
            else:
                current.custom_attributes[k] = v

        saved = self.db.save_profile(current)
        self.db.log_audit("profile_updated", {"updated_keys": list(updates.keys())})
        logger.info(f"Updated profile with keys: {list(updates.keys())}")
        return saved

    def reset_profile(self) -> UserProfile:
        """Reset the user profile back to defaults."""
        reset_val = self.db.reset_profile()
        self.db.log_audit("profile_reset", {})
        logger.info("Reset user profile to system defaults.")
        return reset_val

    def reset_to_default(self) -> UserProfile:
        """Alias for reset_profile."""
        return self.reset_profile()

    def validate_profile_updates(self, updates: Dict[str, Any]) -> None:
        """Check for forbidden, invalid, or dangerous field values."""
        if not isinstance(updates, dict):
            raise ProfileValidationError("Profile updates must be a dictionary.")

        valid_tones = {"iron_man_witty", "professional", "friendly", "sarcastic"}

        for key, val in updates.items():
            # Check secret leakage
            if isinstance(val, str):
                if is_sensitive_secret(val):
                    raise ProfileValidationError(f"Profile attribute '{key}' contains sensitive credentials and cannot be saved.")
                # Reject command execution strings
                if re.search(r"(?i)\b(?:format\s+[a-z]:|rmdir\s+/s|powershell|cmd\.exe|bash)\b", val):
                    raise ProfileValidationError(f"Profile attribute '{key}' contains prohibited system command tokens.")

            # Validate specific structured fields
            if key in ("preferred_name", "user_name"):
                if not val or not str(val).strip():
                    raise ProfileValidationError("User name cannot be empty.")
            elif key in ("response_length", "verbosity") and isinstance(val, str):
                if val.lower() not in VALID_RESPONSE_LENGTHS:
                    raise ProfileValidationError(f"Invalid response_length: '{val}'. Expected one of: {VALID_RESPONSE_LENGTHS}")
            elif key in ("response_style", "communication_style") and isinstance(val, str):
                if val.lower() not in VALID_RESPONSE_STYLES:
                    raise ProfileValidationError(f"Invalid response_style: '{val}'. Expected one of: {VALID_RESPONSE_STYLES}")
            elif key == "tone" and isinstance(val, str):
                if val.lower() not in valid_tones:
                    raise ProfileValidationError(f"Invalid tone: '{val}'. Expected one of: {valid_tones}")
            elif key == "learning_style" and isinstance(val, str):
                if val.lower() not in VALID_LEARNING_STYLES:
                    raise ProfileValidationError(f"Invalid learning_style: '{val}'. Expected one of: {VALID_LEARNING_STYLES}")
            elif key in ("quiet_hours_start", "quiet_hours_end") and isinstance(val, str):
                if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", val):
                    raise ProfileValidationError(f"Invalid time format for '{key}': '{val}'. Expected HH:MM (24-hour).")
            elif key == "max_daily_notifications" and isinstance(val, int):
                if val < 0 or val > 100:
                    raise ProfileValidationError("max_daily_notifications must be between 0 and 100.")
