import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from decimal import Decimal
import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from app.core.config import settings
from app.models import ReadingSession, User, Transaction, PaymentMethod, Subscription
from app.schemas.payment import (
    PaymentIntentCreate,
    PaymentIntentResponse,
    PaymentMethodCreate,
    PaymentMethodResponse,
    SubscriptionCreate,
    SubscriptionResponse,
    InvoiceResponse,
    PayoutResponse
)

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

class BillingService:
    def __init__(self):
        self.active_sessions: Dict[str, asyncio.Task] = {}
        self.billing_interval = 60  # Bill every 60 seconds
        
    async def start_monitoring(self):
        """Start monitoring active reading sessions for billing"""
        logger.info("Starting billing service...")
        while True:
            try:
                await self._process_active_sessions()
                await asyncio.sleep(self.billing_interval)
            except Exception as e:
                logger.error(f"Error in billing service: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _process_active_sessions(self):
        """Process all active reading sessions for billing"""
        async with get_db() as db:
            # Get all active reading sessions
            result = await db.execute(
                select(ReadingSession).where(
                    and_(
                        ReadingSession.status == "active",
                        ReadingSession.end_time.is_(None)
                    )
                )
            )
            sessions = result.scalars().all()
            
            for session in sessions:
                if session.id not in self.active_sessions:
                    # Start billing task for new session
                    self.active_sessions[session.id] = asyncio.create_task(
                        self._bill_session(session.id)
                    )
    
    async def _bill_session(self, session_id: str):
        """Bill a reading session at regular intervals"""
        try:
            async with get_db() as db:
                # Get session with reader and client
                result = await db.execute(
                    select(ReadingSession)
                    .options(selectinload(ReadingSession.reader), selectinload(ReadingSession.client))
                    .where(ReadingSession.id == session_id)
                )
                session = result.scalars().first()
                
                if not session or session.status != "active":
                    logger.warning(f"Session {session_id} not found or not active")
                    return
                
                reader = session.reader
                client = session.client
                
                if not reader or not client:
                    logger.error(f"Invalid session {session_id}: missing reader or client")
                    return
                
                logger.info(f"Starting billing for session {session_id} (Reader: {reader.id}, Client: {client.id})")
                
                while True:
                    # Check if session is still active
                    result = await db.execute(
                        select(ReadingSession.status)
                        .where(ReadingSession.id == session_id)
                    )
                    current_status = result.scalar_one_or_none()
                    
                    if current_status != "active":
                        logger.info(f"Session {session_id} no longer active. Stopping billing.")
                        break
                    
                    # Calculate time since last bill
                    now = datetime.utcnow()
                    last_bill = session.last_bill_time or session.start_time
                    seconds_since_bill = (now - last_bill).total_seconds()
                    
                    if seconds_since_bill >= self.billing_interval:
                        # Calculate amount to bill (in smallest currency unit, e.g., cents)
                        minutes = Decimal(seconds_since_bill) / 60
                        amount = (reader.rate_per_minute * minutes).quantize(Decimal('0.01'))
                        
                        # Process payment
                        payment_success = await self._process_payment(
                            db=db,
                            client_id=client.id,
                            reader_id=reader.id,
                            amount=amount,
                            description=f"Reading session {session_id} - {minutes:.2f} minutes"
                        )
                        
                        if payment_success:
                            # Update session with new bill time and amount
                            session.last_bill_time = now
                            session.total_billed += amount
                            session.total_minutes += minutes
                            
                            # Update reader's stats
                            reader.total_minutes += minutes
                            reader.total_earnings += amount
                            
                            # Update client's stats
                            client.total_minutes += minutes
                            client.total_spent += amount
                            
                            # Create transaction record
                            transaction = Transaction(
                                user_id=client.id,
                                amount=amount,
                                currency="usd",
                                status="completed",
                                type="reading_session",
                                reference_id=session_id,
                                description=f"Reading session with {reader.display_name}",
                                metadata={
                                    "reader_id": str(reader.id),
                                    "reader_name": reader.display_name,
                                    "minutes_billed": float(minutes),
                                    "rate_per_minute": float(reader.rate_per_minute)
                                }
                            )
                            db.add(transaction)
                            
                            await db.commit()
                            logger.info(f"Billed {amount} for session {session_id} ({minutes:.2f} minutes)")
                        else:
                            # Payment failed, end session
                            logger.warning(f"Payment failed for session {session_id}. Ending session.")
                            session.status = "payment_failed"
                            session.end_time = now
                            await db.commit()
                            break
                    
                    # Wait for next billing cycle
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in billing task for session {session_id}: {str(e)}", exc_info=True)
        finally:
            # Clean up
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
    
    async def _process_payment(
        self,
        db: AsyncSession,
        client_id: str,
        reader_id: str,
        amount: Decimal,
        description: str
    ) -> bool:
        """Process a payment from client to reader"""
        try:
            # Get client's default payment method
            result = await db.execute(
                select(PaymentMethod)
                .where(and_(
                    PaymentMethod.user_id == client_id,
                    PaymentMethod.is_default == True
                ))
            )
            payment_method = result.scalars().first()
            
            if not payment_method:
                logger.error(f"No default payment method found for user {client_id}")
                return False
            
            # Get reader's Stripe account ID
            result = await db.execute(
                select(User.stripe_account_id)
                .where(User.id == reader_id)
            )
            reader_stripe_account = result.scalar_one_or_none()
            
            if not reader_stripe_account:
                logger.error(f"No Stripe account found for reader {reader_id}")
                return False
            
            # Convert amount to cents for Stripe
            amount_cents = int(amount * 100)
            
            # Create a payment intent with direct charges
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency='usd',
                customer=payment_method.stripe_customer_id,
                payment_method=payment_method.stripe_payment_method_id,
                off_session=True,
                confirm=True,
                description=description,
                transfer_data={
                    'destination': reader_stripe_account,
                    'amount': int(amount_cents * 0.85)  # 15% platform fee
                },
                metadata={
                    'client_id': str(client_id),
                    'reader_id': str(reader_id),
                    'type': 'reading_session'
                }
            )
            
            if payment_intent.status == 'succeeded':
                return True
            else:
                logger.error(f"Payment failed: {payment_intent.last_payment_error or 'Unknown error'}")
                return False
                
        except stripe.error.CardError as e:
            logger.error(f"Card error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}", exc_info=True)
            return False
    
    # Payment Methods
    async def create_payment_method(
        self,
        db: AsyncSession,
        user_id: str,
        payment_method_data: PaymentMethodCreate
    ) -> PaymentMethodResponse:
        """Add a new payment method for a user"""
        try:
            # Check if user exists
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Create Stripe customer if not exists
            if not user.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    name=f"{user.first_name} {user.last_name}".strip(),
                    metadata={"user_id": str(user.id)}
                )
                user.stripe_customer_id = customer.id
                await db.commit()
            
            # Attach payment method to customer
            payment_method = stripe.PaymentMethod.attach(
                payment_method_data.stripe_payment_method_id,
                customer=user.stripe_customer_id
            )
            
            # Set as default if specified or if it's the first payment method
            result = await db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.user_id == user_id)
            )
            existing_methods = result.scalars().all()
            
            is_default = payment_method_data.is_default or not existing_methods
            
            # If setting as default, unset any existing default
            if is_default:
                await db.execute(
                    update(PaymentMethod)
                    .where(PaymentMethod.user_id == user_id)
                    .values(is_default=False)
                )
            
            # Save payment method to database
            db_payment_method = PaymentMethod(
                user_id=user.id,
                stripe_payment_method_id=payment_method.id,
                card_brand=payment_method.card.brand,
                card_last4=payment_method.card.last4,
                card_exp_month=payment_method.card.exp_month,
                card_exp_year=payment_method.card.exp_year,
                is_default=is_default,
                metadata=payment_method_data.metadata or {}
            )
            db.add(db_payment_method)
            await db.commit()
            await db.refresh(db_payment_method)
            
            return PaymentMethodResponse.from_orm(db_payment_method)
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Payment method could not be added: {str(e)}"
            )
    
    async def get_payment_methods(
        self,
        db: AsyncSession,
        user_id: str
    ) -> List[PaymentMethodResponse]:
        """Get all payment methods for a user"""
        result = await db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user_id)
            .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
        methods = result.scalars().all()
        return [PaymentMethodResponse.from_orm(m) for m in methods]
    
    async def delete_payment_method(
        self,
        db: AsyncSession,
        user_id: str,
        payment_method_id: str
    ) -> bool:
        """Delete a payment method"""
        # Get the payment method
        result = await db.execute(
            select(PaymentMethod)
            .where(and_(
                PaymentMethod.id == payment_method_id,
                PaymentMethod.user_id == user_id
            ))
        )
        payment_method = result.scalars().first()
        
        if not payment_method:
            raise HTTPException(status_code=404, detail="Payment method not found")
        
        if payment_method.is_default:
            # Find another payment method to make default
            result = await db.execute(
                select(PaymentMethod)
                .where(and_(
                    PaymentMethod.user_id == user_id,
                    PaymentMethod.id != payment_method_id
                ))
                .order_by(PaymentMethod.created_at.desc())
                .limit(1)
            )
            next_method = result.scalars().first()
            
            if next_method:
                next_method.is_default = True
        
        # Delete from Stripe
        try:
            stripe.PaymentMethod.detach(payment_method.stripe_payment_method_id)
        except stripe.error.StripeError as e:
            logger.error(f"Error detaching payment method from Stripe: {str(e)}")
        
        # Delete from database
        await db.delete(payment_method)
        await db.commit()
        
        return True
    
    # Subscriptions
    async def create_subscription(
        self,
        db: AsyncSession,
        user_id: str,
        subscription_data: SubscriptionCreate
    ) -> SubscriptionResponse:
        """Create a new subscription"""
        # Check if user exists and has a default payment method
        result = await db.execute(
            select(User, PaymentMethod)
            .outerjoin(PaymentMethod, and_(
                PaymentMethod.user_id == User.id,
                PaymentMethod.is_default == True
            ))
            .where(User.id == user_id)
        )
        user, payment_method = result.first() or (None, None)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not payment_method:
            raise HTTPException(
                status_code=400,
                detail="No default payment method found. Please add a payment method first."
            )
        
        # Check if user already has an active subscription
        result = await db.execute(
            select(Subscription)
            .where(and_(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "trialing", "past_due"])
            ))
        )
        existing_sub = result.scalars().first()
        
        if existing_sub:
            raise HTTPException(
                status_code=400,
                detail="User already has an active subscription"
            )
        
        # Create Stripe subscription
        try:
            subscription = stripe.Subscription.create(
                customer=user.stripe_customer_id,
                items=[{"price": subscription_data.price_id}],
                default_payment_method=payment_method.stripe_payment_method_id,
                trial_period_days=subscription_data.trial_days or None,
                metadata={
                    "user_id": str(user_id),
                    "plan_name": subscription_data.plan_name
                }
            )
            
            # Save subscription to database
            db_subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id=subscription.id,
                status=subscription.status,
                plan_name=subscription_data.plan_name,
                current_period_start=datetime.fromtimestamp(subscription.current_period_start),
                current_period_end=datetime.fromtimestamp(subscription.current_period_end),
                cancel_at_period_end=subscription.cancel_at_period_end,
                metadata=subscription.metadata or {}
            )
            db.add(db_subscription)
            await db.commit()
            await db.refresh(db_subscription)
            
            return SubscriptionResponse.from_orm(db_subscription)
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating subscription: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Subscription could not be created: {str(e)}"
            )
    
    async def cancel_subscription(
        self,
        db: AsyncSession,
        user_id: str,
        subscription_id: str
    ) -> bool:
        """Cancel a subscription"""
        # Get the subscription
        result = await db.execute(
            select(Subscription)
            .where(and_(
                Subscription.id == subscription_id,
                Subscription.user_id == user_id
            ))
        )
        subscription = result.scalars().first()
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        # Cancel in Stripe
        try:
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            
            # Update in database
            subscription.status = "canceled"
            subscription.canceled_at = datetime.utcnow()
            await db.commit()
            
            return True
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error canceling subscription: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Subscription could not be canceled: {str(e)}"
            )
    
    # Invoices and Payouts
    async def get_invoices(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 10,
        starting_after: Optional[str] = None
    ) -> List[InvoiceResponse]:
        """Get payment history for a user"""
        # Get user's Stripe customer ID
        result = await db.execute(
            select(User.stripe_customer_id)
            .where(User.id == user_id)
        )
        customer_id = result.scalar_one_or_none()
        
        if not customer_id:
            return []
        
        # Get invoices from Stripe
        try:
            invoices = stripe.Invoice.list(
                customer=customer_id,
                limit=limit,
                starting_after=starting_after
            )
            
            return [
                InvoiceResponse(
                    id=inv.id,
                    amount_due=inv.amount_due / 100,  # Convert from cents
                    amount_paid=inv.amount_paid / 100,
                    currency=inv.currency,
                    status=inv.status,
                    number=inv.number,
                    created=datetime.fromtimestamp(inv.created),
                    due_date=datetime.fromtimestamp(inv.due_date) if inv.due_date else None,
                    pdf_url=inv.invoice_pdf,
                    hosted_invoice_url=inv.hosted_invoice_url,
                    payment_intent=inv.payment_intent
                )
                for inv in invoices.data
            ]
            
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching invoices: {str(e)}")
            return []
    
    async def get_payouts(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 10,
        starting_after: Optional[str] = None
    ) -> List[PayoutResponse]:
        """Get payout history for a reader"""
        # Get user's Stripe account ID
        result = await db.execute(
            select(User.stripe_account_id)
            .where(User.id == user_id)
        )
        account_id = result.scalar_one_or_none()
        
        if not account_id:
            return []
        
        # Get payouts from Stripe
        try:
            payouts = stripe.Payout.list(
                destination=account_id,
                limit=limit,
                starting_after=starting_after
            )
            
            return [
                PayoutResponse(
                    id=payout.id,
                    amount=payout.amount / 100,  # Convert from cents
                    currency=payout.currency,
                    status=payout.status,
                    arrival_date=datetime.fromtimestamp(payout.arrival_date),
                    created=datetime.fromtimestamp(payout.created),
                    description=payout.description,
                    statement_descriptor=payout.statement_descriptor,
                    type=payout.type
                )
                for payout in payouts.data
            ]
            
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching payouts: {str(e)}")
            return []

# Create a global instance of the billing service
billing_service = BillingService()
