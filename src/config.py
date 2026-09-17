"""Load MCP server configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    auth0_domain: str
    auth0_audience: str
    auth0_client_id: str
    auth0_client_secret: str
    mcp_server_url: str
    downstream_api_audience: str
    downstream_api_url: str
    exchange_scope: str
    host: str
    port: int

    @property
    def issuer_url(self) -> str:
        return f"https://{self.auth0_domain}/"

    @property
    def api_base_url(self) -> str:
        """HTTP base used when calling the downstream Auto Investor API."""
        auto_investor = os.getenv("AUTO_INVESTOR_URL", "").rstrip("/")
        if auto_investor:
            return auto_investor
        return f"{self.downstream_api_url.rstrip('/')}/api/v1"


def get_config() -> Config:
    domain = os.getenv("AUTH0_DOMAIN", "").strip()
    audience = os.getenv("AUTH0_AUDIENCE", "").strip()
    client_id = os.getenv("AUTH0_CLIENT_ID", "").strip()
    client_secret = os.getenv("AUTH0_CLIENT_SECRET", "").strip()
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001/").strip()
    downstream_audience = os.getenv("DOWNSTREAM_API_AUDIENCE", "").strip()
    downstream_url = os.getenv("DOWNSTREAM_API_URL", "http://127.0.0.1:8000").strip()
    exchange_scope = os.getenv("MCP_AUTH0_EXCHANGE_SCOPE", "").strip()
    host = os.getenv("HOST", "127.0.0.1").strip()
    port = int(os.getenv("PORT", "8001"))

    missing = [
        name
        for name, value in [
            ("AUTH0_DOMAIN", domain),
            ("AUTH0_AUDIENCE", audience),
            ("AUTH0_CLIENT_ID", client_id),
            ("AUTH0_CLIENT_SECRET", client_secret),
            ("DOWNSTREAM_API_AUDIENCE", downstream_audience),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    return Config(
        auth0_domain=domain,
        auth0_audience=audience,
        auth0_client_id=client_id,
        auth0_client_secret=client_secret,
        mcp_server_url=mcp_server_url,
        downstream_api_audience=downstream_audience,
        downstream_api_url=downstream_url,
        exchange_scope=exchange_scope,
        host=host,
        port=port,
    )
