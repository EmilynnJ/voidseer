from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, and_, or_, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.database import get_db
from app.core.security import get_current_active_user, has_any_role
from app.models.user import User, UserRole, UserStatus, ReaderProfile, Schedule, ScheduleType, ScheduleStatus
from app.models.reading_session import ReadingSession, SessionStatus
from app.schemas.reader import (
    ReaderProfileResponse,
    ReaderProfileUpdate,
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleResponse,
    AvailabilityWindow,
    ReaderSearchParams,
    ReaderListResponse,
)
from app.schemas.common import Message, ListResponse, PaginationParams

router = APIRouter()

# Reader profile endpoints
@router.get("/profile/me", response_model=ReaderProfileResponse)
async def get_my_reader_profile(
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's reader profile.
    """
    if not current_user.reader_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reader profile not found",
        )
    
    # Eager load relationships
    result = await db.execute(
        select(ReaderProfile)
        .options(
            selectinload(ReaderProfile.user),
            selectinload(ReaderProfile.schedules),
            selectinload(ReaderProfile.specialties),
            selectinload(ReaderProfile.languages),
        )
        .where(ReaderProfile.user_id == current_user.id)
    )
    
    profile = result.scalar_one_or_none()
    return profile

@router.put("/profile/me", response_model=ReaderProfileResponse)
async def update_my_reader_profile(
    profile_in: ReaderProfileUpdate,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user's reader profile.
    """
    if not current_user.reader_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reader profile not found",
        )
    
    # Update profile fields
    update_data = profile_in.dict(exclude_unset=True)
    
    # Handle special fields
    if "specialties" in update_data:
        current_user.reader_profile.specialties = update_data.pop("specialties")
    if "languages" in update_data:
        current_user.reader_profile.languages = update_data.pop("languages")
    
    # Update remaining fields
    for field, value in update_data.items():
        setattr(current_user.reader_profile, field, value)
    
    current_user.reader_profile.updated_at = datetime.now(timezone.utc)
    
    db.add(current_user.reader_profile)
    await db.commit()
    await db.refresh(current_user.reader_profile)
    
    return current_user.reader_profile

# Schedule management endpoints
@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    schedule_in: ScheduleCreate,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new schedule for the current reader.
    """
    # Check for overlapping schedules
    overlapping = await db.execute(
        select(Schedule).where(
            and_(
                Schedule.user_id == current_user.id,
                Schedule.status == ScheduleStatus.ACTIVE,
                or_(
                    and_(
                        Schedule.start_time <= schedule_in.start_time,
                        Schedule.end_time > schedule_in.start_time,
                    ),
                    and_(
                        Schedule.start_time < schedule_in.end_time,
                        Schedule.end_time >= schedule_in.end_time,
                    ),
                    and_(
                        Schedule.start_time >= schedule_in.start_time,
                        Schedule.end_time <= schedule_in.end_time,
                    ),
                ),
            )
        )
    )
    
    if overlapping.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Schedule overlaps with an existing schedule",
        )
    
    # Create schedule
    schedule = Schedule(
        user_id=current_user.id,
        **schedule_in.dict(exclude={"recurrence_rule"}),
        status=ScheduleStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    
    return schedule

@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    schedule_type: Optional[ScheduleType] = None,
    status: Optional[ScheduleStatus] = None,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    List schedules for the current reader with optional filtering.
    """
    query = select(Schedule).where(Schedule.user_id == current_user.id)
    
    # Apply filters
    if start_time:
        query = query.where(Schedule.start_time >= start_time)
    if end_time:
        query = query.where(Schedule.end_time <= end_time)
    if schedule_type:
        query = query.where(Schedule.schedule_type == schedule_type)
    if status:
        query = query.where(Schedule.status == status)
    
    # Order by start time
    query = query.order_by(Schedule.start_time.asc())
    
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: UUID,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific schedule by ID.
    """
    schedule = await db.get(Schedule, schedule_id)
    
    if not schedule or schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    
    return schedule

@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    schedule_in: ScheduleUpdate,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a schedule.
    """
    schedule = await db.get(Schedule, schedule_id)
    
    if not schedule or schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    
    # Check for overlapping schedules (excluding self)
    if schedule_in.start_time or schedule_in.end_time:
        start_time = schedule_in.start_time or schedule.start_time
        end_time = schedule_in.end_time or schedule.end_time
        
        overlapping = await db.execute(
            select(Schedule).where(
                and_(
                    Schedule.user_id == current_user.id,
                    Schedule.id != schedule_id,
                    Schedule.status == ScheduleStatus.ACTIVE,
                    or_(
                        and_(
                            Schedule.start_time <= start_time,
                            Schedule.end_time > start_time,
                        ),
                        and_(
                            Schedule.start_time < end_time,
                            Schedule.end_time >= end_time,
                        ),
                        and_(
                            Schedule.start_time >= start_time,
                            Schedule.end_time <= end_time,
                        ),
                    ),
                )
            )
        )
        
        if overlapping.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Schedule overlaps with an existing schedule",
            )
    
    # Update schedule fields
    update_data = schedule_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)
    
    schedule.updated_at = datetime.now(timezone.utc)
    
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    
    return schedule

@router.delete("/schedules/{schedule_id}", response_model=Message)
async def delete_schedule(
    schedule_id: UUID,
    current_user: User = Depends(has_any_role([UserRole.READER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a schedule.
    """
    schedule = await db.get(Schedule, schedule_id)
    
    if not schedule or schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    
    # Check for future sessions that might be affected
    future_sessions = await db.execute(
        select(ReadingSession).where(
            and_(
                ReadingSession.reader_id == current_user.id,
                ReadingSession.status.in_([SessionStatus.CONFIRMED, SessionStatus.PENDING]),
                ReadingSession.scheduled_start > datetime.now(timezone.utc),
                or_(
                    and_(
                        ReadingSession.scheduled_start >= schedule.start_time,
                        ReadingSession.scheduled_start < schedule.end_time,
                    ),
                    and_(
                        ReadingSession.scheduled_end > schedule.start_time,
                        ReadingSession.scheduled_end <= schedule.end_time,
                    ),
                ),
            )
        )
    )
    
    if future_sessions.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete schedule with upcoming sessions",
        )
    
    # Soft delete
    schedule.status = ScheduleStatus.DELETED
    schedule.updated_at = datetime.now(timezone.utc)
    
    db.add(schedule)
    await db.commit()
    
    return {"message": "Schedule deleted successfully"}

# Availability endpoints
@router.get("/availability", response_model=List[AvailabilityWindow])
async def get_availability(
    reader_id: UUID,
    start_time: datetime = Query(..., description="Start time for availability check"),
    end_time: datetime = Query(..., description="End time for availability check"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a reader's available time slots within a date range.
    """
    # Get reader
    reader = await db.get(User, reader_id)
    if not reader or reader.role != UserRole.READER or not reader.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reader not found",
        )
    
    # Get reader's active schedules
    schedules = await db.execute(
        select(Schedule).where(
            and_(
                Schedule.user_id == reader_id,
                Schedule.status == ScheduleStatus.ACTIVE,
                Schedule.start_time < end_time,
                Schedule.end_time > start_time,
            )
        )
    )
    schedules = schedules.scalars().all()
    
    if not schedules:
        return []
    
    # Get reader's existing sessions in this time range
    sessions = await db.execute(
        select(ReadingSession).where(
            and_(
                ReadingSession.reader_id == reader_id,
                ReadingSession.status.in_([SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]),
                ReadingSession.scheduled_start < end_time,
                ReadingSession.scheduled_end > start_time,
            )
        )
    )
    sessions = sessions.scalars().all()
    
    # Calculate available time slots
    availability = []
    
    for schedule in schedules:
        # Get the effective start and end times for this schedule
        effective_start = max(schedule.start_time, start_time)
        effective_end = min(schedule.end_time, end_time)
        
        if effective_start >= effective_end:
            continue
        
        # Find overlapping sessions
        busy_slots = []
        for session in sessions:
            session_start = max(session.scheduled_start, effective_start)
            session_end = min(session.scheduled_end, effective_end)
            
            if session_start < session_end:
                busy_slots.append((session_start, session_end))
        
        # Sort busy slots by start time
        busy_slots.sort()
        
        # Calculate available slots
        current_time = effective_start
        
        for busy_start, busy_end in busy_slots:
            if busy_start > current_time:
                availability.append({
                    "start_time": current_time,
                    "end_time": busy_start,
                    "schedule_type": schedule.schedule_type,
                })
            
            current_time = max(current_time, busy_end)
        
        # Add remaining time after last busy slot
        if current_time < effective_end:
            availability.append({
                "start_time": current_time,
                "end_time": effective_end,
                "schedule_type": schedule.schedule_type,
            })
    
    return availability

# Reader search endpoint
@router.get("/search", response_model=ReaderListResponse)
async def search_readers(
    params: ReaderSearchParams = Depends(),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for readers based on various criteria.
    """
    # Base query for readers
    query = (
        select(User)
        .join(ReaderProfile, User.id == ReaderProfile.user_id)
        .where(
            and_(
                User.role == UserRole.READER,
                User.status == UserStatus.ACTIVE,
                User.is_active == True,
            )
        )
    )
    
    # Apply search filters
    if params.query:
        search = f"%{params.query}%"
        query = query.where(
            or_(
                User.username.ilike(search),
                User.first_name.ilike(search),
                User.last_name.ilike(search),
                ReaderProfile.bio.ilike(search),
                ReaderProfile.specialties.any(search),
            )
        )
    
    if params.specialties:
        for specialty in params.specialties:
            query = query.where(ReaderProfile.specialties.any(specialty))
    
    if params.languages:
        for language in params.languages:
            query = query.where(ReaderProfile.languages.any(language))
    
    if params.min_rating is not None:
        query = query.where(ReaderProfile.average_rating >= params.min_rating)
    
    if params.available_after or params.available_before:
        # Subquery to find readers with availability in the specified time range
        availability_subq = select(Schedule.user_id).distinct().where(
            and_(
                Schedule.status == ScheduleStatus.ACTIVE,
                Schedule.start_time < (params.available_before or datetime.max),
                Schedule.end_time > (params.available_after or datetime.min),
                or_(
                    params.available_after == None,
                    Schedule.start_time >= params.available_after,
                ),
                or_(
                    params.available_before == None,
                    Schedule.end_time <= params.available_before,
                ),
            )
        ).subquery()
        
        query = query.where(User.id.in_(availability_subq))
    
    # Get total count
    total = await db.scalar(select([query.subquery().count()]))
    
    # Apply sorting
    if params.sort_by == "rating":
        query = query.order_by(ReaderProfile.average_rating.desc())
    elif params.sort_by == "price_asc":
        query = query.order_by(ReaderProfile.price_per_minute.asc())
    elif params.sort_by == "price_desc":
        query = query.order_by(ReaderProfile.price_per_minute.desc())
    else:  # Default: sort by relevance or name
        query = query.order_by(
            User.first_name.asc(),
            User.last_name.asc(),
        )
    
    # Apply pagination
    query = (
        query
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .options(selectinload(User.reader_profile))
    )
    
    # Execute query
    result = await db.execute(query)
    readers = result.scalars().all()
    
    return {
        "data": readers,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }
