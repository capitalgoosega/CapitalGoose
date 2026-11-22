from fastapi import APIRouter, Depends
from app.api import (
    intake, package, applications, webhooks, vault, bank_portal,
    admin_lenders, admin_bank_users, admin_eligibility, admin_access_grants,
    admin_partners, admin_referrals, partner_v1,
)
from app.api.admin_auth import require_admin

router = APIRouter()

# Internal-only routers: require the X-Admin-Key header
router.include_router(intake.router, prefix="/intake", dependencies=[Depends(require_admin)])
router.include_router(package.router, prefix="/package", dependencies=[Depends(require_admin)])
router.include_router(applications.router, prefix="/applications", dependencies=[Depends(require_admin)])
router.include_router(admin_lenders.router, prefix="/admin/lenders", dependencies=[Depends(require_admin)])
router.include_router(admin_bank_users.router, prefix="/admin/bank-users", dependencies=[Depends(require_admin)])
router.include_router(admin_eligibility.router, prefix="/admin/eligibility", dependencies=[Depends(require_admin)])
router.include_router(admin_access_grants.router, prefix="/admin/access-grants", dependencies=[Depends(require_admin)])
router.include_router(admin_partners.router, prefix="/admin/partners", dependencies=[Depends(require_admin)])
router.include_router(admin_referrals.router, prefix="/admin/referrals", dependencies=[Depends(require_admin)])

# Called by Zapier (has its own protection) and by banks (login required)
router.include_router(webhooks.router, prefix="/webhooks")
router.include_router(vault.router, prefix="/vault")
router.include_router(bank_portal.router, prefix="/bank-portal")

# Headless partner API: authenticated by the partner's own X-API-Key
router.include_router(partner_v1.router, prefix="/v1")
