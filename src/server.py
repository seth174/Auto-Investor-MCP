"""Auto Investor MCP server protected by Auth0, with OBO calls to BE API."""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import urlencode

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

# Reuse the same OBO BE token for a given MCP access token so MFA state sticks.
# mcp_access_token -> (be_access_token, expires_at_epoch | None)
_be_token_cache: dict[str, tuple[str, float | None]] = {}
_BE_TOKEN_EXPIRY_SKEW_SECONDS = 30.0


def _require_access_token():
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("Missing authenticated access token")
    return access_token


async def _get_be_token(mcp_access_token: str) -> str:
    cached = _be_token_cache.get(mcp_access_token)
    if cached is not None:
        be_token, expires_at = cached
        if expires_at is None or expires_at > time.time() + _BE_TOKEN_EXPIRY_SKEW_SECONDS:
            return be_token
        _be_token_cache.pop(mcp_access_token, None)

    result = await api_client.get_token_on_behalf_of(
        access_token=mcp_access_token,
        audience=config.downstream_api_audience,
        scope=config.exchange_scope or None,
    )
    be_token = result["access_token"]
    expires_in = result.get("expires_in")
    expires_at = time.time() + float(expires_in) if expires_in is not None else None
    _be_token_cache[mcp_access_token] = (be_token, expires_at)
    logger.info("Cached new OBO BE token (expires_in=%s)", expires_in)
    return be_token


async def _be_request(method: str, path: str, json_body: dict | None = None) -> str:
    access_token = _require_access_token()
    be_token = await _get_be_token(access_token.token)

    base = config.api_base_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    url = f"{base}{suffix}"

    logger.info("Calling BE API via OBO: %s %s", method.upper(), url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method.upper(),
            url,
            headers={"Authorization": f"Bearer {be_token}"},
            json=json_body,
        )

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


async def _be_get(path: str) -> str:
    return await _be_request("GET", path)


async def _be_post(path: str, json_body: dict | None = None) -> str:
    return await _be_request("POST", path, json_body=json_body)


def _with_query(path: str, params: dict[str, str | int]) -> str:
    return f"{path}?{urlencode(params)}"


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


@mcp.tool()
async def verify_mfa(token: str) -> str:
    """Verify an MFA token with the Auto Investor BE API (`/api/v1/users/mfa/verify/`)."""
    return await _be_post("/users/mfa/verify/", {"token": token})


@mcp.tool()
async def get_broker_account(account_id: str) -> str:
    """Fetch a broker account from the Auto Investor BE API (`/api/v1/broker/account/`)."""
    return await _be_get(_with_query("/broker/account/", {"account_id": account_id}))


@mcp.tool()
async def place_broker_order(account_id: str, stock_ticker: str, quantity: int) -> str:
    """Place a broker order via the Auto Investor BE API (`/api/v1/broker/order/`)."""
    return await _be_post(
        _with_query(
            "/broker/order/",
            {
                "account_id": account_id,
                "stock_ticker": stock_ticker,
                "quantity": quantity,
            },
        )
    )


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
