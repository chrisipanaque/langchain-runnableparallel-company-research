import asyncio
import logging

import typer
from pydantic import TypeAdapter

from company_research.__version__ import __version__
from company_research.config import settings
from company_research.pipeline import research_chain
from company_research.schemas.models import CompanyResearchBundle

app = typer.Typer(
    name="company-research",
    help="Research a company using Wikipedia and GitHub data in parallel.",
)

_OUTPUT_ADAPTER = TypeAdapter(CompanyResearchBundle)


def _version_callback(value: bool) -> None:
    if value:
        print(f"company-research v{__version__}")
        raise typer.Exit()


@app.command()
def research(
    company_name: str = typer.Argument(
        ..., help="Name of the company to research"
    ),
    github_token: str = typer.Option(
        "", "--github-token", "-t", envvar="COMPANY_RESEARCH_GITHUB_TOKEN",
        help="GitHub personal access token (or set COMPANY_RESEARCH_GITHUB_TOKEN env var)",
    ),
    timeout: int = typer.Option(
        30, "--timeout", "-T",
        help="Request timeout in seconds",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging",
    ),
    pretty: bool = typer.Option(
        True, "--pretty/--compact",
        help="Pretty-print JSON output",
    ),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback,
        help="Show version and exit",
        is_eager=True,
    ),
) -> None:
    if github_token:
        settings.github_token = github_token
    if timeout:
        settings.request_timeout = timeout
    if verbose:
        settings.verbose = True
        logging.basicConfig(level=logging.DEBUG)

    result = asyncio.run(_run_research(company_name))
    indent = 2 if pretty else None
    print(_OUTPUT_ADAPTER.dump_json(result, indent=indent).decode())


async def _run_research(company_name: str) -> CompanyResearchBundle:
    return await research_chain.ainvoke({"company_name": company_name})


def entry() -> None:
    app()


if __name__ == "__main__":
    entry()
