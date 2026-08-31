"""Persistence contract for safe replay plans and candidate comparisons."""

from typing import Protocol
from uuid import UUID

from personlogy.domain.replay import ReplayComparison, ReplayPlan


class ReplayStore(Protocol):
    async def add_plan(self, plan: ReplayPlan) -> None: ...

    async def get_plan(self, plan_id: UUID) -> ReplayPlan | None: ...

    async def save_plan(self, plan: ReplayPlan) -> None: ...

    async def add_comparison(self, comparison: ReplayComparison) -> None: ...

    async def get_comparison(self, comparison_id: UUID) -> ReplayComparison | None: ...

    async def list_comparisons(
        self, plan_id: UUID, *, limit: int = 100
    ) -> list[ReplayComparison]: ...


__all__ = ["ReplayStore"]
