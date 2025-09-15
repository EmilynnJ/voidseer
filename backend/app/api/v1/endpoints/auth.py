from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.encoders import jsonable_encoder
from jose import jwt
from pydantic import ValidationError, EmailStr
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db, get_db_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    get_current_user,
    get_current_active_user,
    oauth2_scheme,
)
from app.models.user import User, UserRole, UserStatus, SecurityToken, TokenType
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserInDB,
    Token,
    TokenPayload,
    Msg,
    ResetPasswordRequest,
    NewPassword,
    UserRegister,
)
from app.schemas.token import Token as TokenSchema
from app.services.email_service import send_new_account_email, send_reset_password_email

router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Dict[str, str]:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Find user by email or username
    stmt = select(User).where(
        or_(
            User.email == form_data.username,
            User.username == form_data.username,
        )
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Check if user exists and password is correct
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    
    # Generate access and refresh tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Determine user scopes based on role
    scopes = ["user"]
    if user.role == UserRole.READER:
        scopes.append("reader")
    if user.role == UserRole.ADMIN:
        scopes.append("admin")
    
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=access_token_expires,
        scopes=scopes,
        user_claims={"role": user.role},
    )
    
    refresh_token = create_refresh_token(
        subject=str(user.id),
        expires_delta=refresh_token_expires,
    )
    
    # Update last login time
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "expires_in": int(access_token_expires.total_seconds()),
    }

@router.post("/login/test-token", response_model=UserResponse)
async def test_token(current_user: User = Depends(get_current_user)):
    """Test access token"""
    return current_user

@router.post("/password-recovery/{email}", response_model=Msg)
async def recover_password(email: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Password Recovery
    """
    user = await db.execute(select(User).where(User.email == email))
    user = user.scalar_one_or_none()
    
    if not user:
        return {"msg": "If this email is registered, you will receive a password reset link"}
    
    # Generate password reset token
    password_reset_token = SecurityToken.create_password_reset_token(
        user_id=user.id,
        expires_in_minutes=settings.EMAIL_RESET_TOKEN_EXPIRE_MINUTES
    )
    
    db.add(password_reset_token)
    await db.commit()
    
    # Send email with password reset link
    background_tasks.add_task(
        send_reset_password_email,
        email_to=user.email,
        email=email,
        token=password_reset_token.token,
    )
    
    return {"msg": "Password recovery email sent"}

@router.post("/reset-password/", response_model=Msg)
async def reset_password(
    token_data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reset password
    """
    # Find the token
    stmt = select(SecurityToken).where(
        SecurityToken.token == token_data.token,
        SecurityToken.token_type == TokenType.PASSWORD_RESET,
        SecurityToken.is_used == False,
        SecurityToken.expires_at > datetime.now(timezone.utc)
    )
    
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    
    # Get user
    user = await db.get(User, token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Update password
    hashed_password = get_password_hash(token_data.new_password)
    user.hashed_password = hashed_password
    user.updated_at = datetime.now(timezone.utc)
    
    # Mark token as used
    token.is_used = True
    token.used_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {"msg": "Password updated successfully"}

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_in: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create new user without the need to be logged in.
    """
    # Check if user with this email already exists
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    
    # Check if username is taken
    if user_in.username:
        stmt = select(User).where(User.username == user_in.username)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The username is already taken.",
            )
    
    # Create user
    hashed_password = get_password_hash(user_in.password)
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hashed_password,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        is_active=True,
        role=UserRole.CLIENT,
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Send welcome email
    background_tasks.add_task(
        send_new_account_email,
        email_to=user.email,
        username=user.username or user.email,
    )
    
    return user

@router.post("/refresh-token", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using a refresh token
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.REFRESH_SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
        )
        
        token_data = TokenPayload(**payload)
        
        # Verify token type
        if token_data.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        
        # Get user
        user = await db.get(User, uuid.UUID(token_data.sub))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        
        # Generate new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Determine scopes based on user role
        scopes = ["user"]
        if user.role == UserRole.READER:
            scopes.append("reader")
        if user.role == UserRole.ADMIN:
            scopes.append("admin")
        
        access_token = create_access_token(
            subject=str(user.id),
            expires_delta=access_token_expires,
            scopes=scopes,
            user_claims={"role": user.role},
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": int(access_token_expires.total_seconds()),
        }
        
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        clerk_user = response.json()
        
    # Get or create user in our database
    result = await db.execute(
        select(User).where(User.clerk_id == clerk_user["id"])
    )
    user = result.scalars().first()
    
    if not user:
        # Create new user
        user_data = {
            "clerk_id": clerk_user["id"],
            "email": clerk_user["email"],
            "first_name": clerk_user.get("first_name", ""),
            "last_name": clerk_user.get("last_name", ""),
            "is_active": True,
            "is_verified": clerk_user.get("email_verified", False),
            "role": "client"  # Default role
        }
        
        user = User(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Send welcome email
        await email_service.send_welcome_email(
            email=user.email,
            name=f"{user.first_name} {user.last_name}".strip() or "there"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.clerk_id}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/register", response_model=UserResponse)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (handled by Clerk, this is a fallback)"""
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    
    # Create user in Clerk
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.clerk.dev/v1/users",
            json={
                "email_address": [user_in.email],
                "password": user_in.password,
                "first_name": user_in.first_name,
                "last_name": user_in.last_name,
            },
            headers={
                "Authorization": f"Bearer {settings.CLERK_SECRET_KEY}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error creating user in authentication service",
            )
        
        clerk_user = response.json()
    
    # Create user in our database
    user_data = {
        "clerk_id": clerk_user["id"],
        "email": user_in.email,
        "first_name": user_in.first_name,
        "last_name": user_in.last_name,
        "is_active": True,
        "is_verified": False,
        "role": "client"
    }
    
    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Send verification email
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={clerk_user['id']}"
    await email_service.send_verification_email(
        email=user.email,
        name=f"{user.first_name} {user.last_name}".strip() or "there",
        verification_url=verification_url
    )
    
    return user

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user"""
    return current_user

@router.post("/refresh-token", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[security.ALGORITHM],
            options={"verify_aud": False},
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise credentials_exception
    
    result = await db.execute(
        select(User).where(User.clerk_id == token_data.sub)
    )
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.clerk_id}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }
