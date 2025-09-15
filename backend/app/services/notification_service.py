import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import json
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    Notification, 
    User, 
    NotificationPreference,
    ReadingSession,
    Message,
    Review,
    Transaction
)
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationPreferenceUpdate,
    NotificationType
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.pending_notifications: List[Dict] = []
        self.is_running = False
    
    async def start_scheduler(self):
        """Start the notification scheduler"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("Starting notification scheduler...")
        
        while self.is_running:
            try:
                await self._process_pending_notifications()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Error in notification scheduler: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
    
    async def stop_scheduler(self):
        """Stop the notification scheduler"""
        self.is_running = False
        logger.info("Stopping notification scheduler...")
    
    async def _process_pending_notifications(self):
        """Process all pending notifications"""
        if not self.pending_notifications:
            return
            
        # Process notifications in batches
        batch_size = 50
        batch = self.pending_notifications[:batch_size]
        self.pending_notifications = self.pending_notifications[batch_size:]
        
        async with get_db() as db:
            for notification_data in batch:
                try:
                    await self._send_notification(db, **notification_data)
                except Exception as e:
                    logger.error(f"Error sending notification: {str(e)}", exc_info=True)
    
    async def create_notification(
        self,
        db: AsyncSession,
        notification: NotificationCreate,
        send_email: bool = True
    ) -> NotificationResponse:
        """Create a new notification"""
        # Check if user exists
        result = await db.execute(select(User).where(User.id == notification.user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check notification preferences
        if notification.notification_type != NotificationType.SYSTEM:
            result = await db.execute(
                select(NotificationPreference)
                .where(NotificationPreference.user_id == notification.user_id)
            )
            prefs = result.scalars().first()
            
            if prefs and not prefs.enabled:
                logger.info(f"Notifications disabled for user {notification.user_id}")
                return None
                
            # Check if this type of notification is enabled
            if prefs and notification.notification_type in prefs.disabled_types:
                logger.info(f"Notification type {notification.notification_type} disabled for user {notification.user_id}")
                return None
        
        # Save notification to database
        db_notification = Notification(
            user_id=notification.user_id,
            title=notification.title,
            message=notification.message,
            notification_type=notification.notification_type,
            data=notification.data,
            is_read=False
        )
        db.add(db_notification)
        
        # Commit to get the notification ID
        await db.commit()
        await db.refresh(db_notification)
        
        # Queue for immediate delivery
        if send_email and notification.notification_type != NotificationType.EMAIL:
            self.pending_notifications.append({
                "notification_id": db_notification.id,
                "user_id": notification.user_id,
                "title": notification.title,
                "message": notification.message,
                "notification_type": notification.notification_type,
                "data": notification.data
            })
        
        return NotificationResponse.from_orm(db_notification)
    
    async def _send_notification(
        self,
        db: AsyncSession,
        notification_id: str,
        user_id: str,
        title: str,
        message: str,
        notification_type: str,
        data: Optional[Dict] = None
    ) -> bool:
        """Send a notification through the appropriate channels"""
        try:
            # Get user and preferences
            result = await db.execute(
                select(User, NotificationPreference)
                .outerjoin(NotificationPreference, NotificationPreference.user_id == User.id)
                .where(User.id == user_id)
            )
            user, prefs = result.first() or (None, None)
            
            if not user:
                logger.error(f"User {user_id} not found for notification {notification_id}")
                return False
            
            # Check if email notification is enabled
            send_email = True
            if prefs and not prefs.email_enabled:
                send_email = False
            
            # Check if push notification is enabled
            send_push = True
            if prefs and not prefs.push_enabled:
                send_push = False
            
            # Send email if enabled
            if send_email and user.email:
                try:
                    email_sent = await self._send_email_notification(
                        email=user.email,
                        name=user.first_name or "User",
                        title=title,
                        message=message,
                        notification_type=notification_type,
                        data=data
                    )
                    
                    if email_sent:
                        logger.info(f"Email notification sent to {user.email}")
                    else:
                        logger.warning(f"Failed to send email notification to {user.email}")
                except Exception as e:
                    logger.error(f"Error sending email notification: {str(e)}", exc_info=True)
            
            # Send push notification if enabled and user has devices
            if send_push and user.push_tokens:
                try:
                    # This would be implemented with a push notification service
                    # like Firebase Cloud Messaging (FCM) or Apple Push Notification Service (APNS)
                    push_sent = await self._send_push_notification(
                        user=user,
                        title=title,
                        message=message,
                        data=data
                    )
                    
                    if push_sent:
                        logger.info(f"Push notification sent to user {user.id}")
                    else:
                        logger.warning(f"Failed to send push notification to user {user.id}")
                except Exception as e:
                    logger.error(f"Error sending push notification: {str(e)}", exc_info=True)
            
            # Mark notification as sent
            await db.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(is_sent=True, sent_at=datetime.utcnow())
            )
            await db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Error in _send_notification: {str(e)}", exc_info=True)
            return False
    
    async def _send_email_notification(
        self,
        email: str,
        name: str,
        title: str,
        message: str,
        notification_type: str,
        data: Optional[Dict] = None
    ) -> bool:
        """Send an email notification"""
        try:
            # Customize email based on notification type
            subject = f"SoulSeer - {title}"
            
            # Add notification type to data for template
            template_data = {
                "title": title,
                "message": message,
                "name": name,
                "type": notification_type,
                "data": data or {},
                "support_email": settings.SUPPORT_EMAIL
            }
            
            # Load appropriate template based on notification type
            template_name = f"notifications/{notification_type.lower()}.html"
            
            return await email_service.send_email(
                to_email=email,
                subject=subject,
                template_name=template_name,
                template_data=template_data
            )
            
        except Exception as e:
            logger.error(f"Error in _send_email_notification: {str(e)}", exc_info=True)
            return False
    
    async def _send_push_notification(
        self,
        user: User,
        title: str,
        message: str,
        data: Optional[Dict] = None
    ) -> bool:
        """Send a push notification to user's devices"""
        # This is a placeholder for actual push notification implementation
        # In a real app, you would integrate with FCM, APNS, or a service like OneSignal
        
        # Example implementation with Firebase Cloud Messaging (FCM):
        """
        from firebase_admin import messaging
        
        try:
            # Create a message for each device token
            messages = []
            for token in user.push_tokens:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=message,
                    ),
                    data=data or {},
                    token=token,
                )
                messages.append(message)
            
            # Send messages in batches
            batch_size = 500  # FCM batch limit
            for i in range(0, len(messages), batch_size):
                batch = messaging.BatchResponse()
                for message in messages[i:i+batch_size]:
                    try:
                        response = messaging.send(message)
                        batch.add_response(response)
                    except Exception as e:
                        logger.error(f"Error sending push notification: {str(e)}")
                        
                        # Remove invalid tokens
                        if "registration-token-not-registered" in str(e):
                            await self._remove_invalid_push_token(user.id, message.token)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in _send_push_notification: {str(e)}", exc_info=True)
            return False
        """
        
        # For now, just log that we would send a push
        logger.info(f"Would send push notification to user {user.id}: {title} - {message}")
        return True
    
    async def _remove_invalid_push_token(self, user_id: str, token: str) -> None:
        """Remove an invalid push token from the database"""
        async with get_db() as db:
            # This would update the user's push_tokens array to remove the invalid token
            # Implementation depends on how you're storing push tokens
            pass
    
    # Notification Management
    async def get_notifications(
        self,
        db: AsyncSession,
        user_id: str,
        read: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[NotificationResponse]:
        """Get notifications for a user"""
        query = select(Notification).where(Notification.user_id == user_id)
        
        if read is not None:
            query = query.where(Notification.is_read == read)
            
        result = await db.execute(
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        
        notifications = result.scalars().all()
        return [NotificationResponse.from_orm(n) for n in notifications]
    
    async def mark_as_read(
        self,
        db: AsyncSession,
        notification_id: str,
        user_id: str
    ) -> bool:
        """Mark a notification as read"""
        result = await db.execute(
            update(Notification)
            .where(and_(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ))
            .values(is_read=True, read_at=datetime.utcnow())
        )
        
        await db.commit()
        return result.rowcount > 0
    
    async def mark_all_as_read(
        self,
        db: AsyncSession,
        user_id: str
    ) -> int:
        """Mark all notifications as read for a user"""
        result = await db.execute(
            update(Notification)
            .where(and_(
                Notification.user_id == user_id,
                Notification.is_read == False
            ))
            .values(is_read=True, read_at=datetime.utcnow())
        )
        
        await db.commit()
        return result.rowcount
    
    async def delete_notification(
        self,
        db: AsyncSession,
        notification_id: str,
        user_id: str
    ) -> bool:
        """Delete a notification"""
        result = await db.execute(
            select(Notification)
            .where(and_(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ))
        )
        
        notification = result.scalars().first()
        if not notification:
            return False
            
        await db.delete(notification)
        await db.commit()
        return True
    
    # Notification Preferences
    async def get_notification_preferences(
        self,
        db: AsyncSession,
        user_id: str
    ) -> Dict[str, Any]:
        """Get notification preferences for a user"""
        result = await db.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )
        
        prefs = result.scalars().first()
        
        # Return default preferences if none exist
        if not prefs:
            return {
                "enabled": True,
                "email_enabled": True,
                "push_enabled": True,
                "disabled_types": []
            }
            
        return {
            "enabled": prefs.enabled,
            "email_enabled": prefs.email_enabled,
            "push_enabled": prefs.push_enabled,
            "disabled_types": prefs.disabled_types or []
        }
    
    async def update_notification_preferences(
        self,
        db: AsyncSession,
        user_id: str,
        preferences: NotificationPreferenceUpdate
    ) -> Dict[str, Any]:
        """Update notification preferences for a user"""
        result = await db.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )
        
        prefs = result.scalars().first()
        
        if not prefs:
            # Create new preferences
            prefs = NotificationPreference(
                user_id=user_id,
                enabled=preferences.enabled,
                email_enabled=preferences.email_enabled,
                push_enabled=preferences.push_enabled,
                disabled_types=preferences.disabled_types or []
            )
            db.add(prefs)
        else:
            # Update existing preferences
            if preferences.enabled is not None:
                prefs.enabled = preferences.enabled
            if preferences.email_enabled is not None:
                prefs.email_enabled = preferences.email_enabled
            if preferences.push_enabled is not None:
                prefs.push_enabled = preferences.push_enabled
            if preferences.disabled_types is not None:
                prefs.disabled_types = preferences.disabled_types
        
        await db.commit()
        await db.refresh(prefs)
        
        return {
            "enabled": prefs.enabled,
            "email_enabled": prefs.email_enabled,
            "push_enabled": prefs.push_enabled,
            "disabled_types": prefs.disabled_types or []
        }
    
    # Helper methods for common notifications
    async def send_new_message_notification(
        self,
        db: AsyncSession,
        message: Message,
        recipient_id: str
    ) -> None:
        """Send notification for a new message"""
        sender_name = f"{message.sender.first_name} {message.sender.last_name}".strip()
        
        await self.create_notification(
            db=db,
            notification=NotificationCreate(
                user_id=recipient_id,
                title="New Message",
                message=f"You have a new message from {sender_name}",
                notification_type=NotificationType.MESSAGE,
                data={
                    "message_id": str(message.id),
                    "sender_id": str(message.sender_id),
                    "sender_name": sender_name,
                    "thread_id": str(message.thread_id)
                }
            )
        )
    
    async def send_reading_session_notification(
        self,
        db: AsyncSession,
        session: ReadingSession,
        notification_type: str,
        **kwargs
    ) -> None:
        """Send notification for reading session events"""
        if notification_type == "scheduled":
            title = "Reading Session Scheduled"
            message = f"Your reading with {session.reader.display_name} is scheduled for {session.scheduled_time.strftime('%B %d, %Y at %I:%M %p')} {session.timezone}"
            user_id = session.client_id
        elif notification_type == "starting_soon":
            title = "Reading Starting Soon"
            message = f"Your reading with {session.reader.display_name} is starting in 15 minutes"
            user_id = session.client_id
        elif notification_type == "started":
            title = "Reading Session Started"
            message = f"Your reading with {session.reader.display_name} has started"
            user_id = session.client_id
        elif notification_type == "completed":
            title = "Reading Session Completed"
            message = f"Your reading with {session.reader.display_name} has been completed"
            user_id = session.client_id
        elif notification_type == "cancelled":
            title = "Reading Session Cancelled"
            message = f"Your reading with {session.reader.display_name} has been cancelled"
            user_id = session.client_id
        else:
            return
        
        await self.create_notification(
            db=db,
            notification=NotificationCreate(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=NotificationType.READING,
                data={
                    "session_id": str(session.id),
                    "reader_id": str(session.reader_id),
                    "reader_name": session.reader.display_name,
                    "type": notification_type,
                    **kwargs
                }
            )
        )
    
    async def send_payment_notification(
        self,
        db: AsyncSession,
        transaction: Transaction,
        notification_type: str = "payment_received"
    ) -> None:
        """Send notification for payment events"""
        if notification_type == "payment_received":
            title = "Payment Received"
            message = f"Your payment of ${transaction.amount:.2f} has been received"
        elif notification_type == "payment_failed":
            title = "Payment Failed"
            message = f"Your payment of ${transaction.amount:.2f} has failed"
        elif notification_type == "payout_processed":
            title = "Payout Processed"
            message = f"Your payout of ${transaction.amount:.2f} has been processed"
        else:
            return
        
        await self.create_notification(
            db=db,
            notification=NotificationCreate(
                user_id=transaction.user_id,
                title=title,
                message=message,
                notification_type=NotificationType.PAYMENT,
                data={
                    "transaction_id": str(transaction.id),
                    "amount": float(transaction.amount),
                    "currency": transaction.currency,
                    "type": notification_type
                }
            )
        )
    
    async def send_review_notification(
        self,
        db: AsyncSession,
        review: Review
    ) -> None:
        """Send notification for new reviews"""
        await self.create_notification(
            db=db,
            notification=NotificationCreate(
                user_id=review.reader_id,
                title="New Review",
                message=f"You have received a new {review.rating}-star review from {review.client.display_name}",
                notification_type=NotificationType.REVIEW,
                data={
                    "review_id": str(review.id),
                    "rating": review.rating,
                    "reviewer_id": str(review.client_id),
                    "reviewer_name": review.client.display_name,
                    "message": review.comment
                }
            )
        )

# Create a global instance of the notification service
notification_service = NotificationService()
