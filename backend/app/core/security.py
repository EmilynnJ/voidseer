from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union, Dict, List, Tuple

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jose import JWTError, jwt
from jose.exceptions import JWTClaimsError, ExpiredSignatureError
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.token import TokenPayload

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    scopes={
        "user": "Read information about the current user",
        "reader": "Access to reader functionality",
        "admin": "Admin access",
    }
)

def create_access_token(
    subject: Union[str, Any], 
    expires_delta: timedelta = None,
    scopes: List[str] = None,
    user_claims: Dict[str, Any] = None
) -> str:
    """
    Create a JWT access token with the given subject (usually user ID)
    and optional additional claims.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "scopes": scopes or [],
        "iat": datetime.now(timezone.utc),
        "type": "access"
    }
    
    # Add custom claims if provided
    if user_claims:
        to_encode.update(user_claims)
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=ALGORITHM
    )
    return encoded_jwt

def create_refresh_token(
    subject: Union[str, Any],
    expires_delta: timedelta = None
) -> str:
    """Create a refresh token with a longer expiration time."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.REFRESH_SECRET_KEY,
        algorithm=ALGORITHM
    )
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return pwd_context.hash(password)

async def get_current_user(
    security_scopes: SecurityScopes,
    request: Request = None,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current user from the JWT token.
    Validates the token and checks required scopes.
    """
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope=\"{security_scopes.scope_str}\"'
    else:
        authenticate_value = "Bearer"
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    
    try:
        # Verify token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_aud": False}
        )
        
        # Validate token type
        if payload.get("type") != "access":
            raise credentials_exception
            
        # Get user ID from token
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        # Get token scopes
        token_scopes = payload.get("scopes", [])
        token_data = TokenPayload(scopes=token_scopes, sub=user_id)
        
    except (JWTError, ValidationError):
        raise credentials_exception
    
    # Check scopes
    if security_scopes.scopes:
        for scope in security_scopes.scopes:
            if scope not in token_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions",
                    headers={"WWW-Authenticate": authenticate_value},
                )
    
    # Get user from database
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise credentials_exception
        
    # Check if user is active
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    # Update last login time
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    
    return user

# Dependency to get current active user
async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency to check if the current user is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# Dependency to check if user has a specific role
def has_role(required_role: UserRole):
    """Check if the current user has the required role."""
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role",
            )
        return current_user
    return role_checker

# Dependency to check if user has any of the required roles
def has_any_role(required_roles: List[UserRole]):
    """Check if the current user has any of the required roles."""
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of these roles: {', '.join(required_roles)}",
            )
        return current_user
    return role_checker

# Dependency to check if user is the owner of a resource or has admin role
def is_owner_or_admin(resource_owner_id: str):
    """Check if the current user is the owner of the resource or an admin."""
    def checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if str(current_user.id) != resource_owner_id and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to access this resource",
            )
        return current_user
    return checker

def verify_token(token: str) -> Optional[TokenPayload]:
    """Verify JWT token and return payload if valid"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_aud": False}
        )
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        
        if datetime.fromtimestamp(token_data.exp) < datetime.utcnow():
            return None
            
        return token_data
    except (jwt.JWTError, ValidationError):
        return None

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current active user from token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
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
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Check if current user is active"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_authorization_scheme_param(authorization_header_value: Optional[str]) -> Tuple[str, str]:
    """Parse authorization header"""
    if not authorization_header_value:
        return "", ""
    
    scheme, _, param = authorization_header_value.partition(" ")
    return scheme, param

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)
