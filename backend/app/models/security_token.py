from datetime import datetime, timedelta
from enum import Enum as PyEnum
import uuid
from typing import Optional

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

class TokenType(str, PyEnum):
    """Types of security tokens."""
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    API_ACCESS = "api_access"
    REFRESH = "refresh"
    MFA_VERIFICATION = "mfa_verification"
    DEVICE_VERIFICATION = "device_verification"

class SecurityToken(Base):
    """Model for storing security tokens used for various authentication flows."""
    __tablename__ = "security_tokens"
    
    # Primary key
    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True
    )
    
    # Token details
    token: str = Column(String, unique=True, index=True, nullable=False)
    token_type: TokenType = Column(Enum(TokenType), nullable=False)
    expires_at: datetime = Column(DateTime(timezone=True), nullable=False)
    is_used: bool = Column(Boolean, default=False, nullable=False)
    used_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    # Additional data stored with the token (e.g., IP, user agent, etc.)
    data: dict = Column(JSONB, default=dict, nullable=False)
    
    # Timestamps
    created_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now()
    )
    
    # Relationships
    user_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    user = relationship("User", back_populates="security_tokens")
    
    # Methods
    def is_expired(self) -> bool:
        """Check if the token has expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """Check if the token is valid (not used and not expired)."""
        return not self.is_used and not self.is_expired()
    
    def mark_as_used(self) -> None:
        """Mark the token as used."""
        self.is_used = True
        self.used_at = datetime.utcnow()
    
    def __repr__(self) -> str:
        return f"<SecurityToken {self.token_type} for user {self.user_id}>"
    
    # Factory methods for different token types
    @classmethod
    def create_email_verification_token(
        cls, 
        user_id: uuid.UUID,
        expires_in_hours: int = 24,
        **data
    ) -> 'SecurityToken':
        """Create an email verification token."""
        return cls(
            token=str(uuid.uuid4()),
            token_type=TokenType.EMAIL_VERIFICATION,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
            data={
                "purpose": "email_verification",
                **data
            }
        )
    
    @classmethod
    def create_password_reset_token(
        cls,
        user_id: uuid.UUID,
        expires_in_minutes: int = 60,
        **data
    ) -> 'SecurityToken':
        """Create a password reset token."""
        return cls(
            token=str(uuid.uuid4()),
            token_type=TokenType.PASSWORD_RESET,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
            data={
                "purpose": "password_reset",
                **data
            }
        )
    
    @classmethod
    def create_refresh_token(
        cls,
        user_id: uuid.UUID,
        expires_in_days: int = 30,
        **data
    ) -> 'SecurityToken':
        """Create a refresh token for JWT refresh flow."""
        return cls(
            token=str(uuid.uuid4()),
            token_type=TokenType.REFRESH,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
            data={
                "purpose": "refresh_token",
                **data
            }
        )
    
    @classmethod
    def create_mfa_verification_token(
        cls,
        user_id: uuid.UUID,
        expires_in_minutes: int = 10,
        **data
    ) -> 'SecurityToken':
        """Create an MFA verification token."""
        return cls(
            token=str(uuid.uuid4()),
            token_type=TokenType.MFA_VERIFICATION,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
            data={
                "purpose": "mfa_verification",
                **data
            }
        )

# Add the relationship to the User model
from app.models.user import User
User.security_tokens = relationship(
    "SecurityToken", 
    back_populates="user",
    cascade="all, delete-orphan"
)
