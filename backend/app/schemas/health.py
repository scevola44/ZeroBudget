from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    # Lets a client that only has a URL (the mobile app's server onboarding)
    # tell a ZeroBudget instance apart from any other server answering
    # /api/health.
    service: Literal["zerobudget"]
    version: str
