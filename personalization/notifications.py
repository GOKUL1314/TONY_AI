"""
Notification Channel Abstraction and Delivery Service for TONY AI (Stage 12).
Dispatches alerts, reminders, and proactive briefings across in-app and voice channels.
"""
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from personalization.models import Notification, UserProfile
from personalization.storage import PersonalizationDatabase
from personalization.policy import PersonalizationPolicy
from personalization.errors import RateLimitExceededError, QuietHoursError

logger = logging.getLogger("tony.personalization.notifications")


class BaseNotificationProvider(ABC):
    """Abstract interface for a notification delivery channel."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Name of the notification channel (e.g. 'in_app', 'voice')."""
        pass

    @abstractmethod
    def deliver(self, notif: Notification) -> bool:
        """Deliver the notification through this channel."""
        pass


class InAppNotificationProvider(BaseNotificationProvider):
    """Local in-app notification provider storing alerts in SQLite and notifying active listeners."""

    def __init__(self, db: PersonalizationDatabase):
        self.db = db
        self._listeners: List[Callable[[Notification], None]] = []

    @property
    def channel_name(self) -> str:
        return "in_app"

    def register_listener(self, callback: Callable[[Notification], None]):
        """Subscribe a listener to real-time notification events (e.g. SSE)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Notification], None]):
        """Unsubscribe listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def deliver(self, notif: Notification) -> bool:
        """Persist notification and broadcast to listeners."""
        try:
            self.db.add_notification(notif)
            for listener in list(self._listeners):
                try:
                    listener(notif)
                except Exception as ex:
                    logger.warning(f"Error notifying in-app listener: {ex}")
            return True
        except Exception as e:
            logger.error(f"In-app notification delivery failed: {e}")
            return False


class VoiceNotificationProvider(BaseNotificationProvider):
    """Voice alert channel using local TTS provider when available."""

    def __init__(self, tts_provider=None):
        self.tts_provider = tts_provider

    @property
    def channel_name(self) -> str:
        return "voice"

    def deliver(self, notif: Notification) -> bool:
        """Speak notification message if TTS provider is present."""
        if not self.tts_provider:
            return False
        try:
            speech_text = f"Reminder: {notif.message}"
            self.tts_provider.speak(speech_text)
            return True
        except Exception as e:
            logger.debug(f"Voice notification skipped or failed: {e}")
            return False


class NotificationService:
    """Coordinates policy checks, rate limiting, and multi-channel delivery."""

    def __init__(
        self,
        db: PersonalizationDatabase,
        providers: Optional[List[BaseNotificationProvider]] = None
    ):
        self.db = db
        self.providers: Dict[str, BaseNotificationProvider] = {}
        if providers:
            for p in providers:
                self.providers[p.channel_name] = p
        else:
            in_app = InAppNotificationProvider(db)
            self.providers[in_app.channel_name] = in_app

    def register_provider(self, provider: BaseNotificationProvider):
        """Register a notification delivery provider."""
        self.providers[provider.channel_name] = provider

    def send(
        self,
        title: str,
        message: str,
        source_type: str = "reminder",
        channels: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_delivery: bool = False
    ) -> Notification:
        """
        Send a notification, subject to quiet hours and rate limiting.
        :param force_delivery: If True (e.g. user-scheduled reminder), bypasses proactive mode toggle.
        """
        profile = self.db.get_profile()
        sent_today = self.db.count_notifications_today()

        # Check policy
        allowed, reason = PersonalizationPolicy.can_send_proactive_notification(
            profile=profile,
            notifications_sent_today=sent_today,
            is_user_reminder=force_delivery
        )

        if not allowed and not force_delivery:
            logger.info(f"Notification '{title}' suppressed by policy: {reason}")
            self.db.log_audit("notification_suppressed", {"title": title, "reason": reason})
            raise RateLimitExceededError(reason) if "limit" in str(reason).lower() else QuietHoursError(reason)

        notif_id = f"notif_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        target_channels = channels or ["in_app"]

        notif = Notification(
            id=notif_id,
            title=title,
            message=message,
            channel=",".join(target_channels),
            metadata=metadata or {},
            source_type=source_type
        )

        delivered_any = False
        for ch in target_channels:
            prov = self.providers.get(ch)
            if prov:
                ok = prov.deliver(notif)
                if ok: delivered_any = True

        # If in_app provider wasn't in target_channels, still persist record
        if "in_app" not in target_channels:
            self.db.add_notification(notif)

        self.db.log_audit("notification_delivered", {"id": notif.id, "title": title, "channels": target_channels})
        logger.info(f"Delivered notification '{title}' via {target_channels} (id: {notif.id})")
        return notif
