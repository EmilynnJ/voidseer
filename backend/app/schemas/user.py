from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

class UserRole(str, Enum):
    CLIENT = "client"
    READER = "reader"
    ADMIN = "admin"
    MODERATOR = "moderator"

class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending_verification"

# Shared properties
class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image: Optional[str] = None
    bio: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = True
    is_verified: Optional[bool] = False
    role: UserRole = UserRole.CLIENT
    status: UserStatus = UserStatus.ACTIVE

# Properties to receive via API on creation
class UserCreate(UserBase):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: str
    last_name: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

# Properties to receive via API on update
class UserUpdate(UserBase):
    password: Optional[str] = None
    current_password: Optional[str] = None

    @validator('password')
    def check_password_strength(cls, v, values):
        if v is not None:
            if len(v) < 8:
                raise ValueError('Password must be at least 8 characters')
            if not any(c.isupper() for c in v):
                raise ValueError('Password must contain at least one uppercase letter')
            if not any(c.islower() for c in v):
                raise ValueError('Password must contain at least one lowercase letter')
            if not any(c.isdigit() for c in v):
                raise ValueError('Password must contain at least one number')
        return v

class UserInDBBase(UserBase):
    id: UUID
    clerk_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        json_encoders = {
            UUID: lambda v: str(v),
        }

# Additional properties to return via API
class UserResponse(UserInDBBase):
    pass

# Additional properties stored in DB
class UserInDB(UserInDBBase):
    hashed_password: str

# Reader Profile Schemas
class ReaderProfileBase(BaseModel):
    display_name: str
    headline: Optional[str] = None
    bio: Optional[str] = None
    languages: List[str] = []
    specialties: List[str] = []
    timezone: str = "UTC"
    is_online: bool = False
    is_available: bool = False
    rate_per_minute: float = 2.0
    minimum_session_minutes: int = 5
    website_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_handle: Optional[str] = None
    tiktok_handle: Optional[str] = None

class ReaderProfileCreate(ReaderProfileBase):
    pass

class ReaderProfileUpdate(ReaderProfileBase):
    pass

class ReaderProfileResponse(ReaderProfileBase):
    id: UUID
    user_id: UUID
    is_verified: bool = False
    verification_status: str = "pending"
    total_sessions: int = 0
    total_minutes: int = 0
    average_rating: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        json_encoders = {
            UUID: lambda v: str(v),
        }

# Client Profile Schemas
class ClientProfileBase(BaseModel):
    preferred_languages: List[str] = []
    notification_preferences: Dict[str, bool] = {
        "email": True,
        "push": True,
        "sms": False,
        "marketing_emails": True
    }

class ClientProfileCreate(ClientProfileBase):
    pass

class ClientProfileUpdate(ClientProfileBase):
    pass

class ClientProfileResponse(ClientProfileBase):
    id: UUID
    user_id: UUID
    total_sessions: int = 0
    total_spent: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        json_encoders = {
            UUID: lambda v: str(v),
        }

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None

# Email schemas
class EmailSchema(BaseModel):
    email: List[EmailStr]
    subject: str
    body: str

class EmailVerificationRequest(BaseModel):
    email: EmailStr

class EmailVerificationResponse(BaseModel):
    message: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetResponse(BaseModel):
    message: str

class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str

# User search and filter schemas
class UserFilter(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None

class UserSortBy(str, Enum):
    CREATED_AT_ASC = "created_at_asc"
    CREATED_AT_DESC = "created_at_desc"
    EMAIL_ASC = "email_asc"
    EMAIL_DESC = "email_desc"
    LAST_LOGIN_ASC = "last_login_asc"
    LAST_LOGIN_DESC = "last_login_desc"

class UserPagination(BaseModel):
    page: int = 1
    per_page: int = 20
    sort_by: UserSortBy = UserSortBy.CREATED_AT_DESC

# Response models for user lists
class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int
    page: int
    per_page: int
    total_pages: int

    class Config:
        json_encoders = {
            UUID: lambda v: str(v),
        }
