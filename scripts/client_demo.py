from __future__ import annotations

import asyncio
import sys
import json
from pathlib import Path
from typing import Any

from fastmcp import Client  # type: ignore
from fastmcp.client.sampling import (  # type: ignore
    RequestContext,
    SamplingMessage,
    SamplingParams,
)
from fastmcp.client.transports import FastMCPTransport  # type: ignore

# Ensure the src/ package path is available for imports when run from project root
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from BIBLEFIGHT.server import mcp  # type: ignore


async def sampling_handler(
    messages: list[SamplingMessage],
    params: SamplingParams,
    ctx: RequestContext,
) -> str:
    """Very simple sampling handler for demos.

    Heuristics:
    - If user mentions money/wealth, return common refs
    - If claim contains "helps themselves", return common misattribution refs
    - Otherwise return a generic pair
    """
    text = " \n".join(getattr(m, "text", "") for m in messages if getattr(m, "text", ""))
    lower = text.lower()
    if "money" in lower or "wealth" in lower or "rich" in lower:
        return "1 Timothy 6:10; Matthew 6:24; Proverbs 11:28"
    if "helps themselves" in lower:
        return "Proverbs 28:26; Psalm 37:5; Jeremiah 17:5; Matthew 6:33"
    return "John 3:16; Psalm 23:1-3; Matthew 5:9-12"


async def main() -> None:
    transport = FastMCPTransport(mcp)
    async with Client(transport, sampling_handler=sampling_handler) as client:
        tests: list[dict[str, Any]] = [
            {
                "label": "Money is the root of all evil",
                "args": {
                    "claim": "Money is the root of all evil",
                    "translation": "kjv",
                    "context_verses": 7,
                },
            },
            {
                "label": "God helps those who help themselves",
                "args": {
                    "claim": "God helps those who help themselves",
                    "translation": "kjv",
                    "context_verses": 7,
                },
            },
            {
                "label": "Only supporting (no challengers)",
                "args": {
                    "claim": "Blessed are the peacemakers",
                    "translation": "kjv",
                    "context_verses": 7,
                    "include_supporting": True,
                    "include_challengers": False,
                },
            },
            {
                "label": "Only challengers (no supporting)",
                "args": {
                    "claim": "Money is the root of all evil",
                    "translation": "kjv",
                    "context_verses": 7,
                    "include_supporting": False,
                    "include_challengers": True,
                    "include_snippets": False,
                },
            },
        ]

        for t in tests:
            print("\n===", t["label"], "===")
            # Ask for slightly longer snippets to demonstrate configurability
            args = dict(t["args"])  # copy
            args["snippet_chars"] = 220
            args["include_snippets"] = True  # set False to request full text only
            resp = await client.call_tool("analyze_claim", {"args": args})

            # Prefer structured_content/data when available; fallback to JSON text
            payload: dict[str, Any] | None = None
            structured = getattr(resp, "structured_content", None)
            if isinstance(structured, dict) and structured:
                payload = structured
            else:
                data_obj = getattr(resp, "data", None)
                if isinstance(data_obj, dict) and data_obj:
                    payload = data_obj
            if payload is None:
                try:
                    for c in getattr(resp, "content", []) or []:
                        text = getattr(c, "text", None)
                        if text:
                            payload = json.loads(text)
                            break
                except Exception:
                    payload = None

            if not isinstance(payload, dict):
                print("(No structured payload)")
                continue

            def snippet(txt: str, limit: int = 180) -> str:
                s = " ".join((txt or "").split())
                if len(s) <= limit:
                    return s
                return s[: limit - 1] + "…"

            candidates = (payload.get("candidates") or [])[:3]
            challengers = (payload.get("challengers") or [])[:3]
            print("Candidates:")
            for p in candidates:
                ref = (p.get("reference") or (p.get("raw") or {}).get("reference"))
                txt = p.get("snippet") or p.get("text") or (p.get("raw") or {}).get("text") or ""
                if ref:
                    print(f" - {ref}: {snippet(txt)}")
            print("Challengers:")
            for p in challengers:
                ref = (p.get("reference") or (p.get("raw") or {}).get("reference"))
                txt = p.get("snippet") or p.get("text") or (p.get("raw") or {}).get("text") or ""
                if ref:
                    print(f" - {ref}: {snippet(txt)}")


if __name__ == "__main__":
    asyncio.run(main())


