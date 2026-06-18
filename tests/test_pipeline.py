from datetime import datetime
from unittest.mock import patch

from company_research.pipeline import _aggregate
from company_research.schemas.models import (
    GitHubData,
    RetrievalError,
    SourceMetadata,
    WikipediaData,
)


async def test_safe_wiki_catches_errors() -> None:
    from company_research.pipeline import _safe_wiki

    with patch("company_research.pipeline.retrieve_wikipedia", side_effect=ValueError("boom")):
        result = await _safe_wiki("Acme")
    assert result["wikipedia"] is None
    assert result["wiki_error"] is not None
    assert result["wiki_error"].source == "wikipedia"
    assert "boom" in result["wiki_error"].detail


async def test_safe_wiki_returns_data() -> None:
    from company_research.pipeline import _safe_wiki

    now = datetime.now()
    wiki_data = WikipediaData(
        metadata=SourceMetadata(source="wikipedia", retrieved_at=now, elapsed_ms=50),
        title="Acme",
        summary="summary",
        url="https://en.wikipedia.org/wiki/Acme",
    )
    with patch("company_research.pipeline.retrieve_wikipedia", return_value=wiki_data):
        result = await _safe_wiki("Acme")
    assert result["wikipedia"] is not None
    assert result["wikipedia"].title == "Acme"
    assert result["wiki_error"] is None


async def test_safe_github_catches_errors() -> None:
    from company_research.pipeline import _safe_github

    with patch("company_research.pipeline.retrieve_github", side_effect=ValueError("not found")):
        result = await _safe_github("Acme")
    assert result["github"] is None
    assert result["github_error"] is not None
    assert result["github_error"].source == "github"


async def test_safe_github_returns_data() -> None:
    from company_research.pipeline import _safe_github

    now = datetime.now()
    gh_data = GitHubData(
        metadata=SourceMetadata(source="github", retrieved_at=now, elapsed_ms=100),
        org_name="acme",
        public_repos=5,
    )
    with patch("company_research.pipeline.retrieve_github", return_value=gh_data):
        result = await _safe_github("Acme")
    assert result["github"] is not None
    assert result["github"].org_name == "acme"
    assert result["github_error"] is None


def test_aggregate_both_failed() -> None:
    bundle = _aggregate({
        "company_name": "Acme",
        "wiki": {
            "wikipedia": None,
            "wiki_error": RetrievalError(
                source="wikipedia", error_type="NotFound", detail="not found"
            ),
        },
        "gh": {
            "github": None,
            "github_error": RetrievalError(
                source="github", error_type="NotFound", detail="org not found"
            ),
        },
    })
    assert bundle.company_name == "Acme"
    assert bundle.wikipedia is None
    assert bundle.github is None
    assert len(bundle.errors) == 2


def test_aggregate_partial_success() -> None:
    now = datetime.now()
    wiki_data = WikipediaData(
        metadata=SourceMetadata(source="wikipedia", retrieved_at=now, elapsed_ms=50),
        title="Acme",
        summary="summary",
        url="https://en.wikipedia.org/wiki/Acme",
    )
    bundle = _aggregate({
        "company_name": "Acme",
        "wiki": {"wikipedia": wiki_data, "wiki_error": None},
        "gh": {
            "github": None,
            "github_error": RetrievalError(
                source="github", error_type="NotFound", detail="org not found"
            ),
        },
    })
    assert bundle.wikipedia is not None
    assert bundle.github is None
    assert len(bundle.errors) == 1
    assert bundle.errors[0].source == "github"
