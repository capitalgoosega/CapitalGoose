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


# Real providers get registered here once chosen and contracted.
_PROVIDERS = {"simulated": SimulatedProvider}
_PLANNED = {"crs", "array", "isoftpull", "microbilt"}


def get_provider() -> CreditProvider:
    name = os.environ.get("CREDIT_PROVIDER", "simulated").strip().lower()
    if name in _PROVIDERS:
        return _PROVIDERS[name]()
    if name in _PLANNED:
        raise ProviderNotConfigured(f"Credit provider '{name}' is planned but not implemented yet")
    raise ProviderNotConfigured(f"Unknown CREDIT_PROVIDER '{name}'")
