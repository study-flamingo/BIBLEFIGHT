### Bible Fight! — MCP Server

An MCP server that evaluates a user-provided claim or quote "from the Bible":
- Finds likely canonical locations for the claim
- Returns the verses in context (default 7-verse window)
- Surfaces challenging or contradicting passages to stress-test the claim

Built with FastMCP 2.11 and UV. No API keys required by default; optional API.Bible search support if you have a key.

### Quick start

1) Install dependencies (UV is already configured):

```
uv sync
```

2) (Optional) Create a `.env` to set defaults and keys. Example:

```dotenv
# API.Bible (optional, for keyword search)
BIBLE_API_KEY=your_key
BIBLE_API_BIBLE_ID=06125adad2d5898a-01

# Bible Fight defaults
DEFAULT_TRANSLATION=kjv
BIBLEFIGHT_DEFAULT_CONTEXT_VERSES=7
BIBLEFIGHT_DEFAULT_SNIPPET_CHARS=180
BIBLEFIGHT_INCLUDE_SNIPPETS=true
BIBLEFIGHT_DEFAULT_MAX_RESULTS=5
```

Supported env vars:
- `BIBLE_API_KEY`: API.Bible key (enables full-text search)
- `BIBLE_API_BIBLE_ID`: API.Bible Bible ID (default `06125adad2d5898a-01` ASV)
- `DEFAULT_TRANSLATION`: bible-api.com translation for passages (default `kjv`)
 - `BIBLEFIGHT_DEFAULT_CONTEXT_VERSES`: default verses ±N (default `7`)
 - `BIBLEFIGHT_DEFAULT_SNIPPET_CHARS`: default snippet length (default `180`)
 - `BIBLEFIGHT_INCLUDE_SNIPPETS`: include snippets by default (default `true`)
 - `BIBLEFIGHT_DEFAULT_MAX_RESULTS`: cap on candidate refs (default `5`)
 - `BIBLEFIGHT_INCLUDE_SUPPORTING`: include supporting passages by default (default `true`)
 - `BIBLEFIGHT_INCLUDE_CHALLENGERS`: include challenging passages by default (default `true`)
 - `BIBLEFIGHT_LOG_LEVEL`: logging level (e.g., `INFO`, `DEBUG`) if not set via CLI

3) Run the server in dev inspector (module server is at `src/BIBLEFIGHT/server.py`):

```
uv run fastmcp dev src/BIBLEFIGHT/server.py
```

Or run directly:

```bash
uv run python -m BIBLEFIGHT --log-level INFO
# or
uv run python -m BIBLEFIGHT --debug
```

### Tool: analyze_claim

Arguments:
- `claim`: The phrase/claim to evaluate
- `translation` (optional): Translation code for passages (bible-api.com; default `kjv`)
- `context_verses` (optional): Verses before/after to include (default 7)
- `snippet_chars` (optional): If provided, server includes a `snippet` field per passage trimmed to this char length (default 180)
- `include_snippets` (optional): If true (default), includes `snippet` fields. Set false to request full text only.
- `include_supporting` (optional): If true (default), return supporting/affirming passages.
- `include_challengers` (optional): If true (default), return challenging/contradicting passages.
- Advanced search (API.Bible `/search`):
  - `search_sort` (optional): `relevance` | `canonical` | `reverse-canonical`
  - `search_range` (optional): Limit search to ids/ranges (e.g., `gen.1,gen.5` or `gen.1.1-gen.3.5`)
  - `search_fuzziness` (optional): `AUTO` | `0` | `1` | `2`
  - `search_limit` / `search_offset` (optional): pagination

Behavior:
- If `BIBLE_API_KEY` is set, uses API.Bible search to find likely matches
- Otherwise, uses the connected LLM (via MCP sampling) to extract likely references
- Fetches passages and context using bible-api.com
- Uses LLM to propose challenging/contradictory references, then fetches them
- If `include_snippets` is true and `snippet_chars` is set, responses include both `text` (full) and `snippet` (trimmed)

### Additional tool

- `get_reference(reference, translation?, context_verses?)`
  - Fetches a passage by free-form reference like "Matthew 3:13", returns full text and metadata using bible-api.com

### Sources
- FastMCP 2.x docs: gofastmcp.com (Quickstart, tools, sampling)
- bible-api.com usage (passage retrieval, translations)
- API.Bible search docs (optional, requires key)


