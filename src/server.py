"""Auto Investor MCP server protected by Auth0, with OBO calls to BE API."""

from __future__ import annotations

import json
import logging

import httpx
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from auth0_token_verifier import Auth0TokenVerifier, build_api_client
from config import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = get_config()
api_client = build_api_client(
    domain=config.auth0_domain,
    audience=config.auth0_audience,
    client_id=config.auth0_client_id,
    client_secret=config.auth0_client_secret,
)
token_verifier = Auth0TokenVerifier(api_client, config.auth0_audience)

mcp = MCPServer(
    "Auto Investor MCP",
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(config.issuer_url),
        resource_server_url=AnyHttpUrl(config.mcp_server_url),
        required_scopes=None,
        # Auth0 ApiClient already validates audience.
        validate_token_resource=False,
    ),
    token_verifier=token_verifier,
)


def _require_access_token():
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("Missing authenticated access token")
    return access_token


async def _exchange_for_be_token(access_token: str) -> str:
    result = await api_client.get_token_on_behalf_of(
        access_token=access_token,
        audience=config.downstream_api_audience,
        scope=config.exchange_scope or None,
    )
    return result["access_token"]


async def _be_get(path: str) -> str:
    access_token = _require_access_token()
    be_token = await _exchange_for_be_token(access_token.token)

    base = config.api_base_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    url = f"{base}{suffix}"

    logger.info("Calling BE API via OBO: %s", url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {be_token}"})

    try:
        body: object = response.json()
    except Exception:
        body = response.text

    return json.dumps(
        {
            "url": url,
            "status_code": response.status_code,
            "body": body,
        },
        indent=2,
    )


@mcp.tool()
async def whoami() -> str:
    """Return claims for the authenticated MCP user."""
    access_token = _require_access_token()
    return json.dumps(
        {
            "subject": access_token.subject,
            "client_id": access_token.client_id,
            "scopes": access_token.scopes,
            "claims": access_token.claims or {},
        },
        indent=2,
    )


@mcp.tool()
async def get_user() -> str:
    """Fetch the current user from the Auto Investor BE API (`/api/v1/user/`)."""
    return await _be_get("/user/")


@mcp.tool()
async def get_user_accounts() -> str:
    """Fetch the current user's accounts from the Auto Investor BE API (`/api/v1/users/accounts/`)."""
    return await _be_get("/users/accounts/")


# @mcp.tool()
# async def be_get(path: str = "/") -> str:
#     """Call the Auto Investor BE API on the user's behalf (On-Behalf-Of).

#     path: path under the API base (e.g. '/' or '/health'). Uses AUTO_INVESTOR_URL
#     when set, otherwise DOWNSTREAM_API_URL/api/v1.
#     """
#     return await _be_get(path)


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=config.host,
        port=config.port,
    )
