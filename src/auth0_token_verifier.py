"""Auth0 access-token verification for the MCP resource server."""

from __future__ import annotations

import logging
from typing import Any

from auth0_api_python import ApiClient, ApiClientOptions
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


class Auth0TokenVerifier:
    """Validate bearer tokens issued by Auth0 for this MCP server."""

    def __init__(self, api_client: ApiClient, audience: str) -> None:
        self._api_client = api_client
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims: dict[str, Any] = await self._api_client.verify_access_token(access_token=token)
        except Exception:
            logger.exception("Auth0 access token verification failed")
            return None

        scope_claim = claims.get("scope", "")
        scopes = scope_claim.split() if isinstance(scope_claim, str) else list(claims.get("permissions") or [])
        permissions = claims.get("permissions") or []
        if isinstance(permissions, list):
            for permission in permissions:
                if permission not in scopes:
                    scopes.append(permission)

        client_id = str(claims.get("azp") or claims.get("client_id") or "")
        aud = claims.get("aud")
        if isinstance(aud, list):
            resource = next((item for item in aud if item == self._audience), aud[0] if aud else None)
        else:
            resource = aud

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=claims.get("exp"),
            resource=str(resource) if resource else self._audience,
            subject=claims.get("sub"),
            claims=claims,
        )


def build_api_client(
    *,
    domain: str,
    audience: str,
    client_id: str,
    client_secret: str,
) -> ApiClient:
    return ApiClient(
        ApiClientOptions(
            domain=domain,
            audience=audience,
            client_id=client_id,
            client_secret=client_secret,
        )
    )
