# Company Research Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](
https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green)](
LICENSE)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000)](
https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](
http://mypy-lang.org/)

Research any company by name — fetch Wikipedia and GitHub data in parallel using LangChain's `RunnableParallel`, then collect everything into a single strongly-typed `CompanyResearchBundle` schema.

---

## The Problem

### Latency multiplication in sequential retrieval

In production RAG pipelines, agentic systems, or research automation, you often need data from N independent sources. The naive approach is sequential:

```python
wiki = await fetch_wikipedia(company)   # 800ms
github = await fetch_github(company)    # 2500ms
# total: 3300ms
```

Each source adds its full latency to the total. With N sources, total latency is `sum(latency_i)` — linear in N.

`RunnableParallel` runs all sources simultaneously. Total latency becomes `max(latency_i)`, not `sum(latency_i)`:

```python
wiki, github = await asyncio.gather(
    fetch_wikipedia(company),   # 800ms
    fetch_github(company),      # 2500ms
)
# total: 2500ms (not 3300ms)
```

In this project, the Wikipedia and GitHub retrievers run in parallel via `RunnablePassthrough.assign`. As you add more sources (SEC EDGAR, RSS feeds, Crunchbase), each new source adds zero additional wall-clock latency.

### Fragile pipelines break on partial failure

Real-world API calls fail. Rate limits, 404s, transient network errors. Most pipeline implementations crash on the first exception, losing all data from every source, even the ones that succeeded.

This project wraps each retriever in a `_safe_*` catch-all that converts exceptions into `RetrievalError` entries in an `errors[]` list. The pipeline always produces a valid `CompanyResearchBundle` — successful sources populate their fields, failed sources leave their field as `None`, and every failure is recorded with its source name, error type, and detail.

```python
# Even if GitHub 404s, Wikipedia data is preserved:
{
  "wikipedia": { "title": "OpenAI", "summary": "..." },
  "github": null,
  "errors": [
    { "source": "github", "error_type": "GitHubRetrievalError", "detail": "..." }
  ]
}
```

### Surface coupling forces every consumer to re-parse

Without a canonical schema, each downstream consumer (LLM summarizer, dashboard, report generator) must independently parse raw Wikipedia JSON, GitHub JSON, etc. This creates:

- **Fragile consumers** — every API change requires updating every consumer
- **Inconsistent interpretation** — two consumers may extract different fields for the same concept
- **No validation boundary** — malformed API responses propagate deep into the system

The `CompanyResearchBundle` Pydantic model provides a single, versioned contract between the retrieval layer and everything downstream. Consumers import the model and work with typed fields, not raw JSON.

---

## Architecture

```
User Input: "OpenAI"
        │
        ▼
┌──────────────────────────────────────────────────┐
│  RunnablePassthrough.assign(                     │
│    wiki=itemgetter("company_name")               │
│         │ WikipediaRetriever,                    │  runs
│    gh=itemgetter("company_name")                 │  in
│         │ GitHubRetriever,                       │  parallel
│  )                                               │
└───────────────┬──────────────────┬───────────────┘
                │                  │
         WikipediaData        GitHubData
         (or None)            (or None)
                │                  │
                └──────┬───────────┘
                       ▼
          ┌────────────────────────┐
          │     _aggregate()       │
          │  combine + validate    │
          └──────────┬─────────────┘
                     ▼
          CompanyResearchBundle
                     │
                     ▼
              JSON to stdout
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/chrisipanaque/langchain-runnableparallel-company-research.git
cd company-research

# 2. Install
pip install .

# 3. Run
company-research "OpenAI"
```

Expected output (condensed):

```json
{
  "company_name": "OpenAI",
  "wikipedia": {
    "title": "OpenAI",
    "summary": "OpenAI is an American AI research organization...",
    "url": "https://en.wikipedia.org/wiki/OpenAI"
  },
  "github": {
    "org_name": "openai",
    "public_repos": 257,
    "total_stars": 4502,
    "top_repos": [
      {"name": "privacy-filter", "stars": 2460, "language": "Python"},
      {"name": "openai-cli", "stars": 626, "language": "Go"}
    ],
    "languages": {
      "Python": 2832438,
      "Go": 1198473,
      "TypeScript": 812620
    },
    "contributors_count": 1
  },
  "errors": []
}
```

### Development install

```bash
pip install -e ".[dev]"
```

---

## Usage

```
company-research [OPTIONS] COMPANY_NAME
```

| Option | Flag | Default | Description |
|---|---|---|---|
| `--github-token` | `-t` | `""` | GitHub PAT. Without it: 60 req/hr. With it: 5000 req/hr. Also reads `COMPANY_RESEARCH_GITHUB_TOKEN` env var. |
| `--timeout` | `-T` | `30` | Request timeout per source (seconds) |
| `--verbose` | `-v` | `False` | Enable debug logging |
| `--pretty` / `--compact` | | `pretty` | Pretty-print or single-line JSON |
| `--version` | | | Print version and exit |

### Examples

```bash
# Pretty-print (default)
company-research "Anthropic" --pretty

# Compact JSON (for piping into jq or other tools)
company-research "OpenAI" --compact

# With GitHub token (avoids rate limiting)
company-research "Meta" --github-token ghp_xxxx

# Timeout for slow networks
company-research "Google" --timeout 60
```

### Rate limits

| Source | No auth | With auth |
|---|---|---|
| Wikipedia | No limit (be polite) | Same |
| GitHub | 60 req/hr | 5000 req/hr |

For reliable GitHub usage, set `COMPANY_RESEARCH_GITHUB_TOKEN` in your `.env` file or pass `--github-token`.

---

## How It Works

### The RunnableParallel chain

At the core is `pipeline.py`:

```python
research_chain = (
    RunnablePassthrough.assign(
        wiki=itemgetter("company_name") | RunnableLambda(_safe_wiki),
        gh=itemgetter("company_name") | RunnableLambda(_safe_github),
    )
    | RunnableLambda(_aggregate)
)
```

**Step by step:**

1. **Input** — a dict `{"company_name": "OpenAI"}` enters the chain.
2. **`RunnablePassthrough.assign`** — passes the input through unchanged, but also runs two branches in parallel. Each branch uses `itemgetter("company_name")` to extract just the company name string before handing it to the retriever lambda.
3. **`_safe_wiki` / `_safe_github`** — each calls its respective async retriever wrapped in try/except. Returns `{"data": ... | None, "error": ... | None}`.
4. **`_aggregate`** — merges the parallel results into a single `CompanyResearchBundle`, collecting any errors into the `errors[]` list.

### Partial failure by design

Every source field in `CompanyResearchBundle` is `Optional`:

```python
class CompanyResearchBundle(BaseModel):
    company_name: str
    retrieved_at: datetime
    wikipedia: WikipediaData | None = None
    github: GitHubData | None = None
    errors: list[RetrievalError] = []
```

If Wikipedia fails with a 403 but GitHub succeeds, you get back a complete bundle with `wikipedia=None` and one entry in `errors[]`. No exception escapes the chain.

### Schema-first design

The `CompanyResearchBundle` is the **sole output of the retrieval layer**. It is designed to be the input to downstream components (LLM summarizer, dashboard, RAG indexer) without further parsing. Adding a new source means:

1. Define a new Pydantic model in `schemas/models.py`
2. Add an `Optional` field to `CompanyResearchBundle`
3. Create a retriever in `retrievers/`
4. Add it to `RunnablePassthrough.assign`

No consumer code needs to change.

---

## Project Structure

```
company_research/
  __init__.py
  __main__.py            # python -m company_research
  __version__.py         # single source of truth for version
  main.py                # Typer CLI + async runner
  pipeline.py            # RunnablePassthrough.assign chain
  config.py              # pydantic-settings (env vars, .env)
  exceptions.py          # typed errors per source
  schemas/
    models.py            # CompanyResearchBundle + per-source models
  retrievers/
    wikipedia.py         # Wikipedia REST API (opensearch + page summary)
    github.py            # GitHub REST API (org, repos, languages, members)
tests/
  test_schemas.py        # model validation + JSON roundtrip
  test_retrievers.py     # Wikipedia + GitHub (mocked HTTP via respx)
  test_pipeline.py       # safe wrappers + aggregation (mocked via unittest.patch)
pyproject.toml           # deps, entry point, tool config
LICENSE
.env.example
```

---

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check .

# Type check
mypy company_research/

# Test
pytest tests/ -v

# Test with coverage
pytest tests/ --cov=company_research -v
```

---

## Extending with New Sources

Adding a new data source takes four steps:

1. **Create a retriever** — `company_research/retrievers/<source>.py` with an async function `retrieve_<source>(company_name: str) -> SourceData | None`
2. **Define a schema** — add a Pydantic model in `schemas/models.py`
3. **Add to the bundle** — add the field to `CompanyResearchBundle`
4. **Wire into the pipeline** — add to `RunnablePassthrough.assign` in `pipeline.py`

Example:

```python
# pipeline.py
research_chain = (
    RunnablePassthrough.assign(
        wiki=itemgetter("company_name") | RunnableLambda(_safe_wiki),
        gh=itemgetter("company_name") | RunnableLambda(_safe_github),
        crunchbase=itemgetter("company_name") | RunnableLambda(_safe_crunchbase),
    )
    | RunnableLambda(_aggregate)
)
```

---

## License

MIT
