import httpx
import pytest
import respx

from company_research.exceptions import GitHubRetrievalError, WikipediaRetrievalError
from company_research.retrievers.github import retrieve_github
from company_research.retrievers.wikipedia import retrieve_wikipedia


@pytest.mark.asyncio
async def test_wikipedia_no_results_raises() -> None:
    with respx.mock:
        respx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": "NonExistentCompanyXYZ",
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
        ).mock(
            return_value=httpx.Response(200, json=["NonExistentCompanyXYZ", [], [], []])
        )
        with pytest.raises(WikipediaRetrievalError):
            await retrieve_wikipedia("NonExistentCompanyXYZ")


@pytest.mark.asyncio
async def test_wikipedia_http_error_raises() -> None:
    with respx.mock:
        respx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": "OpenAI",
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
        ).mock(return_value=httpx.Response(500))
        with pytest.raises(WikipediaRetrievalError):
            await retrieve_wikipedia("OpenAI")


@pytest.mark.asyncio
async def test_wikipedia_success() -> None:
    with respx.mock:
        respx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": "OpenAI",
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
        ).mock(
            return_value=httpx.Response(
                200, json=["OpenAI", ["OpenAI"], ["AI company"], ["https://en.wikipedia.org/wiki/OpenAI"]]
            )
        )
        respx.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/OpenAI",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "title": "OpenAI",
                    "extract": "OpenAI is an AI research organization.",
                    "content_urls": {
                        "desktop": {"page": "https://en.wikipedia.org/wiki/OpenAI"}
                    },
                },
            )
        )
        result = await retrieve_wikipedia("OpenAI")
        assert result is not None
        assert result.title == "OpenAI"
        assert "AI research" in result.summary
        assert "wikipedia" in result.url


@pytest.mark.asyncio
async def test_github_org_not_found_raises() -> None:
    with respx.mock:
        respx.get("https://api.github.com/orgs/thisorgdoesnotexist").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(GitHubRetrievalError, match="not found"):
            await retrieve_github("thisorgdoesnotexist")


@pytest.mark.asyncio
async def test_github_http_error_raises() -> None:
    with respx.mock:
        respx.get("https://api.github.com/orgs/acme").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(GitHubRetrievalError):
            await retrieve_github("acme")


@pytest.mark.asyncio
async def test_github_success() -> None:
    with respx.mock:
        respx.get("https://api.github.com/orgs/acme").mock(
            return_value=httpx.Response(
                200,
                json={
                    "login": "acme",
                    "public_repos": 10,
                },
            )
        )
        respx.get(
            "https://api.github.com/orgs/acme/repos",
            params={"sort": "stars", "direction": "desc", "per_page": 10, "page": 1},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "foo",
                        "html_url": "https://github.com/acme/foo",
                        "description": "The foo repo",
                        "stargazers_count": 100,
                        "forks_count": 20,
                        "language": "Python",
                    },
                    {
                        "name": "bar",
                        "html_url": "https://github.com/acme/bar",
                        "description": None,
                        "stargazers_count": 50,
                        "forks_count": 10,
                        "language": "Rust",
                    },
                ],
            )
        )
        respx.get(
            "https://api.github.com/orgs/acme/repos",
            params={"sort": "stars", "direction": "desc", "per_page": 10, "page": 2},
        ).mock(return_value=httpx.Response(200, json=[]))
        respx.get("https://api.github.com/repos/acme/foo/languages").mock(
            return_value=httpx.Response(200, json={"Python": 50000})
        )
        respx.get("https://api.github.com/repos/acme/bar/languages").mock(
            return_value=httpx.Response(200, json={"Rust": 30000})
        )
        respx.get(
            "https://api.github.com/orgs/acme/members",
            params={"per_page": 1},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"login": "alice"},
                    {"login": "bob"},
                    {"login": "charlie"},
                    {"login": "dave"},
                    {"login": "eve"},
                ],
            )
        )
        result = await retrieve_github("acme")
        assert result is not None
        assert result.org_name == "acme"
        assert result.public_repos == 10
        assert len(result.top_repos) == 2
        assert result.top_repos[0].name == "foo"
        assert result.top_repos[0].stars == 100
        assert result.top_repos[1].language == "Rust"
        assert result.languages["Python"] == 50000
        assert result.languages["Rust"] == 30000
        assert result.contributors_count == 5
