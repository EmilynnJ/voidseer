import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union, Any
from uuid import UUID, uuid4
import json
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, delete
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.models import (
    User,
    ReadingSession,
    AvailabilitySlot,
    Transaction,
    Notification,
    Review,
    Message,
    Timezone
)
from app.schemas.session import (
    ReadingSessionCreate,
    ReadingSessionUpdate,
    ReadingSessionResponse,
    AvailabilitySlotCreate,
    AvailabilitySlotResponse,
    TimeRange,
    SessionStatus
)
from app.services.billing_service import billing_service
from app.services.notification_service import notification_service
from app.services.email_service import email_service
from app.websockets.connection_manager import connection_manager

logger = logging.getLogger(__name__)

class SessionService:
    """Service for managing reading sessions and availability"""
    
    async def create_session(
        self,
        db: AsyncSession,
        session_data: ReadingSessionCreate,
        current_user_id: UUID
    ) -> ReadingSessionResponse:
        """
        Create a new reading session
        
        Args:
            db: Database session
            session_data: Session creation data
            current_user_id: ID of the user creating the session (must be the client)
            
        Returns:
            ReadingSessionResponse: The created session
            
        Raises:
            HTTPException: If the reader is not available or other validation fails
        """
        # Get reader and client
        reader = await self._get_user(db, session_data.reader_id)
        client = await self._get_user(db, current_user_id)
        
        # Validate reader is a reader and available
        if not reader or not reader.is_reader:
            raise HTTPException(status_code=400, detail="Invalid reader")
            
        # Check if reader is accepting new sessions
        if not reader.reader_profile or not reader.reader_profile.is_available:
            raise HTTPException(status_code=400, detail="Reader is not currently available")
        
        # Check if the requested time slot is available
        if not await self._is_time_slot_available(
            db, 
            reader_id=reader.id,
            start_time=session_data.start_time,
            duration_minutes=session_data.duration_minutes
        ):
            raise HTTPException(status_code=400, detail="Requested time slot is not available")
        
        # Check if client has sufficient balance for the session
        session_cost = (reader.reader_profile.rate_per_minute * session_data.duration_minutes).quantize(Decimal('0.01'))
        
        if client.balance < session_cost:
            raise HTTPException(
                status_code=400,
                detail="Insufficient balance for this session"
            )
        
        # Create the session
        session = ReadingSession(
            reader_id=reader.id,
            client_id=client.id,
            start_time=session_data.start_time,
            end_time=session_data.start_time + timedelta(minutes=session_data.duration_minutes),
            duration_minutes=session_data.duration_minutes,
            status=SessionStatus.SCHEDULED,
            rate_per_minute=reader.reader_profile.rate_per_minute,
            total_cost=session_cost,
            timezone=session_data.timezone or "UTC",
            notes=session_data.notes,
            meeting_link=self._generate_meeting_link()
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        # Send notifications
        await notification_service.send_reading_session_notification(
            db=db,
            session=session,
            notification_type="scheduled"
        )
        
        # Schedule reminder notifications
        await self._schedule_session_reminders(db, session)
        
        return ReadingSessionResponse.from_orm(session)
    
    async def get_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        current_user_id: UUID
    ) -> ReadingSessionResponse:
        """
        Get a session by ID
        
        Args:
            db: Database session
            session_id: ID of the session to retrieve
            current_user_id: ID of the current user (must be the client or reader)
            
        Returns:
            ReadingSessionResponse: The requested session
            
        Raises:
            HTTPException: If the session doesn't exist or the user doesn't have permission
        """
        result = await db.execute(
            select(ReadingSession)
            .options(
                selectinload(ReadingSession.reader).selectinload(User.reader_profile),
                selectinload(ReadingSession.client)
            )
            .where(ReadingSession.id == session_id)
        )
        
        session = result.scalars().first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.reader_id != current_user_id and session.client_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this session")
            
        return ReadingSessionResponse.from_orm(session)
    
    async def update_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        session_data: ReadingSessionUpdate,
        current_user_id: UUID
    ) -> ReadingSessionResponse:
        """
        Update a session
        
        Args:
            db: Database session
            session_id: ID of the session to update
            session_data: Updated session data
            current_user_id: ID of the current user (must be the client or reader)
            
        Returns:
            ReadingSessionResponse: The updated session
            
        Raises:
            HTTPException: If the session doesn't exist or the user doesn't have permission
        """
        result = await db.execute(
            select(ReadingSession)
            .options(
                selectinload(ReadingSession.reader).selectinload(User.reader_profile),
                selectinload(ReadingSession.client)
            )
            .where(ReadingSession.id == session_id)
        )
        
        session = result.scalars().first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.reader_id != current_user_id and session.client_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this session")
        
        # Only allow certain updates based on session status
        if session.status == SessionStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Cannot update a completed session")
            
        if session.status == SessionStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Cannot update a cancelled session")
        
        # Update fields if provided
        update_data = session_data.dict(exclude_unset=True)
        
        if 'status' in update_data:
            new_status = update_data['status']
            
            # Validate status transition
            valid_transitions = {
                SessionStatus.SCHEDULED: [SessionStatus.CONFIRMED, SessionStatus.CANCELLED],
                SessionStatus.CONFIRMED: [SessionStatus.IN_PROGRESS, SessionStatus.CANCELLED],
                SessionStatus.IN_PROGRESS: [SessionStatus.COMPLETED, SessionStatus.CANCELLED],
            }
            
            current_status = session.status
            
            if (current_status in valid_transitions and 
                new_status not in valid_transitions[current_status]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot transition from {current_status} to {new_status}"
                )
            
            # Handle status-specific logic
            if new_status == SessionStatus.IN_PROGRESS:
                # Start the session
                session.actual_start_time = datetime.utcnow()
                
                # Notify client that the session has started
                await notification_service.send_reading_session_notification(
                    db=db,
                    session=session,
                    notification_type="started"
                )
                
                # Start billing
                await billing_service.start_session_billing(session.id)
                
            elif new_status == SessionStatus.COMPLETED:
                # End the session
                session.actual_end_time = datetime.utcnow()
                
                # Calculate actual duration and final cost
                if session.actual_start_time and session.actual_end_time:
                    actual_duration = (session.actual_end_time - session.actual_start_time).total_seconds() / 60
                    session.actual_duration_minutes = max(1, int(actual_duration))  # Minimum 1 minute
                    session.final_cost = (session.rate_per_minute * session.actual_duration_minutes).quantize(Decimal('0.01'))
                
                # Stop billing
                await billing_service.end_session_billing(session.id)
                
                # Notify client that the session has ended
                await notification_service.send_reading_session_notification(
                    db=db,
                    session=session,
                    notification_type="completed"
                )
                
                # Request review from client
                await self._request_review(db, session)
                
            elif new_status == SessionStatus.CANCELLED:
                # Cancel the session
                session.cancelled_at = datetime.utcnow()
                session.cancelled_by_id = current_user_id
                
                # Stop billing if in progress
                if session.status == SessionStatus.IN_PROGRESS:
                    await billing_service.end_session_billing(session.id, is_cancelled=True)
                
                # Notify the other party
                recipient_id = session.client_id if current_user_id == session.reader_id else session.reader_id
                
                await notification_service.send_reading_session_notification(
                    db=db,
                    session=session,
                    notification_type="cancelled",
                    cancelled_by=current_user_id == session.reader_id and "reader" or "client"
                )
        
        # Update other fields
        for field, value in update_data.items():
            if field != 'status' and hasattr(session, field):
                setattr(session, field, value)
        
        session.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(session)
        
        return ReadingSessionResponse.from_orm(session)
    
    async def list_sessions(
        self,
        db: AsyncSession,
        current_user_id: UUID,
        status: Optional[SessionStatus] = None,
        as_reader: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        List sessions for a user
        
        Args:
            db: Database session
            current_user_id: ID of the current user
            status: Filter by status
            as_reader: If True, get sessions where user is the reader; if False, as client
            start_date: Filter by start date (inclusive)
            end_date: Filter by end date (inclusive)
            page: Page number (1-based)
            page_size: Number of items per page
            
        Returns:
            Dict containing the list of sessions and pagination info
        """
        query = select(ReadingSession).options(
            selectinload(ReadingSession.reader).selectinload(User.reader_profile),
            selectinload(ReadingSession.client)
        )
        
        # Filter by user role (reader or client)
        if as_reader:
            query = query.where(ReadingSession.reader_id == current_user_id)
        else:
            query = query.where(ReadingSession.client_id == current_user_id)
        
        # Apply filters
        if status:
            query = query.where(ReadingSession.status == status)
            
        if start_date:
            query = query.where(ReadingSession.start_time >= start_date)
            
        if end_date:
            # Add one day to include the entire end date
            end_of_day = end_date.replace(hour=23, minute=59, second=59)
            query = query.where(ReadingSession.start_time <= end_of_day)
        
        # Count total items for pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_items = (await db.execute(count_query)).scalar()
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(ReadingSession.start_time.desc())
        query = query.offset(offset).limit(page_size)
        
        # Execute query
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        # Calculate pagination info
        total_pages = (total_items + page_size - 1) // page_size
        
        return {
            "items": [ReadingSessionResponse.from_orm(session) for session in sessions],
            "total": total_items,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1
        }
    
    async def get_availability(
        self,
        db: AsyncSession,
        reader_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get available time slots for a reader within a date range
        
        Args:
            db: Database session
            reader_id: ID of the reader
            start_date: Start of the date range (inclusive)
            end_date: End of the date range (inclusive)
            
        Returns:
            List of available time slots grouped by date
        """
        # Get reader's timezone (default to UTC)
        result = await db.execute(
            select(User.timezone).where(User.id == reader_id)
        )
        timezone = result.scalar() or "UTC"
        
        # Get reader's availability slots
        result = await db.execute(
            select(AvailabilitySlot)
            .where(and_(
                AvailabilitySlot.reader_id == reader_id,
                or_(
                    and_(
                        AvailabilitySlot.recurring == True,
                        # For recurring slots, just check the day of week and time
                        func.extract('dow', func.timezone(timezone, start_date)) == func.extract('dow', AvailabilitySlot.start_time)
                    ),
                    and_(
                        AvailabilitySlot.recurring == False,
                        func.date(AvailabilitySlot.start_time) >= start_date.date(),
                        func.date(AvailabilitySlot.start_time) <= end_date.date()
                    )
                )
            ))
        )
        
        slots = result.scalars().all()
        
        # Get booked sessions in the date range
        result = await db.execute(
            select(ReadingSession)
            .where(and_(
                ReadingSession.reader_id == reader_id,
                ReadingSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]),
                ReadingSession.start_time >= start_date,
                ReadingSession.end_time <= end_date + timedelta(days=1)  # Include the entire end date
            ))
        )
        
        booked_sessions = result.scalars().all()
        
        # Group availability by date
        availability = {}
        current_date = start_date.date()
        
        while current_date <= end_date.date():
            availability[current_date.isoformat()] = []
            current_date += timedelta(days=1)
        
        # Process recurring slots
        for slot in slots:
            if slot.recurring:
                # For recurring slots, add for each day in the range
                current_date = start_date.date()
                
                while current_date <= end_date.date():
                    # Check if this is the correct day of the week
                    if current_date.weekday() == slot.start_time.weekday():
                        # Create a time slot for this date
                        start_datetime = datetime.combine(
                            current_date,
                            slot.start_time.time(),
                            tzinfo=slot.start_time.tzinfo
                        )
                        
                        end_datetime = datetime.combine(
                            current_date,
                            slot.end_time.time(),
                            tzinfo=slot.end_time.tzinfo
                        )
                        
                        # Only add if in the future
                        if end_datetime > datetime.now(timezone.utc):
                            availability[current_date.isoformat()].append({
                                "start_time": start_datetime,
                                "end_time": end_datetime,
                                "recurring": True
                            })
                    
                    current_date += timedelta(days=1)
            else:
                # For one-time slots, just add if in the date range
                slot_date = slot.start_time.date()
                
                if slot_date in availability:
                    # Only add if in the future
                    if slot.end_time > datetime.now(timezone.utc):
                        availability[slot_date.isoformat()].append({
                            "start_time": slot.start_time,
                            "end_time": slot.end_time,
                            "recurring": False
                        })
        
        # Remove booked time slots
        for session in booked_sessions:
            session_date = session.start_time.date().isoformat()
            
            if session_date in availability:
                # Remove or adjust time slots that overlap with the session
                new_slots = []
                
                for slot in availability[session_date]:
                    # If the session completely overlaps the slot, remove the slot
                    if (session.start_time <= slot["start_time"] and 
                        session.end_time >= slot["end_time"]):
                        continue
                    
                    # If the session overlaps the start of the slot, adjust the start time
                    elif (session.start_time > slot["start_time"] and 
                          session.start_time < slot["end_time"]):
                        new_slot = slot.copy()
                        new_slot["start_time"] = session.end_time
                        new_slots.append(new_slot)
                    
                    # If the session overlaps the end of the slot, adjust the end time
                    elif (session.end_time > slot["start_time"] and 
                          session.end_time < slot["end_time"]):
                        new_slot = slot.copy()
                        new_slot["end_time"] = session.start_time
                        new_slots.append(new_slot)
                    
                    # If the session is within the slot, split into two slots
                    elif (session.start_time > slot["start_time"] and 
                          session.end_time < slot["end_time"]):
                        # First part
                        new_slot1 = slot.copy()
                        new_slot1["end_time"] = session.start_time
                        new_slots.append(new_slot1)
                        
                        # Second part
                        new_slot2 = slot.copy()
                        new_slot2["start_time"] = session.end_time
                        new_slots.append(new_slot2)
                    
                    # No overlap, keep the slot as is
                    else:
                        new_slots.append(slot)
                
                availability[session_date] = new_slots
        
        # Convert to list of time ranges for the API response
        result = []
        
        for date_str, slots in availability.items():
            if slots:
                result.append({
                    "date": date_str,
                    "slots": [
                        {
                            "start_time": slot["start_time"].isoformat(),
                            "end_time": slot["end_time"].isoformat(),
                            "recurring": slot["recurring"]
                        }
                        for slot in slots
                    ]
                })
        
        return result
    
    async def set_availability(
        self,
        db: AsyncSession,
        reader_id: UUID,
        availability: List[AvailabilitySlotCreate],
        current_user_id: UUID
    ) -> List[AvailabilitySlotResponse]:
        """
        Set a reader's availability
        
        Args:
            db: Database session
            reader_id: ID of the reader
            availability: List of availability slots
            current_user_id: ID of the current user (must be the reader)
            
        Returns:
            List of created/updated availability slots
            
        Raises:
            HTTPException: If the user is not authorized or validation fails
        """
        if reader_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this reader's availability")
        
        # Delete existing non-recurring slots in the future
        await db.execute(
            delete(AvailabilitySlot)
            .where(and_(
                AvailabilitySlot.reader_id == reader_id,
                or_(
                    AvailabilitySlot.recurring == False,
                    AvailabilitySlot.end_time >= datetime.utcnow()
                )
            ))
        )
        
        # Create new slots
        new_slots = []
        
        for slot_data in availability:
            slot = AvailabilitySlot(
                reader_id=reader_id,
                start_time=slot_data.start_time,
                end_time=slot_data.end_time,
                recurring=slot_data.recurring,
                timezone=slot_data.timezone or "UTC"
            )
            
            db.add(slot)
            new_slots.append(slot)
        
        await db.commit()
        
        # Refresh the slots to get their IDs
        for slot in new_slots:
            await db.refresh(slot)
        
        return [AvailabilitySlotResponse.from_orm(slot) for slot in new_slots]
    
    async def join_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Join a reading session
        
        Args:
            db: Database session
            session_id: ID of the session to join
            user_id: ID of the user joining the session
            
        Returns:
            Dict containing the meeting link and any other necessary details
            
        Raises:
            HTTPException: If the session doesn't exist or the user doesn't have permission
        """
        result = await db.execute(
            select(ReadingSession)
            .options(
                selectinload(ReadingSession.reader),
                selectinload(ReadingSession.client)
            )
            .where(ReadingSession.id == session_id)
        )
        
        session = result.scalars().first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.reader_id != user_id and session.client_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to join this session")
        
        # Check if the session has started or is about to start
        now = datetime.utcnow()
        start_buffer = timedelta(minutes=15)  # Allow joining 15 minutes before start
        
        if now < (session.start_time - start_buffer):
            raise HTTPException(
                status_code=400,
                detail="Session has not started yet"
            )
        
        # If this is the first person joining, mark the session as in progress
        if session.status == SessionStatus.SCHEDULED:
            session.status = SessionStatus.IN_PROGRESS
            session.actual_start_time = now
            await db.commit()
            
            # Start billing
            await billing_service.start_session_billing(session.id)
            
            # Notify the other participant
            other_user_id = session.client_id if user_id == session.reader_id else session.reader_id
            
            await notification_service.send_reading_session_notification(
                db=db,
                session=session,
                notification_type="started"
            )
        
        # Generate a token for the video call
        token = self._generate_meeting_token(session_id, user_id)
        
        return {
            "meeting_link": session.meeting_link,
            "token": token,
            "session_id": str(session_id),
            "user_id": str(user_id),
            "is_reader": user_id == session.reader_id,
            "other_participant": {
                "id": str(session.reader_id if user_id == session.client_id else session.client_id),
                "name": session.reader.first_name if user_id == session.client_id else session.client.first_name,
                "is_online": await connection_manager.is_user_connected(
                    session.reader_id if user_id == session.client_id else session.client_id
                )
            },
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat(),
            "timezone": session.timezone or "UTC"
        }
    
    async def end_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        End a reading session
        
        Args:
            db: Database session
            session_id: ID of the session to end
            user_id: ID of the user ending the session
            
        Returns:
            bool: True if the session was ended successfully
            
        Raises:
            HTTPException: If the session doesn't exist or the user doesn't have permission
        """
        result = await db.execute(
            select(ReadingSession)
            .where(ReadingSession.id == session_id)
        )
        
        session = result.scalars().first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.reader_id != user_id and session.client_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to end this session")
        
        # Only allow ending if the session is in progress
        if session.status != SessionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot end a session with status {session.status}"
            )
        
        # Update session status
        session.status = SessionStatus.COMPLETED
        session.actual_end_time = datetime.utcnow()
        
        # Calculate actual duration and final cost
        if session.actual_start_time and session.actual_end_time:
            actual_duration = (session.actual_end_time - session.actual_start_time).total_seconds() / 60
            session.actual_duration_minutes = max(1, int(actual_duration))  # Minimum 1 minute
            session.final_cost = (session.rate_per_minute * session.actual_duration_minutes).quantize(Decimal('0.01'))
        
        await db.commit()
        
        # Stop billing
        await billing_service.end_session_billing(session.id)
        
        # Notify the other participant
        other_user_id = session.client_id if user_id == session.reader_id else session.reader_id
        
        await notification_service.send_reading_session_notification(
            db=db,
            session=session,
            notification_type="completed"
        )
        
        # Request review from client
        if user_id == session.client_id:
            await self._request_review(db, session)
        
        return True
    
    async def _is_time_slot_available(
        self,
        db: AsyncSession,
        reader_id: UUID,
        start_time: datetime,
        duration_minutes: int
    ) -> bool:
        """Check if a time slot is available for booking"""
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Check for overlapping sessions
        result = await db.execute(
            select(func.count(ReadingSession.id))
            .where(and_(
                ReadingSession.reader_id == reader_id,
                ReadingSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]),
                or_(
                    # New session starts during an existing session
                    and_(
                        ReadingSession.start_time <= start_time,
                        ReadingSession.end_time > start_time
                    ),
                    # New session ends during an existing session
                    and_(
                        ReadingSession.start_time < end_time,
                        ReadingSession.end_time >= end_time
                    ),
                    # New session completely contains an existing session
                    and_(
                        ReadingSession.start_time >= start_time,
                        ReadingSession.end_time <= end_time
                    )
                )
            ))
        )
        
        overlapping_sessions = result.scalar()
        
        return overlapping_sessions == 0
    
    async def _schedule_session_reminders(
        self,
        db: AsyncSession,
        session: ReadingSession
    ) -> None:
        """Schedule reminder notifications for a session"""
        # Schedule 24-hour reminder
        reminder_time = session.start_time - timedelta(hours=24)
        
        if reminder_time > datetime.utcnow():
            asyncio.create_task(
                self._send_reminder(
                    db=db,
                    session_id=session.id,
                    reminder_time=reminder_time,
                    reminder_type="24h"
                )
            )
        
        # Schedule 1-hour reminder
        reminder_time = session.start_time - timedelta(hours=1)
        
        if reminder_time > datetime.utcnow():
            asyncio.create_task(
                self._send_reminder(
                    db=db,
                    session_id=session.id,
                    reminder_time=reminder_time,
                    reminder_type="1h"
                )
            )
        
        # Schedule 15-minute reminder
        reminder_time = session.start_time - timedelta(minutes=15)
        
        if reminder_time > datetime.utcnow():
            asyncio.create_task(
                self._send_reminder(
                    db=db,
                    session_id=session.id,
                    reminder_time=reminder_time,
                    reminder_type="15m"
                )
            )
    
    async def _send_reminder(
        self,
        db: AsyncSession,
        session_id: UUID,
        reminder_time: datetime,
        reminder_type: str
    ) -> None:
        """Send a reminder notification at the specified time"""
        try:
            # Calculate sleep time
            now = datetime.utcnow()
            sleep_seconds = (reminder_time - now).total_seconds()
            
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)
            
            # Get the session
            result = await db.execute(
                select(ReadingSession)
                .options(
                    selectinload(ReadingSession.reader),
                    selectinload(ReadingSession.client)
                )
                .where(ReadingSession.id == session_id)
            )
            
            session = result.scalars().first()
            
            if not session or session.status != SessionStatus.SCHEDULED:
                return
            
            # Send reminder to client
            await notification_service.send_reading_session_notification(
                db=db,
                session=session,
                notification_type=f"reminder_{reminder_type}",
                reminder_type=reminder_type
            )
            
        except Exception as e:
            logger.error(f"Error sending reminder: {str(e)}", exc_info=True)
    
    async def _request_review(
        self,
        db: AsyncSession,
        session: ReadingSession
    ) -> None:
        """Request a review from the client"""
        try:
            # Create a review request
            review_request = ReviewRequest(
                session_id=session.id,
                reader_id=session.reader_id,
                client_id=session.client_id,
                status="pending",
                expires_at=datetime.utcnow() + timedelta(days=7)  # Review link expires in 7 days
            )
            
            db.add(review_request)
            await db.commit()
            
            # Send notification to client
            await notification_service.send_reading_session_notification(
                db=db,
                session=session,
                notification_type="review_requested",
                review_request_id=str(review_request.id)
            )
            
        except Exception as e:
            logger.error(f"Error requesting review: {str(e)}", exc_info=True)
    
    async def _get_user(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Get a user by ID with related data"""
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.reader_profile)
            )
            .where(User.id == user_id)
        )
        
        return result.scalars().first()
    
    def _generate_meeting_link(self) -> str:
        """Generate a unique meeting link"""
        # In a real app, this would generate a link to your video conferencing service
        # For now, we'll just generate a random string
        import random
        import string
        
        chars = string.ascii_lowercase + string.digits
        random_string = ''.join(random.choice(chars) for _ in range(16))
        
        return f"https://meet.soulseer.com/{random_string}"
    
    def _generate_meeting_token(self, session_id: UUID, user_id: UUID) -> str:
        """Generate a JWT token for joining the meeting"""
        import jwt
        from datetime import datetime, timedelta
        
        payload = {
            "session_id": str(session_id),
            "user_id": str(user_id),
            "exp": datetime.utcnow() + timedelta(hours=2)  # Token expires in 2 hours
        }
        
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

# Create a global instance of the session service
session_service = SessionService()
