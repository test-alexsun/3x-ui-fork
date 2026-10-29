"""Sanitized diagnostics from explicit read-only APIs."""

from __future__ import annotations

from .api_client import ApiClient


def panel_summary(client: ApiClient) -> dict:
    status = client.read("server/status")
    inbounds = client.read("inbounds/list")
    clients = client.read("clients/list")
    return {
        "api_reachable": True,
        "status_type": type(status).__name__,
        "inbound_count": len(inbounds) if isinstance(inbounds, list) else None,
        "client_count": len(clients) if isinstance(clients, list) else None,
    }
