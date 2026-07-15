import re
from datetime import datetime
from typing import Any

import httpx

from company_research.config import settings
from company_research.exceptions import GitHubRetrievalError
from company_research.schemas.models import GitHubData, RepoInfo, SourceMetadata

GITHUB_API = "https://api.github.com"

TOP_REPOS_LIMIT = 10
REPOS_PER_PAGE = 100


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "company-research-agent",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def _fetch_org(org: str, client: httpx.AsyncClient) -> dict[str, Any]:
    resp = await client.get(
        f"{GITHUB_API}/orgs/{org}",
        headers=_auth_headers(),
        timeout=settings.request_timeout,
    )
    if resp.status_code == 404:
        msg = f"GitHub org '{org}' not found"
        raise GitHubRetrievalError(msg)
    if resp.status_code in (403, 429):
        msg = f"GitHub API rate limit exceeded or access denied: {resp.text[:200]}"
        raise GitHubRetrievalError(msg)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def _fetch_repos(
    org: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Fetch every public repo for the org.

    Note: GitHub's ``GET /orgs/{org}/repos`` endpoint only supports
    ``sort`` values of ``created | updated | pushed | full_name`` (default
    ``created``) -- there is no server-side ``stars`` sort, so an invalid
    value is silently ignored. To rank by stars we must page through all
    repositories and sort client-side (see :func:`retrieve_github`).
    """
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/repos",
            params={"per_page": REPOS_PER_PAGE, "page": page},
            headers=_auth_headers(),
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < REPOS_PER_PAGE:
            break
        page += 1
    return repos


async def _fetch_languages(
    org: str, repo: str, client: httpx.AsyncClient
) -> dict[str, float]:
    resp = await client.get(
        f"{GITHUB_API}/repos/{org}/{repo}/languages",
        headers=_auth_headers(),
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def _aggregate_languages(
    org: str, top_repos: list[dict[str, Any]], client: httpx.AsyncClient
) -> dict[str, float]:
    aggregated: dict[str, float] = {}
    for repo in top_repos:
        try:
            langs = await _fetch_languages(org, repo["name"], client)
            for lang, bytes_count in langs.items():
                aggregated[lang] = aggregated.get(lang, 0) + bytes_count
        except httpx.HTTPError:
            continue
    return aggregated


async def _fetch_members_count(
    org: str, client: httpx.AsyncClient
) -> int:
    try:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/members",
            params={"per_page": 1},
            headers=_auth_headers(),
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        link = resp.headers.get("Link", "")
        if not link:
            return len(resp.json())
        for part in link.split(","):
            if 'rel="last"' in part:
                match = re.search(r"page=(\d+)", part)
                if match:
                    return int(match.group(1))
        return 0
    except httpx.HTTPError:
        return 0


async def retrieve_github(company_name: str) -> GitHubData | None:
    org = company_name.lower().replace(" ", "").replace("-", "").replace(".", "")
    start = datetime.now()

    async with httpx.AsyncClient() as client:
        try:
            org_data = await _fetch_org(org, client)
            repos_data = await _fetch_repos(org, client)
        except GitHubRetrievalError:
            raise
        except httpx.HTTPStatusError as e:
            msg = f"GitHub API HTTP {e.response.status_code}: {e.response.text[:200]}"
            raise GitHubRetrievalError(msg) from e
        except httpx.RequestError as e:
            msg = f"GitHub request failed: {e}"
            raise GitHubRetrievalError(msg) from e

        # Rank client-side: the API cannot sort org repos by stars.
        repos_data.sort(
            key=lambda r: r.get("stargazers_count", 0), reverse=True
        )
        top_repos_data = repos_data[:TOP_REPOS_LIMIT]

        top_repos = [
            RepoInfo(
                name=r["name"],
                url=r["html_url"],
                description=r.get("description"),
                stars=r.get("stargazers_count", 0),
                forks=r.get("forks_count", 0),
                language=r.get("language"),
            )
            for r in top_repos_data
        ]

        languages = await _aggregate_languages(org, top_repos_data, client)
        members_count = await _fetch_members_count(org, client)

    elapsed = int((datetime.now() - start).total_seconds() * 1000)
    # Total stars across the whole org, not just the top slice.
    total_stars = sum(r.get("stargazers_count", 0) for r in repos_data)

    return GitHubData(
        metadata=SourceMetadata(
            source="github",
            retrieved_at=datetime.now(),
            elapsed_ms=elapsed,
        ),
        org_name=str(org_data.get("login", org)),
        public_repos=int(org_data.get("public_repos", 0)),
        total_stars=total_stars,
        top_repos=top_repos,
        languages=languages,
        contributors_count=members_count,
    )
