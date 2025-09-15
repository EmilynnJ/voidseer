import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Any, Union
import asyncio
import json
import stripe

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, delete
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.models import (
    User,
    Transaction,
    Payout,
    ReadingSession,
    ReaderProfile,
    BankAccount,
    Notification
)
from app.schemas.payout import (
    PayoutCreate,
    PayoutResponse,
    PayoutStatus,
    PayoutMethodCreate,
    PayoutMethodResponse,
    PayoutMethodType,
    PayoutMethodUpdate,
    PayoutEstimateResponse
)
from app.services.notification_service import notification_service
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

class PayoutService:
    """Service for managing payouts to readers"""
    
    async def calculate_earnings(
        self,
        db: AsyncSession,
        reader_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate a reader's earnings for a given time period
        
        Args:
            db: Database session
            reader_id: ID of the reader
            start_date: Start of the date range (inclusive)
            end_date: End of the date range (inclusive)
            
        Returns:
            Dict containing earnings summary
        """
        # Set default date range if not provided (last 30 days)
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Get completed sessions in the date range
        result = await db.execute(
            select(
                func.sum(ReadingSession.final_cost).label("total_earnings"),
                func.count(ReadingSession.id).label("session_count")
            )
            .where(and_(
                ReadingSession.reader_id == reader_id,
                ReadingSession.status == "completed",
                ReadingSession.actual_end_time >= start_date,
                ReadingSession.actual_end_time <= end_date,
                ReadingSession.payout_id.is_(None)  # Only include unpaid sessions
            ))
        )
        
        earnings_data = result.first()
        total_earnings = earnings_data.total_earnings or Decimal('0')
        session_count = earnings_data.session_count or 0
        
        # Get reader's profile for platform fee percentage
        result = await db.execute(
            select(ReaderProfile.platform_fee_percent)
            .where(ReaderProfile.user_id == reader_id)
        )
        
        platform_fee_percent = result.scalar() or settings.DEFAULT_PLATFORM_FEE_PERCENT
        
        # Calculate fees and net amount
        platform_fee = (total_earnings * Decimal(platform_fee_percent) / 100).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )
        
        net_amount = (total_earnings - platform_fee).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )
        
        # Get pending and completed payouts in the date range
        result = await db.execute(
            select(
                Payout.status,
                func.sum(Payout.amount).label("amount")
            )
            .where(and_(
                Payout.reader_id == reader_id,
                Payout.paid_at >= start_date,
                Payout.paid_at <= end_date
            ))
            .group_by(Payout.status)
        )
        
        payouts = result.all()
        
        paid_out = Decimal('0')
        pending_payouts = Decimal('0')
        
        for status, amount in payouts:
            if status == "paid":
                paid_out += amount or Decimal('0')
            elif status == "pending":
                pending_payouts += amount or Decimal('0')
        
        # Get next payout date (if applicable)
        next_payout_date = None
        if net_amount >= settings.MINIMUM_PAYOUT_AMOUNT:
            # Next payout is on the next configured payout day (e.g., every Friday)
            today = datetime.utcnow()
            days_until_payout = (settings.PAYOUT_DAY - today.weekday()) % 7
            
            # If today is the payout day and it's after the cutoff time, schedule for next week
            if days_until_payout == 0 and today.hour >= settings.PAYOUT_CUTOFF_HOUR:
                days_until_payout = 7
                
            next_payout_date = (today + timedelta(days=days_until_payout)).replace(
                hour=settings.PAYOUT_CUTOFF_HOUR,
                minute=0,
                second=0,
                microsecond=0
            )
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_earnings": float(total_earnings),
            "session_count": session_count,
            "platform_fee_percent": float(platform_fee_percent),
            "platform_fee": float(platform_fee),
            "net_amount": float(net_amount),
            "paid_out": float(paid_out),
            "pending_payouts": float(pending_payouts),
            "available_for_payout": float(net_amount - pending_payouts - paid_out),
            "minimum_payout_amount": float(settings.MINIMUM_PAYOUT_AMOUNT),
            "next_payout_date": next_payout_date.isoformat() if next_payout_date else None,
            "payout_schedule": settings.PAYOUT_SCHEDULE
        }
    
    async def request_payout(
        self,
        db: AsyncSession,
        reader_id: str,
        amount: Decimal,
        payout_method_id: str,
        notes: Optional[str] = None
    ) -> PayoutResponse:
        """
        Request a payout
        
        Args:
            db: Database session
            reader_id: ID of the reader requesting the payout
            amount: Amount to payout
            payout_method_id: ID of the payout method to use
            notes: Optional notes for the payout
            
        Returns:
            PayoutResponse: The created payout
            
        Raises:
            HTTPException: If the request is invalid
        """
        # Validate amount
        if amount < settings.MINIMUM_PAYOUT_AMOUNT:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum payout amount is {settings.MINIMUM_PAYOUT_AMOUNT}"
            )
        
        # Get reader's available balance
        earnings = await self.calculate_earnings(db, reader_id)
        available_balance = Decimal(str(earnings["available_for_payout"]))
        
        if amount > available_balance:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Available: {available_balance}"
            )
        
        # Get payout method
        payout_method = await self.get_payout_method(db, payout_method_id, reader_id)
        
        if not payout_method:
            raise HTTPException(status_code=404, detail="Payout method not found")
        
        # Create payout record
        payout = Payout(
            reader_id=reader_id,
            amount=amount,
            currency="USD",  # For now, hardcode to USD
            status=PayoutStatus.PENDING,
            payout_method_id=payout_method_id,
            notes=notes,
            scheduled_date=datetime.utcnow()  # Will be processed on next payout run
        )
        
        db.add(payout)
        
        # Mark sessions as paid (in a real app, you'd have a more sophisticated way to track this)
        await db.execute(
            update(ReadingSession)
            .where(and_(
                ReadingSession.reader_id == reader_id,
                ReadingSession.status == "completed",
                ReadingSession.payout_id.is_(None)
            ))
            .values(payout_id=payout.id)
        )
        
        await db.commit()
        await db.refresh(payout)
        
        # Notify admin (in a real app, this would be an email or in-app notification)
        await notification_service.create_notification(
            db=db,
            notification=NotificationCreate(
                user_id=settings.ADMIN_USER_ID,  # Assuming you have an admin user
                title="New Payout Request",
                message=f"Reader {reader_id} has requested a payout of ${amount}",
                notification_type="payout_requested",
                data={
                    "payout_id": str(payout.id),
                    "reader_id": reader_id,
                    "amount": float(amount),
                    "payout_method": payout_method.dict()
                }
            )
        )
        
        return PayoutResponse.from_orm(payout)
    
    async def process_payouts(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Process all pending payouts
        
        This would typically be run as a scheduled job (e.g., daily or weekly)
        """
        # Get all pending payouts
        result = await db.execute(
            select(Payout)
            .options(
                selectinload(Payout.reader).selectinload(User.reader_profile),
                selectinload(Payout.payout_method)
            )
            .where(Payout.status == PayoutStatus.PENDING)
            .order_by(Payout.created_at.asc())
        )
        
        payouts = result.scalars().all()
        
        processed = 0
        failed = 0
        total_amount = Decimal('0')
        
        for payout in payouts:
            try:
                # Process the payout with Stripe
                if not payout.payout_method or not payout.payout_method.stripe_payment_method_id:
                    logger.error(f"Payout {payout.id} has no valid payout method")
                    payout.status = PayoutStatus.FAILED
                    payout.failure_reason = "No valid payout method"
                    failed += 1
                    continue
                
                # In a real app, you'd use the Stripe API to create a transfer
                # For now, we'll just simulate it
                transfer = {
                    "id": f"simulated_transfer_{payout.id}",
                    "amount": int(payout.amount * 100),  # Amount in cents
                    "currency": payout.currency.lower(),
                    "status": "paid"
                }
                
                # Update payout status
                payout.status = PayoutStatus.PAID
                payout.processed_at = datetime.utcnow()
                payout.transaction_id = transfer["id"]
                payout.metadata = {
                    "stripe_transfer_id": transfer["id"],
                    "processed_at": datetime.utcnow().isoformat()
                }
                
                # Create a transaction record
                transaction = Transaction(
                    user_id=payout.reader_id,
                    amount=-payout.amount,  # Negative for payouts
                    currency=payout.currency,
                    transaction_type="payout",
                    status="completed",
                    description=f"Payout to {payout.payout_method.type}",
                    reference_id=payout.id,
                    metadata={
                        "payout_id": str(payout.id),
                        "payout_method_id": str(payout.payout_method_id),
                        "stripe_transfer_id": transfer["id"]
                    }
                )
                
                db.add(transaction)
                
                # Update reader's balance
                await db.execute(
                    update(User)
                    .where(User.id == payout.reader_id)
                    .values(balance=User.balance - payout.amount)
                )
                
                await db.commit()
                
                # Notify reader
                await notification_service.create_notification(
                    db=db,
                    notification=NotificationCreate(
                        user_id=payout.reader_id,
                        title="Payout Processed",
                        message=f"Your payout of ${payout.amount} has been processed.",
                        notification_type="payout_processed",
                        data={
                            "payout_id": str(payout.id),
                            "amount": float(payout.amount),
                            "currency": payout.currency,
                            "payout_method": {
                                "type": payout.payout_method.type,
                                "last4": payout.payout_method.last4 if hasattr(payout.payout_method, 'last4') else None,
                                "bank_name": getattr(payout.payout_method, 'bank_name', None)
                            },
                            "transaction_id": transfer["id"]
                        }
                    )
                )
                
                processed += 1
                total_amount += payout.amount
                
            except Exception as e:
                logger.error(f"Error processing payout {payout.id}: {str(e)}", exc_info=True)
                
                # Update payout status
                payout.status = PayoutStatus.FAILED
                payout.failure_reason = str(e)[:255]  # Truncate to fit in the database
                
                # Create a failed transaction record
                transaction = Transaction(
                    user_id=payout.reader_id,
                    amount=Decimal('0'),  # No amount for failed payouts
                    currency=payout.currency,
                    transaction_type="payout_failed",
                    status="failed",
                    description=f"Failed payout to {payout.payout_method.type if payout.payout_method else 'unknown'}",
                    reference_id=payout.id,
                    metadata={
                        "payout_id": str(payout.id),
                        "payout_method_id": str(payout.payout_method_id) if payout.payout_method_id else None,
                        "error": str(e)
                    }
                )
                
                db.add(transaction)
                
                await db.commit()
                
                # Notify admin of failure
                await notification_service.create_notification(
                    db=db,
                    notification=NotificationCreate(
                        user_id=settings.ADMIN_USER_ID,
                        title="Payout Failed",
                        message=f"Failed to process payout {payout.id}: {str(e)}",
                        notification_type="payout_failed",
                        data={
                            "payout_id": str(payout.id),
                            "reader_id": payout.reader_id,
                            "amount": float(payout.amount),
                            "error": str(e)
                        }
                    )
                )
                
                failed += 1
        
        return {
            "total_processed": processed,
            "total_failed": failed,
            "total_amount": float(total_amount),
            "currency": "USD"
        }
    
    # Payout Methods
    
    async def get_payout_methods(
        self,
        db: AsyncSession,
        user_id: str
    ) -> List[PayoutMethodResponse]:
        """
        Get all payout methods for a user
        """
        result = await db.execute(
            select(BankAccount)
            .where(BankAccount.user_id == user_id)
            .order_by(BankAccount.is_default.desc(), BankAccount.created_at.desc())
        )
        
        accounts = result.scalars().all()
        
        # Convert to PayoutMethodResponse
        methods = []
        for account in accounts:
            methods.append(PayoutMethodResponse(
                id=account.id,
                type=PayoutMethodType.BANK_ACCOUNT,
                is_default=account.is_default,
                bank_name=account.bank_name,
                last4=account.last4,
                routing_number=account.routing_number[-4:] if account.routing_number else None,
                account_holder_name=account.account_holder_name,
                account_holder_type=account.account_holder_type,
                created_at=account.created_at,
                updated_at=account.updated_at
            ))
        
        return methods
    
    async def get_payout_method(
        self,
        db: AsyncSession,
        method_id: str,
        user_id: str
    ) -> Optional[PayoutMethodResponse]:
        """
        Get a specific payout method
        """
        result = await db.execute(
            select(BankAccount)
            .where(and_(
                BankAccount.id == method_id,
                BankAccount.user_id == user_id
            ))
        )
        
        account = result.scalars().first()
        
        if not account:
            return None
        
        return PayoutMethodResponse(
            id=account.id,
            type=PayoutMethodType.BANK_ACCOUNT,
            is_default=account.is_default,
            bank_name=account.bank_name,
            last4=account.last4,
            routing_number=account.routing_number[-4:] if account.routing_number else None,
            account_holder_name=account.account_holder_name,
            account_holder_type=account.account_holder_type,
            created_at=account.created_at,
            updated_at=account.updated_at
        )
    
    async def create_payout_method(
        self,
        db: AsyncSession,
        user_id: str,
        method_data: PayoutMethodCreate
    ) -> PayoutMethodResponse:
        """
        Add a new payout method
        """
        # In a real app, you'd validate the bank account with Stripe or another service
        # For now, we'll just create a record
        
        # Make sure this is the only default if specified
        if method_data.is_default:
            await db.execute(
                update(BankAccount)
                .where(BankAccount.user_id == user_id)
                .values(is_default=False)
            )
        
        # Create a Stripe bank account token
        try:
            # In a real app, you'd create a bank account token with Stripe.js on the frontend
            # and pass it to your backend. For now, we'll simulate it.
            bank_account = {
                "id": f"ba_simulated_{user_id[-8:]}",
                "bank_name": method_data.bank_name,
                "last4": method_data.account_number[-4:],
                "routing_number": method_data.routing_number,
                "account_holder_name": method_data.account_holder_name,
                "account_holder_type": method_data.account_holder_type or "individual"
            }
            
            # Create the bank account record
            account = BankAccount(
                user_id=user_id,
                stripe_bank_account_id=bank_account["id"],
                bank_name=bank_account["bank_name"],
                last4=bank_account["last4"],
                routing_number=bank_account["routing_number"],
                account_holder_name=bank_account["account_holder_name"],
                account_holder_type=bank_account["account_holder_type"],
                is_default=method_data.is_default,
                is_verified=True  # In a real app, you'd need to verify micro-deposits
            )
            
            db.add(account)
            await db.commit()
            await db.refresh(account)
            
            # Return the created method
            return PayoutMethodResponse(
                id=account.id,
                type=PayoutMethodType.BANK_ACCOUNT,
                is_default=account.is_default,
                bank_name=account.bank_name,
                last4=account.last4,
                routing_number=account.routing_number[-4:] if account.routing_number else None,
                account_holder_name=account.account_holder_name,
                account_holder_type=account.account_holder_type,
                created_at=account.created_at,
                updated_at=account.updated_at
            )
            
        except Exception as e:
            logger.error(f"Error creating payout method: {str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"Failed to add payout method: {str(e)}")
    
    async def update_payout_method(
        self,
        db: AsyncSession,
        method_id: str,
        user_id: str,
        update_data: PayoutMethodUpdate
    ) -> PayoutMethodResponse:
        """
        Update a payout method
        """
        # Get the existing method
        result = await db.execute(
            select(BankAccount)
            .where(and_(
                BankAccount.id == method_id,
                BankAccount.user_id == user_id
            ))
        )
        
        account = result.scalars().first()
        
        if not account:
            raise HTTPException(status_code=404, detail="Payout method not found")
        
        # If setting as default, unset other defaults
        if update_data.is_default and not account.is_default:
            await db.execute(
                update(BankAccount)
                .where(BankAccount.user_id == user_id)
                .values(is_default=False)
            )
        
        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        
        for field, value in update_dict.items():
            if hasattr(account, field):
                setattr(account, field, value)
        
        account.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(account)
        
        # Return the updated method
        return PayoutMethodResponse(
            id=account.id,
            type=PayoutMethodType.BANK_ACCOUNT,
            is_default=account.is_default,
            bank_name=account.bank_name,
            last4=account.last4,
            routing_number=account.routing_number[-4:] if account.routing_number else None,
            account_holder_name=account.account_holder_name,
            account_holder_type=account.account_holder_type,
            created_at=account.created_at,
            updated_at=account.updated_at
        )
    
    async def delete_payout_method(
        self,
        db: AsyncSession,
        method_id: str,
        user_id: str
    ) -> bool:
        """
        Delete a payout method
        """
        # Check if this is the user's only payout method
        result = await db.execute(
            select(func.count(BankAccount.id))
            .where(BankAccount.user_id == user_id)
        )
        
        method_count = result.scalar()
        
        if method_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete your only payout method"
            )
        
        # Delete the method
        result = await db.execute(
            delete(BankAccount)
            .where(and_(
                BankAccount.id == method_id,
                BankAccount.user_id == user_id
            ))
            .returning(BankAccount.is_default)
        )
        
        deleted = result.first()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Payout method not found")
        
        # If we deleted the default, set another method as default
        if deleted[0]:  # is_default was True
            # Get the most recently added method
            result = await db.execute(
                select(BankAccount)
                .where(BankAccount.user_id == user_id)
                .order_by(BankAccount.created_at.desc())
                .limit(1)
            )
            
            new_default = result.scalars().first()
            
            if new_default:
                new_default.is_default = True
                db.add(new_default)
        
        await db.commit()
        return True
    
    async def get_payout_history(
        self,
        db: AsyncSession,
        user_id: str,
        status: Optional[PayoutStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Get payout history for a user
        """
        query = select(Payout).where(Payout.reader_id == user_id)
        
        # Apply filters
        if status:
            query = query.where(Payout.status == status)
            
        if start_date:
            query = query.where(Payout.created_at >= start_date)
            
        if end_date:
            query = query.where(Payout.created_at <= end_date)
        
        # Count total items for pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_items = (await db.execute(count_query)).scalar()
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Payout.created_at.desc())
        query = query.offset(offset).limit(page_size)
        
        # Execute query
        result = await db.execute(
            query.options(
                selectinload(Payout.payout_method)
            )
        )
        
        payouts = result.scalars().all()
        
        # Calculate pagination info
        total_pages = (total_items + page_size - 1) // page_size
        
        return {
            "items": [PayoutResponse.from_orm(payout) for payout in payouts],
            "total": total_items,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1
        }
    
    async def get_payout_estimate(
        self,
        db: AsyncSession,
        user_id: str,
        amount: Optional[Decimal] = None
    ) -> PayoutEstimateResponse:
        """
        Get an estimate for a payout
        """
        # Get available balance
        earnings = await self.calculate_earnings(db, user_id)
        available_balance = Decimal(str(earnings["available_for_payout"]))
        
        # If no amount specified, use available balance
        if amount is None:
            amount = available_balance
        
        # Validate amount
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")
            
        if amount > available_balance:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Available: {available_balance}"
            )
        
        # Get default payout method
        result = await db.execute(
            select(BankAccount)
            .where(and_(
                BankAccount.user_id == user_id,
                BankAccount.is_default == True
            ))
        )
        
        default_method = result.scalars().first()
        
        # Calculate fees
        # In a real app, this would depend on the payout method and other factors
        fee_percent = Decimal('1.0')  # 1% fee
        fee_amount = (amount * fee_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Minimum fee
        if fee_amount < Decimal('0.25'):
            fee_amount = Decimal('0.25')
        
        # Maximum fee
        if fee_amount > Decimal('10.00'):
            fee_amount = Decimal('10.00')
        
        net_amount = (amount - fee_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        return PayoutEstimateResponse(
            amount_requested=float(amount),
            fee_percent=float(fee_percent),
            fee_amount=float(fee_amount),
            net_amount=float(net_amount),
            currency="USD",
            estimated_arrival=(
                datetime.utcnow() + timedelta(days=2)  # 2 business days
            ).isoformat(),
            payout_method={
                "id": default_method.id if default_method else None,
                "type": PayoutMethodType.BANK_ACCOUNT if default_method else None,
                "last4": default_method.last4 if default_method else None,
                "bank_name": default_method.bank_name if default_method else None
            } if default_method else None
        )

# Create a global instance of the payout service
payout_service = PayoutService()
