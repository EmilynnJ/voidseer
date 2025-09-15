from datetime import datetime, timedelta
from enum import Enum as PyEnum
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Enum, 
    Integer, Float, Text, Date, event
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, ENUM
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func, expression
from passlib.context import CryptContext
from pydantic import EmailStr, validator, BaseModel
import phonenumbers

from app.core.database import Base, get_db_session
from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRole(str, PyEnum):
    CLIENT = "client"
    READER = "reader"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SUPPORT = "support"

class UserStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending_verification"
    BANNED = "banned"

class UserAuthProvider(str, PyEnum):
    EMAIL = "email"
    GOOGLE = "google"
    FACEBOOK = "facebook"
    APPLE = "apple"
    CLERK = "clerk"

class User(Base):
    """User model representing all users in the system."""
    __tablename__ = "users"
    
    # Core identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Authentication and identification
    clerk_id: Mapped[Optional[str]] = mapped_column(
        String, 
        unique=True, 
        index=True, 
        nullable=True
    )
    email: Mapped[str] = mapped_column(
        String, 
        unique=True, 
        index=True, 
        nullable=False
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # User information
    username: Mapped[Optional[str]] = mapped_column(
        String, 
        unique=True, 
        index=True, 
        nullable=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Authentication
    hashed_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    auth_provider: Mapped[UserAuthProvider] = mapped_column(
        ENUM(UserAuthProvider, name="user_auth_provider"),
        default=UserAuthProvider.EMAIL
    )
    auth_provider_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Security
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_failed_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Preferences
    preferred_language: Mapped[str] = mapped_column(String, default="en")
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    notification_preferences: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default={
            "email": True,
            "push": True,
            "sms": False,
            "marketing_emails": True
        }
    )
    
    # Roles and permissions
    role: Mapped[UserRole] = mapped_column(
        ENUM(UserRole, name="user_role"),
        default=UserRole.CLIENT
    )
    permissions: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=[]
    )
    status: Mapped[UserStatus] = mapped_column(
        ENUM(UserStatus, name="user_status"),
        default=UserStatus.PENDING
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now()
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships (lazy loading by default)
    reader_profile: Mapped[Optional["ReaderProfile"]] = relationship(
        "ReaderProfile", 
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    client_profile: Mapped[Optional["ClientProfile"]] = relationship(
        "ClientProfile", 
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Security tokens (for password reset, email verification, etc.)
    security_tokens: Mapped[List["SecurityToken"]] = relationship(
        "SecurityToken", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Methods
    def set_password(self, password: str) -> None:
        """Hash and set the user's password."""
        self.hashed_password = pwd_context.hash(password)
        self.password_changed_at = datetime.utcnow()
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        if not self.hashed_password:
            return False
        return pwd_context.verify(password, self.hashed_password)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        if self.is_superuser:
            return True
        return permission in self.permissions
    
    def is_locked(self) -> bool:
        """Check if the user account is locked due to too many failed attempts."""
        if not self.last_failed_login:
            return False
            
        lockout_time = settings.ACCOUNT_LOCKOUT_MINUTES
        if lockout_time <= 0:
            return False
            
        time_since_failed = datetime.utcnow() - self.last_failed_login
        return (
            self.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS and
            time_since_failed < timedelta(minutes=lockout_time)
        )
    
    def record_failed_login(self) -> None:
        """Record a failed login attempt."""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
    
    def record_successful_login(self) -> None:
        """Record a successful login."""
        self.failed_login_attempts = 0
        self.last_login = datetime.utcnow()
    
    def get_full_name(self) -> str:
        """Return the user's full name if available, otherwise the email."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email
    
    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
    
    # Pydantic model for API responses
    class Model(BaseModel):
        id: uuid.UUID
        email: str
        username: Optional[str]
        first_name: Optional[str]
        last_name: Optional[str]
        display_name: Optional[str]
        role: UserRole
        status: UserStatus
        is_active: bool
        is_verified: bool
        created_at: datetime
        
        class Config:
            from_attributes = True

# Event listeners
@event.listens_for(User, 'before_insert')
@event.listens_for(User, 'before_update')
def update_display_name(mapper, connection, target):
    """Update display name if not set."""
    if not target.display_name:
        if target.first_name and target.last_name:
            target.display_name = f"{target.first_name} {target.last_name}"
        elif target.first_name:
            target.display_name = target.first_name
        elif target.username:
            target.display_name = target.username
        else:
            target.display_name = target.email.split('@')[0]

@event.listens_for(User, 'before_insert')
def set_default_username(mapper, connection, target):
    """Set a default username if not provided."""
    if not target.username and target.email:
        base_username = target.email.split('@')[0]
        # TODO: Add logic to ensure username is unique
        target.username = base_username
    last_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)  # Only for local auth fallback
    profile_image = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    phone_number = Column(String, nullable=True)
    
    # Authentication
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    is_phone_verified = Column(Boolean, default=False)
    
    # Roles and permissions
    role = Column(Enum(UserRole), default=UserRole.CLIENT)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    permissions = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    reader_profile = relationship("ReaderProfile", back_populates="user", uselist=False)
    client_profile = relationship("ClientProfile", back_populates="user", uselist=False)
    
    # Backrefs (defined in other models)
    # - readings_as_reader
    # - readings_as_client
    # - messages_sent
    # - messages_received
    # - reviews_given
    # - reviews_received
    # - products
    # - transactions
    # - notifications
    # - forum_posts
    # - forum_comments
    # - help_tickets
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name or ''} {self.last_name or ''}".strip()
    
    @property
    def is_reader(self) -> bool:
        return self.role == UserRole.READER
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def is_moderator(self) -> bool:
        return self.role == UserRole.MODERATOR
class ClientProfile(Base):
    __tablename__ = "client_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    
    # Preferences
    preferred_languages = Column(JSONB, default=list)
    notification_preferences = Column(JSONB, default={
        "email": True,
        "push": True,
        "sms": False,
        "marketing_emails": True
    })
    
    # Stats
    total_sessions = Column(Integer, default=0)
    total_spent = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="client_profile")
    
    def __repr__(self):
        return f"<ClientProfile {self.user.email}>"
