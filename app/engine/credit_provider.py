"""
Credit data behind one interface, so the bureau can be chosen (CRS, Array...)
after the Week 0 decision without touching the rest of the engine.

Only the simulated provider exists today. It returns RANDOM scores, so the
referral service refuses to use it for "live" partners.
"""
import os
from dataclasses import dataclass, field


class ProviderNotConfigured(Exception):
    pass


@dataclass
class PullRequest:
    """Held in memory for the pull only; DOB and address are not stored by us."""
    first_name: str
    last_name: str
    dob: str
    address: dict = field(default_factory=dict)
    credit_band: str = None     # only used by the self-reported provider


class CreditProvider:
    name = "base"
    simulated = False

    def pull(self, db, application_id: int, request: PullRequest):
        """Must store and return a SoftPullResult (with source=self.name)."""
        raise NotImplementedError


class SimulatedProvider(CreditProvider):
    name = "simulated"
    simulated = True

    def pull(self, db, application_id, request):
        from app.services.credit_service import simulate_soft_pull
        return simulate_soft_pull(db, application_id)


class SelfReportedProvider(CreditProvider):
    """
    No bureau pull. The applicant states a credit range, which we map to its
    lower bound. Stored with source "self_reported" so it is never confused
    with a bureau score. Off unless CREDIT_PROVIDER=self_reported.
    """
    name = "self_reported"
    simulated = False

    def pull(self, db, application_id, request):
        from app.engine.credit_bands import band_to_score
        from app.models.soft_pull_result import SoftPullResult
        score = band_to_score(request.credit_band)
        if score is None:
            raise ValueError("credit_band is required: one of below_580, 580_649, 650_679, 680_719, 720_plus")
        result = SoftPullResult(application_id=application_id, credit_score=score, source="self_reported")
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


# Real providers get registered here once chosen and contracted.
_PROVIDERS = {"simulated": SimulatedProvider, "self_reported": SelfReportedProvider}
_PLANNED = {"crs", "array", "isoftpull", "microbilt"}


def get_provider() -> CreditProvider:
    name = os.environ.get("CREDIT_PROVIDER", "simulated").strip().lower()
    if name in _PROVIDERS:
        return _PROVIDERS[name]()
    if name in _PLANNED:
        raise ProviderNotConfigured(f"Credit provider '{name}' is planned but not implemented yet")
    raise ProviderNotConfigured(f"Unknown CREDIT_PROVIDER '{name}'")


def uses_self_reported() -> bool:
    return os.environ.get("CREDIT_PROVIDER", "simulated").strip().lower() == "self_reported"
