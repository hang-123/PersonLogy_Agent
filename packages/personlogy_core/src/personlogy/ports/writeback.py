"""Ports used by the controlled knowledge publication workflow."""

from typing import Protocol
from uuid import UUID

from personlogy.domain.writeback.models import WritebackItem, WritebackRecord


class WritebackRepository(Protocol):
    async def add(self, record: WritebackRecord) -> None: ...

    async def get(self, record_id: UUID) -> WritebackRecord | None: ...

    async def get_by_idempotency_key(self, key: str) -> WritebackRecord | None: ...

    async def save(self, record: WritebackRecord) -> None: ...

    async def add_item(self, item: WritebackItem) -> None: ...

    async def list_items(self, record_id: UUID) -> list[WritebackItem]: ...


class WritebackAuthorizer(Protocol):
    async def authorize(
        self, *, project_id: UUID, actor_type: str, actor_id: str | None
    ) -> bool: ...


class SchemaWritebackValidator(Protocol):
    async def validate(
        self, *, namespace: str, version: int, project_id: UUID, candidate_ids: tuple[UUID, ...]
    ) -> None: ...


__all__ = ["SchemaWritebackValidator", "WritebackAuthorizer", "WritebackRepository"]
