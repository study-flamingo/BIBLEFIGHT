from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest


# Ensure src/ on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from BIBLEFIGHT.server import (  # type: ignore
    mcp,
)

from fastmcp import Client  # type: ignore
from fastmcp.client.transports import FastMCPTransport  # type: ignore


def _parse_payload(resp: Any) -> dict[str, Any] | None:
    payload = getattr(resp, "structured_content", None)
    if isinstance(payload, dict) and payload:
        return payload
    data_obj = getattr(resp, "data", None)
    if isinstance(data_obj, dict) and data_obj:
        return data_obj
    try:
        for c in getattr(resp, "content", []) or []:
            text = getattr(c, "text", None)
            if text:
                return json.loads(text)
    except Exception:
        return None
    return None


@pytest.mark.asyncio
async def test_get_reference_monkeypatched(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stub_fetch(client: Any, reference: str, translation: str, context_n: int) -> dict[str, Any] | None:  # noqa: ANN401
        return {
            "reference": reference,
            "text": f"Stub text for {reference} in {translation} (±{context_n})",
            "translation": translation,
            "raw": {"verses": [{"text": "stub"}]},
        }

    # Patch the passage fetcher to avoid network
    import BIBLEFIGHT.server as srv  # type: ignore

    monkeypatch.setattr(srv, "fetch_passage_with_context", stub_fetch)

    transport = FastMCPTransport(mcp)
    async with Client(transport) as client:
        resp = await client.call_tool(
            "get_reference",
            {"args": {"reference": "Matthew 3:13", "translation": "kjv", "context_verses": 7}},
        )
        payload = _parse_payload(resp)
        assert isinstance(payload, dict)
        assert payload.get("reference") == "Matthew 3:13"
        assert payload.get("translation") == "kjv"
        assert "Stub text for Matthew 3:13" in payload.get("text", "")


@pytest.mark.asyncio
async def test_analyze_claim_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch LLM-dependent functions and passage fetches
    async def stub_extract(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return ["John 3:16", "Psalm 23:1-3"]

    async def stub_challengers(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return ["Matthew 5:9-12"]

    async def stub_fetch(client: Any, reference: str, translation: str, context_n: int) -> dict[str, Any] | None:  # noqa: ANN401
        return {
            "reference": reference,
            "text": f"Text for {reference}",
            "translation": translation,
            "raw": {"verses": [{"text": "stub"}]},
        }

    import BIBLEFIGHT.server as srv  # type: ignore

    monkeypatch.setattr(srv, "extract_references_via_llm", stub_extract)
    monkeypatch.setattr(srv, "propose_challengers", stub_challengers)
    monkeypatch.setattr(srv, "fetch_passage_with_context", stub_fetch)

    transport = FastMCPTransport(mcp)
    async with Client(transport) as client:
        args = {
            "claim": "Money is the root of all evil",
            "translation": "kjv",
            "context_verses": 7,
            "include_snippets": True,
            "snippet_chars": 50,
            "include_supporting": True,
            "include_challengers": True,
        }
        resp = await client.call_tool("analyze_claim", {"args": args})
        payload = _parse_payload(resp)
        assert isinstance(payload, dict)
        # Candidates and challengers should be present
        candidates = payload.get("candidates") or []
        challengers = payload.get("challengers") or []
        assert isinstance(candidates, list) and isinstance(challengers, list)
        assert any(p.get("reference") == "John 3:16" for p in candidates)
        assert any(p.get("reference") == "Matthew 5:9-12" for p in challengers)
        # Snippet should be present and trimmed
        for p in (candidates + challengers):
            assert "text" in p
            assert "snippet" in p
            assert p.get("snippet_chars") == 50


@pytest.mark.asyncio
async def test_analyze_claim_empty_claim_via_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from BIBLEFIGHT.server import AnalyzeClaimArgs  # type: ignore

    # Avoid LLM calls by stubbing sampling to return nothing
    import BIBLEFIGHT.server as srv  # type: ignore

    async def stub_extract(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return []

    async def stub_challengers(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return []

    monkeypatch.setattr(srv, "extract_references_via_llm", stub_extract)
    monkeypatch.setattr(srv, "propose_challengers", stub_challengers)

    transport = FastMCPTransport(mcp)
    async with Client(transport) as client:
        resp = await client.call_tool("analyze_claim", {"args": AnalyzeClaimArgs(claim="   ").model_dump()})
        payload = _parse_payload(resp)
        assert isinstance(payload, dict)
        assert payload.get("error") == "Empty claim"



@pytest.mark.asyncio
async def test_analyze_claim_fallback_when_no_sampling_or_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure analyze_claim returns content using deterministic fallback when both
    API.Bible search (no key) and sampling are unavailable (return empty).
    """
    import BIBLEFIGHT.server as srv  # type: ignore

    # Disable API key path
    monkeypatch.setattr(srv.settings, "BIBLE_API_KEY", None, raising=False)

    # Force LLM extractors to return nothing
    async def stub_extract(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return []

    async def stub_challengers(claim: str, ctx: Any) -> list[str]:  # noqa: ANN401
        return []

    # Stub passage fetcher to avoid network and return predictable content
    async def stub_fetch(client: Any, reference: str, translation: str, context_n: int) -> dict[str, Any] | None:  # noqa: ANN401
        return {
            "reference": reference,
            "text": f"Text for {reference}",
            "translation": translation,
            "raw": {"verses": [{"text": "stub"}]},
        }

    monkeypatch.setattr(srv, "extract_references_via_llm", stub_extract)
    monkeypatch.setattr(srv, "propose_challengers", stub_challengers)
    monkeypatch.setattr(srv, "fetch_passage_with_context", stub_fetch)

    from fastmcp import Client  # type: ignore
    from fastmcp.client.transports import FastMCPTransport  # type: ignore

    transport = FastMCPTransport(srv.mcp)
    async with Client(transport) as client:
        args = {
            "claim": "Money is the root of all evil",
            "translation": "kjv",
            "context_verses": 7,
            "include_snippets": True,
            "snippet_chars": 50,
            "include_supporting": True,
            "include_challengers": True,
        }
        resp = await client.call_tool("analyze_claim", {"args": args})
        payload = _parse_payload(resp)
        assert isinstance(payload, dict)
        candidates = payload.get("candidates") or []
        challengers = payload.get("challengers") or []
        assert isinstance(candidates, list) and len(candidates) > 0
        assert isinstance(challengers, list) and len(challengers) > 0
        for p in (candidates + challengers):
            assert "text" in p
            assert "snippet" in p
            assert p.get("snippet_chars") == 50
