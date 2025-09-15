from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_active_user, has_any_role
from app.models.user import User, UserRole, UserStatus
from app.models.reading_session import ReadingSession, SessionStatus, SessionType
from app.models.chat import ChatMessage, MessageType, MessageStatus
from app.models.review import Review
from app.schemas.reading_session import (
    ReadingSessionCreate,
    ReadingSessionUpdate,
    ReadingSessionResponse,
    ReadingSessionListResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ReviewCreate,
    ReviewResponse,
)
from app.schemas.common import Message, ListResponse, PaginationParams
from app.services.payment import process_payment, issue_refund
from app.services.notification import send_session_notification

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[UUID, WebSocket] = {}
        self.user_sessions: Dict[UUID, set] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID, session_id: UUID):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        if session_id not in self.user_sessions:
            self.user_sessions[session_id] = set()
        self.user_sessions[session_id].add(user_id)

    def disconnect(self, user_id: UUID, session_id: UUID):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if session_id in self.user_sessions and user_id in self.user_sessions[session_id]:
            self.user_sessions[session_id].remove(user_id)
            if not self.user_sessions[session_id]:
                del self.user_sessions[session_id]

    async def send_personal_message(self, message: str, user_id: UUID):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast_to_session(self, message: str, session_id: UUID, exclude: UUID = None):
        if session_id in self.user_sessions:
            for user_id in self.user_sessions[session_id]:
                if user_id != exclude and user_id in self.active_connections:
                    await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

# WebSocket endpoint for chat
@router.websocket("/ws/readings/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time chat during reading sessions.
    """
    try:
        # Verify token
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                options={"verify_aud": False}
            )
            user_id = payload.get("sub")
            if user_id is None:
                raise credentials_exception
            user_id = UUID(user_id)
        except (JWTError, ValidationError):
            raise credentials_exception
        
        # Get user and session
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            raise credentials_exception
            
        session = await db.get(ReadingSession, session_id)
        if session is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Verify user is part of the session
        if user_id not in [session.client_id, session.reader_id]:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Connect to the session
        await manager.connect(websocket, user_id, session_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                # Parse message
                try:
                    message_data = json.loads(data)
                    message_type = message_data.get("type", "chat")
                    content = message_data.get("content", "")
                    
                    # Create chat message
                    chat_message = ChatMessage(
                        id=uuid4(),
                        session_id=session_id,
                        sender_id=user_id,
                        message_type=MessageType[message_type.upper()],
                        content=content,
                        status=MessageStatus.DELIVERED,
                        created_at=datetime.now(timezone.utc),
                    )
                    
                    db.add(chat_message)
                    await db.commit()
                    await db.refresh(chat_message)
                    
                    # Broadcast message to all participants
                    await manager.broadcast_to_session(
                        json.dumps({
                            "id": str(chat_message.id),
                            "session_id": str(chat_message.session_id),
                            "sender_id": str(chat_message.sender_id),
                            "type": chat_message.message_type.value,
                            "content": chat_message.content,
                            "status": chat_message.status.value,
                            "created_at": chat_message.created_at.isoformat(),
                        }),
                        session_id
                    )
                    
                except json.JSONDecodeError:
                    await websocket.send_text("Invalid message format")
                except Exception as e:
                    await websocket.send_text(f"Error: {str(e)}")
                    
        except WebSocketDisconnect:
            manager.disconnect(user_id, session_id)
            
    except Exception as e:
        try:
            await websocket.close()
        except:
            pass
        raise e

# Reading session endpoints
@router.post("/", response_model=ReadingSessionResponse)
async def create_reading_session(
    session_in: ReadingSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new reading session.
    """
    # Check if reader exists and is active
    reader = await db.get(User, session_in.reader_id)
    if not reader or not reader.is_active or reader.role != UserRole.READER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reader",
        )
    
    # Check if reader is available at the requested time
    # (Implement availability check based on reader's schedule)
    
    # Check if user has an existing pending or active session with this reader
    existing_session = await db.execute(
        select(ReadingSession).where(
            and_(
                ReadingSession.client_id == current_user.id,
                ReadingSession.reader_id == reader.id,
                ReadingSession.status.in_([SessionStatus.PENDING, SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]),
            )
        )
    )
    if existing_session.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active or pending session with this reader",
        )
    
    # Process payment (if required)
    payment_intent = None
    if session_in.payment_method_id:
        try:
            payment_intent = await process_payment(
                amount=session_in.amount,
                payment_method_id=session_in.payment_method_id,
                customer_id=current_user.stripe_customer_id,
                description=f"Reading session with {reader.username}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment failed: {str(e)}",
            )
    
    # Create reading session
    db_session = ReadingSession(
        id=uuid4(),
        client_id=current_user.id,
        reader_id=reader.id,
        session_type=session_in.session_type,
        status=SessionStatus.PENDING,
        scheduled_start=session_in.scheduled_start,
        scheduled_end=session_in.scheduled_end,
        duration_minutes=session_in.duration_minutes,
        amount=session_in.amount,
        currency=session_in.currency or "USD",
        payment_intent_id=payment_intent.id if payment_intent else None,
        payment_status=payment_intent.status if payment_intent else "unpaid",
        notes=session_in.notes,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    
    # Send notification to reader
    await send_session_notification(
        user_id=reader.id,
        title="New Reading Session Request",
        message=f"You have a new reading session request from {current_user.username}",
        data={"session_id": str(db_session.id)},
    )
    
    return db_session

@router.get("/", response_model=ReadingSessionListResponse)
async def list_reading_sessions(
    pagination: PaginationParams = Depends(),
    status: Optional[SessionStatus] = None,
    session_type: Optional[SessionType] = None,
    reader_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List reading sessions with optional filtering.
    """
    query = select(ReadingSession)
    
    # Apply filters based on user role
    if current_user.role == UserRole.READER:
        query = query.where(ReadingSession.reader_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(ReadingSession.client_id == current_user.id)
    
    # Additional filters
    if status:
        query = query.where(ReadingSession.status == status)
    if session_type:
        query = query.where(ReadingSession.session_type == session_type)
    if reader_id:
        # Only allow admins to filter by reader_id
        if current_user.role == UserRole.ADMIN:
            query = query.where(ReadingSession.reader_id == reader_id)
    if client_id:
        # Only allow admins to filter by client_id
        if current_user.role == UserRole.ADMIN:
            query = query.where(ReadingSession.client_id == client_id)
    
    # Get total count
    total = await db.scalar(select([query.subquery().count()]))
    
    # Apply pagination and ordering
    query = (
        query.order_by(ReadingSession.scheduled_start.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    
    # Execute query with relationships
    result = await db.execute(
        query.options(
            selectinload(ReadingSession.client),
            selectinload(ReadingSession.reader),
            selectinload(ReadingSession.chat_messages),
        )
    )
    sessions = result.scalars().all()
    
    return {
        "data": sessions,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }

@router.get("/{session_id}", response_model=ReadingSessionResponse)
async def get_reading_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific reading session by ID.
    """
    session = await db.get(
        ReadingSession,
        session_id,
        [
            selectinload(ReadingSession.client),
            selectinload(ReadingSession.reader),
            selectinload(ReadingSession.chat_messages),
            selectinload(ReadingSession.review),
        ]
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.READER] and current_user.id != session.client_id:
        if current_user.role != UserRole.READER or current_user.id != session.reader_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session",
            )
    
    return session

@router.put("/{session_id}", response_model=ReadingSessionResponse)
async def update_reading_session(
    session_id: UUID,
    session_in: ReadingSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a reading session.
    """
    session = await db.get(ReadingSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.READER] and current_user.id != session.client_id:
        if current_user.role != UserRole.READER or current_user.id != session.reader_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this session",
            )
    
    # Only allow certain updates based on current status
    update_data = session_in.dict(exclude_unset=True)
    
    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        
        # Validate status transition
        valid_transitions = {
            SessionStatus.PENDING: [SessionStatus.CONFIRMED, SessionStatus.CANCELLED, SessionStatus.REJECTED],
            SessionStatus.CONFIRMED: [SessionStatus.IN_PROGRESS, SessionStatus.CANCELLED],
            SessionStatus.IN_PROGRESS: [SessionStatus.COMPLETED, SessionStatus.CANCELLED],
            SessionStatus.COMPLETED: [],
            SessionStatus.CANCELLED: [],
            SessionStatus.REJECTED: [],
        }
        
        if new_status not in valid_transitions.get(session.status, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from {session.status} to {new_status}",
            )
        
        # Handle specific status changes
        if new_status == SessionStatus.CANCELLED:
            # Process refund if applicable
            if session.payment_intent_id and session.payment_status == "succeeded":
                try:
                    await issue_refund(
                        payment_intent_id=session.payment_intent_id,
                        amount=session.amount,
                        reason="requested_by_customer",
                    )
                    update_data["refund_status"] = "pending"
                except Exception as e:
                    # Log error but don't fail the request
                    print(f"Error issuing refund: {str(e)}")
        
        elif new_status == SessionStatus.COMPLETED:
            # Mark payment as captured if it was authorized
            if session.payment_status == "requires_capture":
                try:
                    # Capture payment
                    payment_intent = await capture_payment(session.payment_intent_id)
                    update_data["payment_status"] = payment_intent.status
                except Exception as e:
                    # Log error but don't fail the request
                    print(f"Error capturing payment: {str(e)}")
            
            # Update session end time
            update_data["actual_end"] = datetime.now(timezone.utc)
    
    # Update session fields
    for field, value in update_data.items():
        setattr(session, field, value)
    
    session.updated_at = datetime.now(timezone.utc)
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    # Send notifications
    if "status" in update_data:
        if current_user.id == session.client_id:
            # Notify reader
            await send_session_notification(
                user_id=session.reader_id,
                title=f"Session {session.status.value.title()}",
                message=f"Your session with {current_user.username} has been {session.status.value}",
                data={"session_id": str(session.id)},
            )
        else:
            # Notify client
            await send_session_notification(
                user_id=session.client_id,
                title=f"Session {session.status.value.title()}",
                message=f"Your session with {session.reader.username} has been {session.status.value}",
                data={"session_id": str(session.id)},
            )
    
    return session

# Review endpoints
@router.post("/{session_id}/review", response_model=ReviewResponse)
async def create_review(
    session_id: UUID,
    review_in: ReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update a review for a completed reading session.
    """
    # Get session with reader relationship
    session = await db.get(
        ReadingSession,
        session_id,
        [selectinload(ReadingSession.reader), selectinload(ReadingSession.review)]
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Check permissions
    if current_user.id != session.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the client can review this session",
        )
    
    # Check if session is completed
    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only review completed sessions",
        )
    
    # Check if review already exists
    if session.review:
        # Update existing review
        for field, value in review_in.dict(exclude_unset=True).items():
            setattr(session.review, field, value)
        
        session.review.updated_at = datetime.now(timezone.utc)
        db.add(session.review)
    else:
        # Create new review
        review = Review(
            id=uuid4(),
            session_id=session_id,
            reader_id=session.reader_id,
            client_id=current_user.id,
            rating=review_in.rating,
            comment=review_in.comment,
            is_anonymous=review_in.is_anonymous,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(review)
    
    await db.commit()
    
    # Recalculate reader's average rating
    await update_reader_rating(session.reader_id, db)
    
    return session.review if session.review else review

async def update_reader_rating(reader_id: UUID, db: AsyncSession):
    """
    Update a reader's average rating based on approved reviews.
    """
    # Get all approved reviews for this reader
    stmt = select(Review).where(
        and_(
            Review.reader_id == reader_id,
            Review.status == "approved"
        )
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()
    
    if not reviews:
        return
    
    # Calculate average rating
    avg_rating = sum(review.rating for review in reviews) / len(reviews)
    
    # Update reader's profile
    reader = await db.get(User, reader_id)
    if reader and reader.reader_profile:
        reader.reader_profile.average_rating = avg_rating
        reader.reader_profile.total_reviews = len(reviews)
        reader.reader_profile.updated_at = datetime.now(timezone.utc)
        
        db.add(reader.reader_profile)
        await db.commit()

# Chat message endpoints
@router.get("/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all messages for a specific reading session.
    """
    # Verify user has access to this session
    session = await db.get(ReadingSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    if current_user.role not in [UserRole.ADMIN, UserRole.READER] and current_user.id != session.client_id:
        if current_user.role != UserRole.READER or current_user.id != session.reader_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these messages",
            )
    
    # Get messages
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    return messages

@router.post("/{session_id}/messages", response_model=ChatMessageResponse)
async def create_chat_message(
    session_id: UUID,
    message_in: ChatMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a chat message in a reading session.
    """
    # Verify user has access to this session
    session = await db.get(ReadingSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    if current_user.id not in [session.client_id, session.reader_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to send messages in this session",
        )
    
    # Check if session is active
    if session.status not in [SessionStatus.IN_PROGRESS, SessionStatus.CONFIRMED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only send messages in active sessions",
        )
    
    # Create message
    message = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        sender_id=current_user.id,
        message_type=message_in.message_type or MessageType.TEXT,
        content=message_in.content,
        status=MessageStatus.DELIVERED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    # Update session's last activity
    session.updated_at = datetime.now(timezone.utc)
    db.add(session)
    await db.commit()
    
    # Broadcast message via WebSocket
    await manager.broadcast_to_session(
        json.dumps({
            "id": str(message.id),
            "session_id": str(message.session_id),
            "sender_id": str(message.sender_id),
            "type": message.message_type.value,
            "content": message.content,
            "status": message.status.value,
            "created_at": message.created_at.isoformat(),
        }),
        session_id
    )
    
    return message
