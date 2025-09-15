from datetime import datetime
from enum import Enum as PyEnum
import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, Text, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

class ReviewRating(int, PyEnum):
    """Possible rating values for reviews."""
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5

class ReviewStatus(str, PyEnum):
    """Status of a review."""
    PENDING = "pending"       # Awaiting moderation
    APPROVED = "approved"     # Published and visible
    REJECTED = "rejected"     # Rejected by moderator
    EDITED = "edited"         # Modified after approval
    REPORTED = "reported"     # Flagged for review

class Review(Base):
    """Model representing a review left by a client for a reader."""
    __tablename__ = "reviews"
    
    # Primary key
    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True
    )
    
    # Rating and content
    rating: int = Column(
        Integer,
        nullable=False,
        index=True
    )
    
    title: Optional[str] = Column(String(200), nullable=True)
    content: str = Column(Text, nullable=False)
    
    # Status and moderation
    status: ReviewStatus = Column(
        ENUM(ReviewStatus, name="review_status"),
        nullable=False,
        default=ReviewStatus.PENDING,
        index=True
    )
    
    is_anonymous: bool = Column(Boolean, default=False)
    moderator_notes: Optional[str] = Column(Text, nullable=True)
    
    # Metadata
    metadata: Dict[str, Any] = Column(JSONB, default=dict)  # Additional metadata
    
    # Timestamps
    created_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now()
    )
    published_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
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
    
    session_id: Optional[uuid.UUID] = Column(
        UUID(as_uuid=True),
        ForeignKey("reading_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Define relationships
    reader = relationship("User", foreign_keys=[reader_id], back_populates="reviews_received")
    client = relationship("User", foreign_keys=[client_id], back_populates="reviews_given")
    session = relationship("ReadingSession", back_populates="review")
    
    # Table constraints
    __table_args__ = (
        # Ensure rating is between 1 and 5
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
        # A client can only leave one review per session
        # CheckConstraint(
        #     'NOT (session_id IS NOT NULL AND EXISTS ('
        #     'SELECT 1 FROM reviews r2 WHERE r2.session_id = reviews.session_id AND r2.client_id = reviews.client_id'
        #     '))',
        #     name='one_review_per_session_per_client'
        # ),
    )
    
    # Methods
    def approve(self, moderator_id: uuid.UUID, notes: str = None) -> None:
        """Approve the review for publication."""
        self.status = ReviewStatus.APPROVED
        self.published_at = datetime.utcnow()
        self.moderator_notes = notes
        
        # Update the reader's average rating
        if self.reader and hasattr(self.reader, 'reader_profile'):
            reader_profile = self.reader.reader_profile
            
            # Recalculate average rating
            total_ratings = (reader_profile.average_rating * reader_profile.rating_count) + self.rating
            reader_profile.rating_count += 1
            reader_profile.average_rating = total_ratings / reader_profile.rating_count
    
    def reject(self, moderator_id: uuid.UUID, reason: str) -> None:
        """Reject the review with a reason."""
        self.status = ReviewStatus.REJECTED
        self.moderator_notes = f"Rejected: {reason}"
    
    def report(self, reason: str, reported_by: uuid.UUID) -> None:
        """Flag the review for moderator attention."""
        self.status = ReviewStatus.REPORTED
        self.moderator_notes = f"Reported by {reported_by}: {reason}"
    
    def to_dict(self, include_client: bool = False) -> Dict[str, Any]:
        """Convert the review to a dictionary."""
        result = {
            "id": str(self.id),
            "rating": self.rating,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "is_anonymous": self.is_anonymous,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reader_id": str(self.reader_id),
            "session_id": str(self.session_id) if self.session_id else None,
        }
        
        if include_client and not self.is_anonymous:
            result["client"] = {
                "id": str(self.client_id),
                "display_name": self.client.display_name if self.client else "Anonymous",
                "profile_image": self.client.profile_image if self.client else None
            }
        
        return result
    
    def __repr__(self) -> str:
        return f"<Review {self.rating}★ by {self.client_id} for {self.reader_id}>"

# Add relationships to User model
from app.models.user import User
from app.models.reading_session import ReadingSession

User.reviews_received = relationship(
    "Review",
    foreign_keys="[Review.reader_id]",
    back_populates="reader",
    cascade="all, delete-orphan"
)

User.reviews_given = relationship(
    "Review",
    foreign_keys="[Review.client_id]",
    back_populates="client",
    cascade="all, delete-orphan"
)

ReadingSession.review = relationship(
    "Review",
    back_populates="session",
    uselist=False,
    cascade="all, delete-orphan"
)
