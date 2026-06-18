from datetime import datetime
from operator import itemgetter
from typing import Any

from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from company_research.retrievers.github import retrieve_github
from company_research.retrievers.wikipedia import retrieve_wikipedia
from company_research.schemas.models import (
    CompanyResearchBundle,
    GitHubData,
    RetrievalError,
    WikipediaData,
)


async def _safe_wiki(company_name: str) -> dict[str, Any]:
    try:
        data = await retrieve_wikipedia(company_name)
        return {"wikipedia": data, "wiki_error": None}
    except Exception as e:
        return {
            "wikipedia": None,
            "wiki_error": RetrievalError(
                source="wikipedia",
                error_type=type(e).__name__,
                detail=str(e),
            ),
        }


async def _safe_github(company_name: str) -> dict[str, Any]:
    try:
        data = await retrieve_github(company_name)
        return {"github": data, "github_error": None}
    except Exception as e:
        return {
            "github": None,
            "github_error": RetrievalError(
                source="github",
                error_type=type(e).__name__,
                detail=str(e),
            ),
        }


def _aggregate(results: dict[str, Any]) -> CompanyResearchBundle:
    company_name: str = results["company_name"]
    wiki_result: dict[str, Any] = results["wiki"]
    gh_result: dict[str, Any] = results["gh"]

    wikipedia: WikipediaData | None = wiki_result.get("wikipedia")
    github: GitHubData | None = gh_result.get("github")

    errors: list[RetrievalError] = []
    if wiki_err := wiki_result.get("wiki_error"):
        errors.append(wiki_err)
    if gh_err := gh_result.get("github_error"):
        errors.append(gh_err)

    return CompanyResearchBundle(
        company_name=company_name,
        retrieved_at=datetime.now(),
        wikipedia=wikipedia,
        github=github,
        errors=errors,
    )


research_chain = (
    RunnablePassthrough.assign(
        wiki=itemgetter("company_name") | RunnableLambda(_safe_wiki),  # type: ignore[arg-type]
        gh=itemgetter("company_name") | RunnableLambda(_safe_github),  # type: ignore[arg-type]
    )
    | RunnableLambda(_aggregate)
)
