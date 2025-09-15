""
Notification service for sending real-time and push notifications to users.
"""
import json
from typing import Dict, Any, List, Optional, Union
from uuid import UUID
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationType, NotificationStatus
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationResponse
from app.core.websocket import manager as ws_manager


async def send_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.INFO,
    data: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
) -> Notification:
    """
    Send a notification to a specific user.
    
    Args:
        db: Database session
        user_id: ID of the user to notify
        title: Notification title
        message: Notification message
        notification_type: Type of notification
        data: Additional data to include with the notification
        action_url: URL to navigate to when the notification is clicked
        
    Returns:
        The created notification
    """
    # Create notification in database
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        data=data or {},
        action_url=action_url,
        status=NotificationStatus.UNREAD,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    # Send real-time notification via WebSocket if user is connected
    await ws_manager.send_personal_notification(
        user_id=user_id,
        notification={
            "id": str(notification.id),
            "title": title,
            "message": message,
            "type": notification_type.value,
            "data": data or {},
            "action_url": action_url,
            "created_at": notification.created_at.isoformat(),
            "is_read": False,
        }
    )
    
    # TODO: Implement push notification for mobile apps
    # await _send_push_notification(user_id, title, message, data, action_url)
    
    return notification

async def mark_notification_read(
    db: AsyncSession,
    notification_id: UUID,
    user_id: UUID,
) -> Optional[Notification]:
    """
    Mark a notification as read.
    
    Args:
        db: Database session
        notification_id: ID of the notification to mark as read
        user_id: ID of the user who owns the notification
        
    Returns:
        The updated notification, or None if not found
    """
    # Get the notification
    notification = await db.get(Notification, notification_id)
    
    # Verify ownership
    if not notification or notification.user_id != user_id:
        return None
    
    # Update status if not already read
    if notification.status != NotificationStatus.READ:
        notification.status = NotificationStatus.READ
        notification.read_at = datetime.now(timezone.utc)
        
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
    
    return notification

async def mark_all_notifications_read(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """
    Mark all unread notifications as read for a user.
    
    Args:
        db: Database session
        user_id: ID of the user
        
    Returns:
        Number of notifications marked as read
    """
    result = await db.execute(
        Notification.__table__.update()
        .where(
            (Notification.user_id == user_id) &
            (Notification.status == NotificationStatus.UNREAD)
        )
        .values(
            status=NotificationStatus.READ,
            read_at=datetime.now(timezone.utc)
        )
    )
    
    await db.commit()
    return result.rowcount

async def get_user_notifications(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> List[Notification]:
    """
    Get notifications for a user.
    
    Args:
        db: Database session
        user_id: ID of the user
        limit: Maximum number of notifications to return
        offset: Number of notifications to skip
        unread_only: Whether to return only unread notifications
        
    Returns:
        List of notifications
    """
    query = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    if unread_only:
        query = query.where(Notification.status == NotificationStatus.UNREAD)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_unread_count(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """
    Get the number of unread notifications for a user.
    
    Args:
        db: Database session
        user_id: ID of the user
        
    Returns:
        Number of unread notifications
    """
    result = await db.execute(
        select([func.count()])
        .select_from(Notification)
        .where(
            (Notification.user_id == user_id) &
            (Notification.status == NotificationStatus.UNREAD)
        )
    )
    
    return result.scalar() or 0

async def delete_notification(
    db: AsyncSession,
    notification_id: UUID,
    user_id: UUID,
) -> bool:
    """
    Delete a notification.
    
    Args:
        db: Database session
        notification_id: ID of the notification to delete
        user_id: ID of the user who owns the notification
        
    Returns:
        True if the notification was deleted, False otherwise
    """
    # Get the notification
    notification = await db.get(Notification, notification_id)
    
    # Verify ownership
    if not notification or notification.user_id != user_id:
        return False
    
    # Delete the notification
    await db.delete(notification)
    await db.commit()
    
    return True

# Helper functions for specific notification types

async def send_session_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    session_id: UUID,
    notification_type: NotificationType = NotificationType.INFO,
) -> Notification:
    """
    Send a notification related to a reading session.
    """
    return await send_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        data={"session_id": str(session_id)},
        action_url=f"/sessions/{session_id}",
    )

async def send_message_notification(
    db: AsyncSession,
    user_id: UUID,
    sender_name: str,
    message_preview: str,
    session_id: UUID,
) -> Notification:
    """
    Send a notification for a new message in a session.
    """
    return await send_notification(
        db=db,
        user_id=user_id,
        title=f"New message from {sender_name}",
        message=message_preview[:100] + ("..." if len(message_preview) > 100 else ""),
        notification_type=NotificationType.MESSAGE,
        data={
            "session_id": str(session_id),
            "sender_name": sender_name,
        },
        action_url=f"/sessions/{session_id}#messages",
    )

async def send_payment_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    payment_id: str,
    amount: float,
    currency: str,
) -> Notification:
    """
    Send a notification related to a payment.
    """
    return await send_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=NotificationType.PAYMENT,
        data={
            "payment_id": payment_id,
            "amount": amount,
            "currency": currency,
        },
        action_url=f"/payments/{payment_id}",
    )

async def send_system_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    action_url: Optional[str] = None,
) -> Notification:
    """
    Send a system notification to a user.
    """
    return await send_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=NotificationType.SYSTEM,
        action_url=action_url,
    )
