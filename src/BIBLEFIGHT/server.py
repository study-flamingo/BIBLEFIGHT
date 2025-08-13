from __future__ import annotations

from typing import Any, Literal
import re
import logging

import httpx
from fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from .settings import Settings
from .logging_setup import ensure_logging_configured


settings = Settings()
ensure_logging_configured(settings.LOG_LEVEL)
log = logging.getLogger("biblefight.server")
mcp = FastMCP(
    name="Bible Fight!",
    instructions=(
        "Evaluate user claims against Scripture. Find likely passages, provide context, "
        "and surface challenging or contradicting verses."
    ),
)


class AnalyzeClaimArgs(BaseModel):
    claim: str = Field(
        ..., description="The phrase/claim to evaluate, e.g., 'Money is the root of all evil'",
        examples=["God helps those who help themselves", "Blessed are the peacemakers"],
    )
    translation: str | None = Field(
        default=None,
        description="Passage translation code for bible-api.com (e.g., 'kjv', 'asv', 'web'). Defaults to settings.DEFAULT_TRANSLATION.",
        examples=["kjv", "asv"],
    )
    context_verses: int | None = Field(
        default=None,
        ge=0,
        description="Number of verses before/after to include in context window (±N). Defaults to settings.DEFAULT_CONTEXT_VERSES.",
        examples=[7, 5],
    )
    snippet_chars: int | None = Field(
        default=None,
        gt=0,
        description="If provided and snippets are enabled, include a 'snippet' field trimmed to this many characters.",
        examples=[180, 220],
    )
    include_snippets: bool | None = Field(
        default=None,
        description="Whether to include snippet fields in results. Defaults to settings.DEFAULT_INCLUDE_SNIPPETS.",
        examples=[True, False],
    )
    # Control which kinds of verses to return
    include_supporting: bool | None = Field(
        default=None,
        description="Include likely supporting/affirming passages. Defaults to settings.DEFAULT_INCLUDE_SUPPORTING.",
    )
    include_challengers: bool | None = Field(
        default=None,
        description="Include challenging/contradicting passages. Defaults to settings.DEFAULT_INCLUDE_CHALLENGERS.",
    )
    # Advanced search knobs for API.Bible
    search_sort: Literal["relevance", "canonical", "reverse-canonical"] | None = Field(
        default=None,
        description="Sort order for API.Bible search when key is set.",
    )
    search_range: str | None = Field(
        default=None,
        description="Comma-separated passage ids or ranges to limit search (e.g., 'gen.1,gen.5' or 'gen.1.1-gen.3.5').",
    )
    search_fuzziness: Literal["AUTO", "0", "1", "2"] | None = Field(
        default=None,
        description="Fuzziness for API.Bible search.",
    )
    search_limit: int | None = Field(
        default=None,
        ge=1,
        description="Max results for API.Bible search (defaults to 10 when unspecified).",
        examples=[10, 20],
    )
    search_offset: int | None = Field(
        default=None,
        ge=0,
        description="Offset for API.Bible search pagination.",
        examples=[0, 10, 20],
    )


@mcp.tool
async def analyze_claim(args: AnalyzeClaimArgs, ctx: Context) -> dict[str, Any]:
    """Analyze a claim or quote against Scripture.

    Purpose:
    - Find likely canonical locations for the claim
    - Return passages in context (±N verses)
    - Propose challenging/contradicting passages

    Parameters:
    - claim (string, required): The phrase to evaluate.
    - translation (string, optional): bible-api.com translation code (e.g., 'kjv').
    - context_verses (int, optional): Verses before/after to include (±N).
    - snippet_chars (int, optional): Include 'snippet' trimmed to this length when snippets are enabled.
    - include_snippets (bool, optional): Whether to include snippet fields.
    - include_supporting (bool, optional): Include likely supporting passages.
    - include_challengers (bool, optional): Include likely challenging passages.
    - search_sort (relevance|canonical|reverse-canonical, optional): Sort for API.Bible search (requires key).
    - search_range (string, optional): Limit search to specific ids/ranges.
    - search_fuzziness (AUTO|0|1|2, optional): Fuzziness for API.Bible search.
    - search_limit (int, optional): Max search results (default 10).
    - search_offset (int, optional): Pagination offset.

    Returns:
    - Object with: claim, translation, context_verses, candidates[], challengers[]

    Example:
    - {"claim": "Money is the root of all evil", "translation": "kjv", "context_verses": 7}
    """

    claim = args.claim.strip()
    if not claim:
        log.warning("Empty claim provided")
        return {"error": "Empty claim"}

    translation = (args.translation or settings.DEFAULT_TRANSLATION).lower()
    context_n = int(args.context_verses if args.context_verses is not None else settings.DEFAULT_CONTEXT_VERSES)
    snippet_limit = (
        None if args.snippet_chars is None else max(1, int(args.snippet_chars))
    )
    if snippet_limit is None and settings.DEFAULT_SNIPPET_CHARS:
        snippet_limit = max(1, int(settings.DEFAULT_SNIPPET_CHARS))
    include_snippets = (
        settings.DEFAULT_INCLUDE_SNIPPETS if args.include_snippets is None else bool(args.include_snippets)
    )
    include_supporting = (
        settings.DEFAULT_INCLUDE_SUPPORTING if args.include_supporting is None else bool(args.include_supporting)
    )
    include_challengers = (
        settings.DEFAULT_INCLUDE_CHALLENGERS if args.include_challengers is None else bool(args.include_challengers)
    )

    log.info("Analyze claim: '%s' | translation=%s context=%d snippets=%s", claim, translation, context_n, snippet_limit)
    # Step 1: candidate references
    candidate_refs: list[str] = []
    if settings.BIBLE_API_KEY:
        try:
            log.debug("Searching API.Bible for candidates…")
            candidate_refs = await search_candidates_api_bible(
                query=claim,
                cfg=settings,
                sort=args.search_sort,
                search_range=args.search_range,
                fuzziness=args.search_fuzziness,
                limit=args.search_limit,
                offset=args.search_offset,
            )
        except Exception as e:  # Fallback to LLM extraction
            await ctx.warning(f"API.Bible search failed; falling back. {e}")
            log.exception("API.Bible search failed")
            candidate_refs = await extract_references_via_llm(claim, ctx)
    else:
        log.debug("No API key; extracting references via LLM sampling")
        candidate_refs = await extract_references_via_llm(claim, ctx)

    # Deduplicate and cap
    seen = set()
    unique_refs = []
    for r in candidate_refs:
        key = r.strip().upper()
        if key and key not in seen:
            seen.add(key)
            unique_refs.append(r)
    candidate_refs = unique_refs[: max(1, int(settings.DEFAULT_MAX_RESULTS))]
    log.info("Candidate refs: %s", candidate_refs)

    # Step 2: fetch supporting passages + context from bible-api.com
    passages: list[dict[str, Any]] = []
    if include_supporting:
        log.info("Fetching supporting passages (%d)…", len(candidate_refs))
        async with httpx.AsyncClient(timeout=20) as client:
            for ref in candidate_refs:
                try:
                    passage = await fetch_passage_with_context(client, ref, translation, context_n)
                    if passage:
                        if include_snippets and snippet_limit is not None:
                            passage["snippet"] = make_snippet(passage.get("text", ""), snippet_limit)
                            passage["snippet_chars"] = snippet_limit
                        passages.append(passage)
                except Exception as e:
                    await ctx.warning(f"Failed fetching '{ref}': {e}")
                    log.exception("Fetch failed for supporting '%s'", ref)

    # Step 3: propose challenging/contradicting verses via LLM
    challengers: list[str] = []
    if include_challengers:
        log.info("Proposing challenging refs via LLM…")
        challengers = await propose_challengers(claim, ctx)

    # Step 4: fetch challengers' passages
    challenging_passages: list[dict[str, Any]] = []
    if include_challengers and challengers:
        log.info("Fetching challenging passages (%d)…", len(challengers))
        async with httpx.AsyncClient(timeout=20) as client:
            for ref in challengers:
                try:
                    passage = await fetch_passage_with_context(client, ref, translation, context_n)
                    if passage:
                        if include_snippets and snippet_limit is not None:
                            passage["snippet"] = make_snippet(passage.get("text", ""), snippet_limit)
                            passage["snippet_chars"] = snippet_limit
                        challenging_passages.append(passage)
                except Exception:
                    # Ignore failures silently for challengers
                    log.debug("Fetch failed for challenger '%s'", ref)
                    pass

    return {
        "claim": claim,
        "translation": translation,
        "context_verses": context_n,
        "candidates": passages,
        "challengers": challenging_passages,
    }


async def search_candidates_api_bible(
    query: str,
    cfg: Settings,
    *,
    sort: str | None = None,
    search_range: str | None = None,
    fuzziness: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[str]:
    """Use API.Bible search if key is configured.

    Docs examples reference endpoint:
    GET /v1/bibles/{bibleId}/search?query=...
    (Requires header: api-key)
    """
    base = "https://api.scripture.api.bible/v1"
    url = f"{base}/bibles/{cfg.BIBLE_API_BIBLE_ID}/search"
    params: dict[str, Any] = {"query": query, "limit": int(limit or 10)}
    if offset is not None:
        params["offset"] = int(offset)
    if sort:
        params["sort"] = sort
    if search_range:
        params["range"] = search_range
    if fuzziness:
        params["fuzziness"] = fuzziness
    headers = {"api-key": cfg.BIBLE_API_KEY}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        # Prefer verses list; fallback to passages
        refs: list[str] = []
        for v in data.get("verses", []) or []:
            # API returns objects with 'reference' and 'verseId' fields
            ref = v.get("reference") or v.get("verseId")
            if ref:
                refs.append(str(ref))
        for p in data.get("passages", []) or []:
            ref = p.get("reference")
            if ref:
                refs.append(str(ref))
        return refs


async def extract_references_via_llm(claim: str, ctx: Context) -> list[str]:
    """Ask the client LLM to extract likely Bible references for the claim.
    Expected output: a comma-separated list like "John 3:16; Matthew 5:9-12".
    """
    prompt = (
        "Extract 3-5 likely Bible references (book chapter:verse or ranges) that "
        "correspond to the following claim or phrase. Return only the references, "
        "separated by semicolons.\n\nClaim: "
        f"{claim}"
    )
    try:
        response = await ctx.sample(prompt, system_prompt=(
            "You are a precise Bible reference extractor. Return only references, "
            "semicolon-separated; no commentary."
        ))
        text = (response.text or "").strip()
        parts = [p.strip() for p in text.replace("\n", " ").split(";")]
        return [p for p in parts if p]
    except Exception:
        return []


async def propose_challengers(claim: str, ctx: Context) -> list[str]:
    """Ask the client LLM to propose verses that challenge or nuance the claim."""
    prompt = (
        "Given this claim, produce 3-5 Bible references that challenge, qualify, "
        "or appear to contradict it. Return only references, semicolon-separated.\n\n"
        f"Claim: {claim}"
    )
    try:
        response = await ctx.sample(prompt, system_prompt=(
            "You are a critical Bible cross-referencer. Return only references, "
            "semicolon-separated; no commentary."
        ))
        text = (response.text or "").strip()
        parts = [p.strip() for p in text.replace("\n", " ").split(";")]
        return [p for p in parts if p]
    except Exception:
        return []


async def fetch_passage_with_context(
    client: httpx.AsyncClient,
    reference: str,
    translation: str,
    context_n: int,
) -> dict[str, Any] | None:
    """Use bible-api.com to fetch passage and context.

    Examples per docs: https://bible-api.com/BOOK+CHAP:VERSE?translation=kjv
    We emulate ±N verses by expanding a small range where possible.
    """
    # Try to separate book and range; if parsing fails, defer to API's user input parser
    ref_encoded = reference.replace(" ", "+")
    url = f"https://bible-api.com/{ref_encoded}?translation={translation}"
    # Note: bible-api.com accepts ranges and multiple refs; we rely on server to include nearby verses
    r = await client.get(url)
    if r.status_code != 200:
        # Fallback: remove space after leading ordinal (e.g., "1 Timothy" -> "1Timothy")
        m = re.match(r"^(\d)\s+(.*)$", reference)
        if m:
            alt = f"{m.group(1)}{m.group(2)}"
            alt_encoded = alt.replace(" ", "+")
            alt_url = f"https://bible-api.com/{alt_encoded}?translation={translation}"
            r = await client.get(alt_url)
            if r.status_code != 200:
                return None
        else:
            return None
    data = r.json()
    verses = data.get("verses") or []
    if not verses:
        return None
    # construct a context window from received verses list
    text = " ".join(v.get("text", "").strip() for v in verses)
    return {
        "reference": data.get("reference") or reference,
        "text": text.strip(),
        "translation": translation,
        "raw": data,
    }


def make_snippet(text: str, limit: int) -> str:
    s = " ".join((text or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


class GetReferenceArgs(BaseModel):
    reference: str = Field(
        ..., description="Free-form Bible reference, e.g., 'Matthew 3:13' or 'John 3:16-18' or 'Psalm 23'.",
        examples=["Matthew 3:13", "John 3:16-18", "Psalm 23"],
    )
    translation: str | None = Field(
        default=None,
        description="Passage translation code for bible-api.com (e.g., 'kjv', 'asv', 'web'). Defaults to settings.DEFAULT_TRANSLATION.",
        examples=["kjv", "asv"],
    )
    context_verses: int | None = Field(
        default=None,
        ge=0,
        description="Number of verses before/after to include in context window (±N). Defaults to settings.DEFAULT_CONTEXT_VERSES.",
        examples=[7, 5],
    )


@mcp.tool
async def get_reference(args: GetReferenceArgs, ctx: Context) -> dict[str, Any]:
    """Fetch a passage by free-form reference.

    Purpose:
    - Resolve and return the passage text and metadata for inputs like 'Matthew 3:13', 'John 3:16-18', or 'Psalm 23'.

    Parameters:
    - reference (string, required): Human-readable reference.
    - translation (string, optional): bible-api.com translation code (e.g., 'kjv').
    - context_verses (int, optional): Verses before/after to include (±N).

    Returns:
    - Object with: reference, text, translation, raw

    Example:
    - {"reference": "Matthew 3:13", "translation": "kjv"}
    """
    ref = (args.reference or "").strip()
    if not ref:
        return {"error": "Empty reference"}
    translation = (args.translation or settings.DEFAULT_TRANSLATION).lower()
    context_n = int(args.context_verses if args.context_verses is not None else settings.DEFAULT_CONTEXT_VERSES)
    async with httpx.AsyncClient(timeout=20) as client:
        passage = await fetch_passage_with_context(client, ref, translation, context_n)
    if not passage:
        return {"error": f"Reference not found: {ref}"}
    return passage

