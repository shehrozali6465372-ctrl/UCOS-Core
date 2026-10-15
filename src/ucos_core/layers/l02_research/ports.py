"""Ports consumed by L02; concrete security/persistence/provider ownership stays external."""

from collections.abc import Sequence
from typing import Protocol

from ucos_core.layers.l02_research.contracts import (
    ResearchRequest,
    ResearchResult,
    ResearchSourceObservation,
)


class DependencyUnavailable(RuntimeError):
    """Raised when a required adapter has not been configured or cannot be reached."""


class AuthenticationRejected(PermissionError):
    """Raised by the L17 authorization boundary when the caller is not authorized."""


class ResearchProviderError(RuntimeError):
    """Normalized provider failure; raw credentials and provider payloads are not exposed."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ResearchSourcePort(Protocol):
    async def search(
        self, query: str, *, max_results: int
    ) -> Sequence[ResearchSourceObservation]: ...


class ResearchRepositoryPort(Protocol):
    async def ensure_ready(self) -> None: ...

    async def save(self, result: ResearchResult) -> None: ...


class ResearchAuthorizationPort(Protocol):
    async def authorize(self, authorization: str | None, context: ResearchRequest) -> None: ...
