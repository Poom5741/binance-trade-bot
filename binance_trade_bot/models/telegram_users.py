from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from .base import Base


class UserRole(Enum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"
    API_USER = "API_USER"


class UserStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BANNED = "BANNED"
    PENDING = "PENDING"


class TelegramUsers(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True)

    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    role = Column(SQLAlchemyEnum(UserRole), default=UserRole.VIEWER)
    status = Column(SQLAlchemyEnum(UserStatus), default=UserStatus.PENDING)

    is_bot = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)

    language_code = Column(String, nullable=True)
    timezone = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)
    verified_at = Column(DateTime)

    api_key = Column(String, unique=True, nullable=True)
    api_key_expires_at = Column(DateTime, nullable=True)

    notification_settings = Column(Text, nullable=True)  # JSON string for notification preferences
    trading_preferences = Column(Text, nullable=True)  # JSON string for trading preferences

    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)

    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    def __init__(
        self,
        telegram_id: str,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        role: UserRole = UserRole.VIEWER,
        is_bot: bool = False,
        language_code: str = None,
        timezone: str = None,
    ):
        self.telegram_id = telegram_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_bot = is_bot
        self.language_code = language_code
        self.timezone = timezone

    def activate(self):
        self.status = UserStatus.ACTIVE
        self.verified_at = datetime.utcnow()

    def deactivate(self):
        self.status = UserStatus.INACTIVE

    def ban(self):
        self.status = UserStatus.BANNED

    def set_pending(self):
        self.status = UserStatus.PENDING

    def update_last_login(self):
        self.last_login_at = datetime.utcnow()
        self.failed_login_attempts = 0
        self.locked_until = None

    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(hours=1)

    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None

    def enable_two_factor(self, secret: str):
        self.two_factor_enabled = True
        self.two_factor_secret = secret

    def disable_two_factor(self):
        self.two_factor_enabled = False
        self.two_factor_secret = None

    def generate_api_key(self, expires_in_days: int = 30):
        import secrets
        import uuid
        from datetime import timedelta

        self.api_key = str(uuid.uuid4())
        self.api_key_expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        return self.api_key

    def revoke_api_key(self):
        self.api_key = None
        self.api_key_expires_at = None

    def is_api_key_valid(self):
        if not self.api_key or not self.api_key_expires_at:
            return False
        return self.api_key_expires_at > datetime.utcnow()

    def update_notification_settings(self, settings: dict):
        import json
        self.notification_settings = json.dumps(settings)

    def update_trading_preferences(self, preferences: dict):
        import json
        self.trading_preferences = json.dumps(preferences)

    def get_notification_settings(self):
        import json
        if self.notification_settings:
            return json.loads(self.notification_settings)
        return {}

    def get_trading_preferences(self):
        import json
        if self.trading_preferences:
            return json.loads(self.trading_preferences)
        return {}

    def has_permission(self, required_role: UserRole):
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.API_USER: 1,
            UserRole.TRADER: 2,
            UserRole.ADMIN: 3,
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(required_role, 0)

    def info(self):
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "role": self.role.value,
            "status": self.status.value,
            "is_bot": self.is_bot,
            "is_premium": self.is_premium,
            "language_code": self.language_code,
            "timezone": self.timezone,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "api_key_exists": bool(self.api_key),
            "api_key_expires_at": self.api_key_expires_at.isoformat() if self.api_key_expires_at else None,
            "two_factor_enabled": self.two_factor_enabled,
            "failed_login_attempts": self.failed_login_attempts,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
        }