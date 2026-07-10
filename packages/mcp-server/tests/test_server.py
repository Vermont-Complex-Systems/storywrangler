"""Tests for graceful HTTP error handling (no tracebacks on non-200)."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storywrangler_mcp import cli, server


def _client_with(handler):
    """Return an AsyncClient factory backed by a MockTransport handler."""
    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    return lambda *a, **k: orig(*a, **{**k, "transport": transport})


def test_get_raises_friendly_runtimeerror_on_404(monkeypatch):
    monkeypatch.setattr(server.httpx, "AsyncClient",
                        _client_with(lambda req: httpx.Response(404, text="nope")))
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(server._get("https://example.test/registry/"))
    msg = str(ei.value)
    assert "HTTP 404" in msg and "STORYWRANGLER_URL" in msg  # actionable, not a traceback


def test_get_returns_response_on_200(monkeypatch):
    monkeypatch.setattr(server.httpx, "AsyncClient",
                        _client_with(lambda req: httpx.Response(200, text="ok")))
    res = asyncio.run(server._get("https://example.test/llms.txt"))
    assert res.status_code == 200 and res.text == "ok"


def test_cli_prints_clean_error_not_traceback(monkeypatch, capsys):
    async def boom():
        raise RuntimeError("registry unreachable at api.example")
    monkeypatch.setattr(server, "list_datasets", boom)
    with pytest.raises(SystemExit) as ei:
        cli.main(["list-datasets"])
    assert ei.value.code == 1
    assert "registry unreachable" in capsys.readouterr().err
