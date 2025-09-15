from datetime import datetime, time, date
from enum import Enum as PyEnum
import uuid
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, Boolean, Date, Time, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, and_, or_

from app.core.database import Base

class ScheduleRecurrence(str, PyEnum):
    """Types of schedule recurrence."""
    NONE = "none"           # One-time schedule
    DAILY = "daily"         # Repeats daily
    WEEKLY = "weekly"       # Repeats weekly on specific days
    BIWEEKLY = "biweekly"   # Repeats every other week
    MONTHLY = "monthly"     # Repeats monthly
    CUSTOM = "custom"       # Custom recurrence pattern

class ScheduleStatus(str, PyEnum):
    """Status of a schedule entry."""
    ACTIVE = "active"           # Schedule is active
    INACTIVE = "inactive"       # Schedule is inactive
    PAUSED = "paused"           # Schedule is temporarily paused
    CANCELLED = "cancelled"     # Schedule has been cancelled

class ScheduleType(str, PyEnum):
    """Type of schedule entry."""
    AVAILABILITY = "availability"   # Regular available time
    UNAVAILABLE = "unavailable"     # Blocked time
    BREAK = "break"                 # Break time
    APPOINTMENT = "appointment"     # Booked appointment
    HOLIDAY = "holiday"             # Holiday/Time off

class Schedule(Base):
    """Model representing a reader's schedule and availability."""
    __tablename__ = "schedules"
    
    # Primary key
    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True
    )
    
    # Schedule details
    title: str = Column(String(200), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    schedule_type: ScheduleType = Column(
        ENUM(ScheduleType, name="schedule_type"),
        nullable=False,
        default=ScheduleType.AVAILABILITY
    )
    
    # Date and time
    start_date: date = Column(Date, nullable=False, index=True)
    end_date: Optional[date] = Column(Date, nullable=True, index=True)
    start_time: time = Column(Time, nullable=False)
    end_time: time = Column(Time, nullable=False)
    
    # Timezone information
    timezone: str = Column(String(50), default="UTC")
    
    # Recurrence
    recurrence: ScheduleRecurrence = Column(
        ENUM(ScheduleRecurrence, name="schedule_recurrence"),
        nullable=False,
        default=ScheduleRecurrence.NONE
    )
    recurrence_days: List[int] = Column(JSONB, default=[])  # 0=Monday, 6=Sunday
    recurrence_end_date: Optional[date] = Column(Date, nullable=True)
    recurrence_interval: int = Column(Integer, default=1)  # Every N days/weeks/months
    
    # Status
    status: ScheduleStatus = Column(
        ENUM(ScheduleStatus, name="schedule_status"),
        nullable=False,
        default=ScheduleStatus.ACTIVE
    )
    
    # Metadata
    metadata: Dict[str, Any] = Column(JSONB, default=dict)  # Additional metadata
    
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
    
    # For appointments
    session_id: Optional[uuid.UUID] = Column(
        UUID(as_uuid=True),
        ForeignKey("reading_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Define relationships
    reader = relationship("User", back_populates="schedules")
    session = relationship("ReadingSession", back_populates="schedule")
    
    # Table constraints
    __table_args__ = (
        # Ensure end_time is after start_time
        CheckConstraint('end_time > start_time', name='check_time_range'),
        # If end_date is set, it must be after or equal to start_date
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='check_date_range'),
    )
    
    # Methods
    def is_available(self) -> bool:
        """Check if this schedule entry represents available time."""
        return self.schedule_type == ScheduleType.AVAILABILITY and \
               self.status == ScheduleStatus.ACTIVE
    
    def is_within_working_hours(self, check_time: datetime) -> bool:
        """Check if the given datetime is within this schedule's time range."""
        if check_time.date() < self.start_date:
            return False
            
        if self.end_date and check_time.date() > self.end_date:
            return False
            
        if self.recurrence != ScheduleRecurrence.NONE:
            # Check if the day of week matches for weekly recurrence
            if self.recurrence == ScheduleRecurrence.WEEKLY:
                if check_time.weekday() not in self.recurrence_days:
                    return False
            # Add more recurrence checks as needed
            
        # Check time of day
        check_time_only = check_time.time()
        return self.start_time <= check_time_only <= self.end_time
    
    def get_occurrences(self, start_dt: datetime, end_dt: datetime) -> List[Tuple[datetime, datetime]]:
        """Get all occurrences of this schedule between two datetimes."""
        if end_dt < start_dt:
            return []
            
        occurrences = []
        current_date = max(
            self.start_date,
            start_dt.date()
        )
        
        end_date = min(
            self.end_date if self.end_date else end_dt.date(),
            end_dt.date()
        )
        
        if self.recurrence == ScheduleRecurrence.NONE:
            # One-time schedule
            if self.start_date <= end_date and self.start_date >= start_dt.date():
                start_dt = datetime.combine(self.start_date, self.start_time)
                end_dt = datetime.combine(self.start_date, self.end_time)
                occurrences.append((start_dt, end_dt))
        
        elif self.recurrence == ScheduleRecurrence.DAILY:
            # Daily recurrence
            delta = timedelta(days=1)
            while current_date <= end_date:
                start_dt = datetime.combine(current_date, self.start_time)
                end_dt = datetime.combine(current_date, self.end_time)
                occurrences.append((start_dt, end_dt))
                current_date += delta
                
        elif self.recurrence == ScheduleRecurrence.WEEKLY:
            # Weekly recurrence on specific days
            delta = timedelta(days=1)
            while current_date <= end_date:
                if current_date.weekday() in self.recurrence_days:
                    start_dt = datetime.combine(current_date, self.start_time)
                    end_dt = datetime.combine(current_date, self.end_time)
                    occurrences.append((start_dt, end_dt))
                current_date += delta
                
        # Add more recurrence patterns as needed
        
        return occurrences
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the schedule to a dictionary."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "type": self.schedule_type,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "timezone": self.timezone,
            "recurrence": self.recurrence,
            "recurrence_days": self.recurrence_days,
            "recurrence_end_date": self.recurrence_end_date.isoformat() if self.recurrence_end_date else None,
            "recurrence_interval": self.recurrence_interval,
            "status": self.status,
            "reader_id": str(self.reader_id),
            "session_id": str(self.session_id) if self.session_id else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def __repr__(self) -> str:
        return f"<Schedule {self.title} ({self.schedule_type}) for {self.reader_id}>"

# Add relationships to User and ReadingSession models
from app.models.user import User
from app.models.reading_session import ReadingSession

User.schedules = relationship(
    "Schedule",
    back_populates="reader",
    cascade="all, delete-orphan"
)

ReadingSession.schedule = relationship(
    "Schedule",
    back_populates="session",
    uselist=False,
    cascade="all, delete-orphan"
)
