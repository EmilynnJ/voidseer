from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, has_any_role
from app.models.user import User, UserRole, UserStatus, ReaderProfile
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    UserCreate,
    UserRegister,
    ReaderProfileCreate,
    ReaderProfileUpdate,
    ReaderProfileResponse,
)
from app.schemas.common import Message, ListResponse

router = APIRouter()

# Admin-only endpoints
@router.get("/", response_model=ListResponse[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    search: Optional[str] = None,
    current_user: User = Depends(has_any_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    List users with optional filtering.
    """
    query = select(User)
    
    # Apply filters
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if search:
        search = f"%{search}%"
        query = query.where(
            or_(
                User.email.ilike(search),
                User.username.ilike(search),
                User.first_name.ilike(search),
                User.last_name.ilike(search),
            )
        )
    
    # Get total count
    total = await db.scalar(select([query.subquery().count()]))
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {
        "data": users,
        "total": total,
        "skip": skip,
        "limit": limit,
    }

@router.post("/", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    current_user: User = Depends(has_any_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user (admin only).
    """
    # Check if user with this email already exists
    existing_user = await db.execute(
        select(User).where(
            or_(
                User.email == user_in.email,
                User.username == user_in.username,
            )
        )
    )
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or username already exists",
        )
    
    # Create user
    user = User(
        email=user_in.email,
        username=user_in.username,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        role=user_in.role,
        status=user_in.status or UserStatus.ACTIVE,
        is_active=user_in.is_active if user_in.is_active is not None else True,
    )
    
    # Set password if provided
    if user_in.password:
        user.set_password(user_in.password)
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user

# User profile endpoints
@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current user.
    """
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_user_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user.
    """
    update_data = user_in.dict(exclude_unset=True)
    
    # Handle password update
    if "password" in update_data:
        hashed_password = get_password_hash(update_data["password"])
        del update_data["password"]
        update_data["hashed_password"] = hashed_password
    
    # Update user fields
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.now(timezone.utc)
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return current_user

# Reader profile endpoints
@router.get("/me/reader-profile", response_model=ReaderProfileResponse)
async def read_my_reader_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's reader profile.
    """
    if current_user.role != UserRole.READER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only readers have a reader profile",
        )
    
    if not current_user.reader_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reader profile not found",
        )
    
    return current_user.reader_profile

@router.post("/me/reader-profile", response_model=ReaderProfileResponse)
async def create_my_reader_profile(
    profile_in: ReaderProfileCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update current user's reader profile.
    """
    if current_user.role != UserRole.READER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only readers can have a reader profile",
        )
    
    # Check if profile already exists
    if current_user.reader_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reader profile already exists",
        )
    
    # Create reader profile
    profile_data = profile_in.dict(exclude_unset=True)
    profile = ReaderProfile(
        user_id=current_user.id,
        **profile_data,
    )
    
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    return profile

@router.put("/me/reader-profile", response_model=ReaderProfileResponse)
async def update_my_reader_profile(
    profile_in: ReaderProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user's reader profile.
    """
    if current_user.role != UserRole.READER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only readers can have a reader profile",
        )
    
    if not current_user.reader_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reader profile not found",
        )
    
    # Update profile fields
    profile_data = profile_in.dict(exclude_unset=True)
    for field, value in profile_data.items():
        setattr(current_user.reader_profile, field, value)
    
    current_user.reader_profile.updated_at = datetime.now(timezone.utc)
    
    db.add(current_user.reader_profile)
    await db.commit()
    await db.refresh(current_user.reader_profile)
    
    return current_user.reader_profile

# Public endpoints
@router.get("/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific user by ID.
    """
    # Users can only view their own profile unless they're an admin
    if str(current_user.id) != str(user_id) and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a user.
    """
    # Only admins can update other users
    if str(current_user.id) != str(user_id) and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Only admins can change roles or status
    if current_user.role != UserRole.ADMIN:
        if "role" in user_in.dict(exclude_unset=True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to change user role",
            )
        if "status" in user_in.dict(exclude_unset=True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to change user status",
            )
    
    # Update user fields
    update_data = user_in.dict(exclude_unset=True)
    
    # Handle password update
    if "password" in update_data:
        hashed_password = get_password_hash(update_data["password"])
        del update_data["password"]
        update_data["hashed_password"] = hashed_password
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    user.updated_at = datetime.now(timezone.utc)
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user

@router.delete("/{user_id}", response_model=Message)
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(has_any_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a user (admin only).
    """
    # Prevent deleting yourself
    if str(current_user.id) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Soft delete
    user.is_active = False
    user.status = UserStatus.DELETED
    user.email = f"deleted_{user.id}@deleted.com"
    user.username = f"deleted_{user.id}"
    user.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {"message": "User deleted successfully"}
