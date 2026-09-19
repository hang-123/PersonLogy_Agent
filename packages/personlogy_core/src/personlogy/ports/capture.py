from typing import Protocol
from uuid import UUID

from personlogy.domain.capture.models import (
    CaptureConflict,
    CapturedEvent,
    CaptureSourceIdentity,
    StreamState,
)


class CaptureRepository(Protocol):
    async def get_by_event_id(self, event_id: UUID) -> CapturedEvent | None: ...

    async def get_by_source_identity(
        self, identity: CaptureSourceIdentity
    ) -> CapturedEvent | None: ...

    async def get_by_stream_sequence(
        self, producer_id: str, stream_id: str, sequence: int
    ) -> CapturedEvent | None: ...

    async def add_event(self, event: CapturedEvent) -> None: ...

    async def add_conflict(self, conflict: CaptureConflict) -> None: ...

    async def get_stream_state(self, producer_id: str, stream_id: str) -> StreamState | None: ...

    async def save_stream_state(self, state: StreamState) -> None: ...
