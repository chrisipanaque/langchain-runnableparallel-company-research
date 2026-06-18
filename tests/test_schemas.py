from datetime import datetime

from company_research.schemas.models import (
    CompanyResearchBundle,
    GitHubData,
    RepoInfo,
    RetrievalError,
    SourceMetadata,
    WikipediaData,
)


def test_minimal_bundle() -> None:
    bundle = CompanyResearchBundle(company_name="Acme", retrieved_at=datetime.now())
    assert bundle.company_name == "Acme"
    assert bundle.wikipedia is None
    assert bundle.github is None
    assert bundle.errors == []


def test_bundle_with_all_sources() -> None:
    now = datetime.now()
    wiki = WikipediaData(
        metadata=SourceMetadata(source="wikipedia", retrieved_at=now, elapsed_ms=100),
        title="Acme",
        summary="A company.",
        url="https://en.wikipedia.org/wiki/Acme",
    )
    gh = GitHubData(
        metadata=SourceMetadata(source="github", retrieved_at=now, elapsed_ms=200),
        org_name="acme",
        public_repos=5,
        total_stars=100,
        top_repos=[
            RepoInfo(name="foo", url="https://github.com/acme/foo", stars=50)
        ],
        languages={"Python": 10000},
        contributors_count=10,
    )
    bundle = CompanyResearchBundle(
        company_name="Acme",
        retrieved_at=now,
        wikipedia=wiki,
        github=gh,
        errors=[RetrievalError(source="test", error_type="ValueError", detail="test")],
    )
    assert bundle.wikipedia is not None
    assert bundle.github is not None
    assert len(bundle.errors) == 1
    assert bundle.github.top_repos[0].name == "foo"
    assert bundle.github.languages["Python"] == 10000


def test_json_roundtrip() -> None:
    now = datetime.now()
    bundle = CompanyResearchBundle(company_name="Acme", retrieved_at=now)
    data = bundle.model_dump(mode="json")
    restored = CompanyResearchBundle.model_validate(data)
    assert restored.company_name == "Acme"
    assert restored.retrieved_at == bundle.retrieved_at
