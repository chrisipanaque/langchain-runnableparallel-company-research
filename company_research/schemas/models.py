from datetime import datetime

from pydantic import BaseModel


class SourceMetadata(BaseModel):
    source: str
    retrieved_at: datetime
    elapsed_ms: int


class RepoInfo(BaseModel):
    name: str
    url: str
    description: str | None = None
    stars: int = 0
    forks: int = 0
    language: str | None = None


class WikipediaData(BaseModel):
    metadata: SourceMetadata
    title: str
    summary: str
    url: str
    infobox: dict[str, str] = {}
    categories: list[str] = []


class GitHubData(BaseModel):
    metadata: SourceMetadata
    org_name: str
    public_repos: int = 0
    total_stars: int = 0
    top_repos: list[RepoInfo] = []
    languages: dict[str, float] = {}
    contributors_count: int = 0


class RetrievalError(BaseModel):
    source: str
    error_type: str
    detail: str


class CompanyResearchBundle(BaseModel):
    company_name: str
    retrieved_at: datetime
    wikipedia: WikipediaData | None = None
    github: GitHubData | None = None
    errors: list[RetrievalError] = []
