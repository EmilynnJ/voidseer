from fastapi import APIRouter
from .endpoints import (
    auth,
    readings,
    payments,
    marketplace,
    admin,
    community,
    messages,
    reviews,
    dashboard,
    help_center,
    applications,
    notifications
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(readings.router, prefix="/readings", tags=["Readings"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(marketplace.router, prefix="/marketplace", tags=["Marketplace"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(community.router, prefix="/community", tags=["Community"])
api_router.include_router(messages.router, prefix="/messages", tags=["Messages"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(help_center.router, prefix="/help", tags=["Help Center"])
api_router.include_router(applications.router, prefix="/applications", tags=["Applications"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
