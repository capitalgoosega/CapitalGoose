from fastapi import APIRouter, Depends
from app.api import intake, package, applications, webhooks, vault, bank_portal
from app.api.admin_auth import require_admin

router = APIRouter()

# Internal-only routers: require the X-Admin-Key header
router.include_router(intake.router, prefix="/intake", dependencies=[Depends(require_admin)])
router.include_router(package.router, prefix="/package", dependencies=[Depends(require_admin)])
router.include_router(applications.router, prefix="/applications", dependencies=[Depends(require_admin)])

# Called by Zapier (has its own protection) and by banks (login required)
router.include_router(webhooks.router, prefix="/webhooks")
router.include_router(vault.router, prefix="/vault")
router.include_router(bank_portal.router, prefix="/bank-portal")
