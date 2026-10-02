"""Caller identity from the Cognito JWT authorizer claims."""
from dataclasses import dataclass, field
from typing import List

from . import config
from .http import HttpError


@dataclass
class Caller:
    sub: str
    email: str
    practice_id: str
    groups: List[str] = field(default_factory=list)

    def has_any(self, *roles) -> bool:
        return any(r in self.groups for r in roles)

    @property
    def label(self) -> str:
        return self.email or self.sub


def _parse_groups(raw) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(g) for g in raw]
    text = str(raw).strip().strip("[]")
    return [g for g in text.replace(",", " ").split() if g]


def get_caller(event) -> Caller:
    claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
    sub = claims.get("sub") or "anonymous"
    return Caller(
        sub=sub,
        email=claims.get("email") or claims.get("cognito:username") or claims.get("username") or sub,
        practice_id=claims.get("custom:practiceId") or config.DEFAULT_PRACTICE_ID,
        groups=_parse_groups(claims.get("cognito:groups")),
    )


def require_role(caller: Caller, *roles):
    if not caller.has_any(*roles):
        raise HttpError(403, f"Requires one of roles: {', '.join(roles)}")
