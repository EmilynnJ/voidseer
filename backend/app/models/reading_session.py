from datetime import datetime, timedelta
from enum import Enum as PyEnum
import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, Float, Boolean, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, expression

from app.core.database import Base

class SessionStatus(str, PyEnum):
    """Status of a reading session."""
    PENDING = "pending"           # Session created but not started
    SCHEDULED = "scheduled"       # Session is scheduled for future
    IN_PROGRESS = "in_progress"   # Session is currently active
    COMPLETED = "completed"       # Session completed successfully
    CANCELLED = "cancelled"       # Session was cancelled
    EXPIRED = "expired"           # Session expired before starting
    DECLINED = "declined"         # Reader declined the session

class SessionType(str, PyEnum):
    """Type of reading session."""
    CHAT = "chat"                 # Text-based chat reading
    VOICE = "voice"               # Voice call reading
    VIDEO = "video"               # Video call reading
    MESSAGE = "message"           # Asynchronous message reading

class PaymentStatus(str, PyEnum):
    """Payment status for a session."""
    PENDING = "pending"           # Payment not yet processed
    PAID = "paid"                 # Payment successfully processed
    FAILED = "failed"             # Payment failed
    REFUNDED = "refunded"         # Payment was refunded
    DISPUTED = "disputed"         # Payment is being disputed

class ReadingSession(Base):
    """Model representing a reading session between a reader and a client."""
    __tablename__ = "reading_sessions"
    
    # Primary key
    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True
    )
    
    # Session details
    session_type: SessionType = Column(
        ENUM(SessionType, name="session_type"),
        nullable=False,
        default=SessionType.CHAT
    )
    status: SessionStatus = Column(
        ENUM(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.PENDING
    )
    
    # Duration and timing
    scheduled_start: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    actual_start: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    end_time: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    duration_seconds: int = Column(Integer, default=0)  # Actual duration in seconds
    
    # Payment information
    payment_status: PaymentStatus = Column(
        ENUM(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.PENDING
    )
    amount_charged: float = Column(Float, default=0.0)  # In the smallest currency unit (e.g., cents)
    currency: str = Column(String(3), default="USD")
    payment_intent_id: Optional[str] = Column(String(100), nullable=True)  # Stripe payment intent ID
    refund_amount: Optional[float] = Column(Float, nullable=True)
    
    # Session metadata
    notes: Optional[str] = Column(Text, nullable=True)  # Private notes from reader
    client_notes: Optional[str] = Column(Text, nullable=True)  # Notes from client
    metadata: Dict[str, Any] = Column(JSONB, default=dict)  # Additional metadata
    
    # Ratings and feedback
    rating: Optional[int] = Column(Integer, nullable=True)  # 1-5 stars
    feedback: Optional[str] = Column(Text, nullable=True)
    is_anonymous: bool = Column(Boolean, default=False)  # If client wants to remain anonymous
    
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
    reader_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    client_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Define relationships
    reader = relationship("User", foreign_keys=[reader_id], back_populates="reader_sessions")
    client = relationship("User", foreign_keys=[client_id], back_populates="client_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    # Methods
    def calculate_cost(self) -> float:
        """Calculate the total cost of the session based on duration and rate."""
        if not self.reader or not hasattr(self.reader, 'reader_profile'):
            return 0.0
            
        rate_per_second = self.reader.reader_profile.rate_per_minute / 60
        return round(rate_per_second * self.duration_seconds, 2)
    
    def is_ongoing(self) -> bool:
        """Check if the session is currently in progress."""
        return self.status == SessionStatus.IN_PROGRESS
    
    def is_completed(self) -> bool:
        """Check if the session has been completed."""
        return self.status == SessionStatus.COMPLETED
    
    def is_cancellable(self) -> bool:
        """Check if the session can be cancelled."""
        return self.status in [SessionStatus.PENDING, SessionStatus.SCHEDULED]
    
    def get_remaining_time(self) -> Optional[timedelta]:
        """Get the remaining time for the session if it's in progress."""
        if not self.actual_start or not self.is_ongoing():
            return None
            
        elapsed = datetime.utcnow() - self.actual_start
        total_allowed = timedelta(seconds=self.duration_seconds)
        remaining = total_allowed - elapsed
        
        return max(remaining, timedelta(0))  # Don't return negative time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the session to a dictionary."""
        return {
            "id": str(self.id),
            "type": self.session_type,
            "status": self.status,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "actual_start": self.actual_start.isoformat() if self.actual_start else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "payment_status": self.payment_status,
            "amount_charged": self.amount_charged,
            "currency": self.currency,
            "reader_id": str(self.reader_id),
            "client_id": str(self.client_id),
            "rating": self.rating,
            "is_anonymous": self.is_anonymous,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def __repr__(self) -> str:
        return f"<ReadingSession {self.id} ({self.status})>"

# Add relationships to User model
from app.models.user import User
User.reader_sessions = relationship(
    "ReadingSession",
    foreign_keys="[ReadingSession.reader_id]",
    back_populates="reader",
    cascade="all, delete-orphan"
)

User.client_sessions = relationship(
    "ReadingSession",
    foreign_keys="[ReadingSession.client_id]",
    back_populates="client",
    cascade="all, delete-orphan"
)

# Create a model for chat messages
class ChatMessage(Base):
    """Model representing a message in a reading session."""
    __tablename__ = "chat_messages"
    
    # Primary key
    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True
    )
    
    # Message content
    content: str = Column(Text, nullable=False)
    message_type: str = Column(String(20), default="text")  # text, image, audio, etc.
    metadata: Dict[str, Any] = Column(JSONB, default=dict)  # Additional metadata
    
    # Sender information
    sender_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    is_from_reader: bool = Column(Boolean, nullable=False)
    
    # Timestamps
    created_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    # Session relationship
    session_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("reading_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    session = relationship("ReadingSession", back_populates="messages")
    
    # Sender relationship
    sender = relationship("User", foreign_keys=[sender_id])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the message to a dictionary."""
        return {
            "id": str(self.id),
            "content": self.content,
            "message_type": self.message_type,
            "sender_id": str(self.sender_id),
            "is_from_reader": self.is_from_reader,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }
    
    def __repr__(self) -> str:
        return f"<ChatMessage {self.id[:8]}... from {self.sender_id} in session {self.session_id}>"
