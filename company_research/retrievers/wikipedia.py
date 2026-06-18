from datetime import datetime
from typing import Any

import httpx

from company_research.__version__ import __version__
from company_research.config import settings
from company_research.exceptions import WikipediaRetrievalError
from company_research.schemas.models import SourceMetadata, WikipediaData

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_OPENSEARCH = "https://en.wikipedia.org/w/api.php"

_USER_AGENT = (
    f"CompanyResearchAgent/{__version__} "
    "(https://github.com/company-research; contact@example.com)"
)


async def _search_wikipedia(company_name: str, client: httpx.AsyncClient) -> str:
    params: dict[str, str | int] = {
        "action": "opensearch",
        "search": company_name,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }
    resp = await client.get(
        WIKIPEDIA_OPENSEARCH,
        params=params,
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    titles = data[1]
    if not titles:
        msg = f"No Wikipedia page found for '{company_name}'"
        raise WikipediaRetrievalError(msg)
    return str(titles[0])


async def _fetch_page_summary(
    title: str, client: httpx.AsyncClient
) -> dict[str, Any]:
    resp = await client.get(
        f"{WIKIPEDIA_API}/page/summary/{title}",
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def retrieve_wikipedia(company_name: str) -> WikipediaData | None:
    start = datetime.now()
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(headers=headers) as client:
        try:
            normalized_title = await _search_wikipedia(company_name, client)
            summary_data = await _fetch_page_summary(normalized_title, client)
        except WikipediaRetrievalError:
            raise
        except httpx.HTTPStatusError as e:
            msg = f"Wikipedia API HTTP {e.response.status_code}: {e.response.text[:200]}"
            raise WikipediaRetrievalError(msg) from e
        except httpx.RequestError as e:
            msg = f"Wikipedia request failed: {e}"
            raise WikipediaRetrievalError(msg) from e

    elapsed = int((datetime.now() - start).total_seconds() * 1000)

    return WikipediaData(
        metadata=SourceMetadata(
            source="wikipedia",
            retrieved_at=datetime.now(),
            elapsed_ms=elapsed,
        ),
        title=str(summary_data.get("title", normalized_title)),
        summary=str(summary_data.get("extract", "")),
        url=str(summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")),
        infobox={},
        categories=[],
    )
