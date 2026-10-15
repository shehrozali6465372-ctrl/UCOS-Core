"""L02 orchestration for evidence collection; no provider or database SDK is owned here."""

from ucos_core.layers.l02_research.contracts import ResearchRequest, ResearchResult, ResearchStatus
from ucos_core.layers.l02_research.ports import (
    ResearchProviderError,
    ResearchRepositoryPort,
    ResearchSourcePort,
)


class ResearchService:
    def __init__(self, *, source: ResearchSourcePort, repository: ResearchRepositoryPort) -> None:
        self._source = source
        self._repository = repository

    async def run(self, request: ResearchRequest) -> ResearchResult:
        # Check durable storage first so an external result is not collected if it cannot be saved.
        await self._repository.ensure_ready()
        try:
            observations = list(
                await self._source.search(request.query, max_results=request.max_results)
            )
        except ResearchProviderError as error:
            # Provider adapters normalize expected failures; unexpected faults remain visible.
            result = ResearchResult.failure(
                request,
                error_code=error.code,
                retryable=error.retryable,
            )
        else:
            result = ResearchResult(
                **request.model_dump(exclude={"query", "max_results"}),
                status=ResearchStatus.SUCCEEDED if observations else ResearchStatus.NO_RESULTS,
                query=request.query,
                provenance=observations,
                error_code=None,
                retryable=False,
            )

        await self._repository.save(result)
        return result
