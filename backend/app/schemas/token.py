from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field
from uuid import UUID

class TokenBase(BaseModel):
    """Base token schema"""
    token: str
    expires_at: datetime
    is_revoked: bool = False
    token_type: str
    
    class Config:
        orm_mode = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

class TokenCreate(TokenBase):
    """Schema for token creation"""
    user_id: UUID
    client_id: Optional[str] = None
    scopes: Optional[list] = []
    
class TokenUpdate(BaseModel):
    """Schema for token updates"""
    is_revoked: Optional[bool] = None
    expires_at: Optional[datetime] = None
    
class TokenInDB(TokenBase):
    """Schema for tokens in the database"""
    id: UUID
    user_id: UUID
    client_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    scopes: list = []
    
    class Config:
        orm_mode = True
        json_encoders = {
            UUID: lambda v: str(v),
            datetime: lambda v: v.isoformat(),
        }

class TokenResponse(TokenInDB):
    """Schema for token responses"""
    pass

class TokenPayload(BaseModel):
    """Schema for JWT token payload"""
    sub: Optional[str] = None  # Subject (usually user ID)
    exp: Optional[int] = None  # Expiration time (timestamp)
    iat: Optional[int] = None  # Issued at (timestamp)
    jti: Optional[str] = None  # JWT ID
    type: Optional[str] = None  # Token type (access, refresh, etc.)
    scopes: list = []  # List of scopes/permissions
    
    class Config:
        json_encoders = {
            'datetime': lambda v: v.isoformat(),
        }

class TokenPair(BaseModel):
    """Schema for access/refresh token pair"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until expiration
    
class TokenRevocationRequest(BaseModel):
    """Schema for token revocation requests"""
    token: str
    token_type_hint: Optional[str] = None
    
class TokenIntrospectionResponse(BaseModel):
    """Schema for token introspection responses (RFC 7662)"""
    active: bool
    scope: Optional[str] = None
    client_id: Optional[str] = None
    username: Optional[str] = None
    token_type: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    nbf: Optional[int] = None
    sub: Optional[str] = None
    aud: Optional[Any] = None
    iss: Optional[str] = None
    jti: Optional[str] = None
    
    class Config:
        json_encoders = {
            'datetime': lambda v: v.isoformat(),
        }

class OAuth2TokenRequestForm:
    """OAuth2 token request form"""
    def __init__(
        self,
        grant_type: str = None,
        username: str = None,
        password: str = None,
        scope: str = "",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        code: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self.grant_type = grant_type
        self.username = username
        self.password = password
        self.scopes = scope.split()
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.code = code
        self.redirect_uri = redirect_uri
