from fastapi import APIRouter
from app.api import intake, package, applications, webhooks

router = APIRouter()
router.include_router(intake.router, prefix="/intake")
router.include_router(package.router, prefix="/package")
router.include_router(applications.router, prefix="/applications")
router.include_router(webhooks.router, prefix="/webhooks")