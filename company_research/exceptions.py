class RetrievalError(Exception):
    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"[{source}] {detail}")


class WikipediaRetrievalError(RetrievalError):
    def __init__(self, detail: str) -> None:
        super().__init__(source="wikipedia", detail=detail)


class GitHubRetrievalError(RetrievalError):
    def __init__(self, detail: str) -> None:
        super().__init__(source="github", detail=detail)
