"""Shared pytest fixtures and httpx2 mock registration for RESPX."""

from __future__ import annotations

import respx.mocks
from respx.mocks import HTTPCoreMocker


class HTTPCore2Mocker(HTTPCoreMocker):
    """Patch httpcore2 so RESPX can mock httpx2 clients (Starlette TestClient + app)."""

    name = "httpcore2"
    targets = [
        "httpcore2._sync.connection.HTTPConnection",
        "httpcore2._sync.connection_pool.ConnectionPool",
        "httpcore2._sync.http_proxy.HTTPProxy",
        "httpcore2._async.connection.AsyncHTTPConnection",
        "httpcore2._async.connection_pool.AsyncConnectionPool",
        "httpcore2._async.http_proxy.AsyncHTTPProxy",
    ]


# Prefer httpx2 / httpcore2 for all @respx.mock usage in this suite.
respx.mocks.DEFAULT_MOCKER = "httpcore2"
