import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.ingestion import (
    ConversationImportService,
    IncomingConversationMessage,
)
from personlogy.application.orchestration import JobService
from personlogy.shared.errors import DomainValidationError


def test_conversation_import_is_message_idempotent(tmp_path: Path) -> None:
    asyncio.run(_test_conversation_import_is_message_idempotent(tmp_path))


async def _test_conversation_import_is_message_idempotent(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    job_service = JobService(factory, SQLiteJobQueue(store, poll_interval_seconds=0.01))
    service = ConversationImportService(factory, job_service)
    messages = (
        IncomingConversationMessage("m-1", "user", "请保持简洁", 0),
        IncomingConversationMessage("m-2", "assistant", "好的", 1, parent_external_id="m-1"),
    )

    first = await service.import_conversation(
        project_name="个人知识",
        project_slug="personal",
        conversation_external_id="conversation-1",
        title="导入测试",
        messages=messages,
    )
    second = await service.import_conversation(
        project_name="个人知识",
        project_slug="personal",
        conversation_external_id="conversation-1",
        title="导入测试",
        messages=messages,
    )

    assert first.conversation_id == second.conversation_id
    assert first.imported_message_count == 2
    assert first.duplicate_message_count == 0
    assert second.imported_message_count == 0
    assert second.duplicate_message_count == 2
    assert first.job.id == second.job.id


def test_conversation_import_rejects_conflicting_message(tmp_path: Path) -> None:
    asyncio.run(_test_conversation_import_rejects_conflicting_message(tmp_path))


async def _test_conversation_import_rejects_conflicting_message(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    service = ConversationImportService(
        factory, JobService(factory, SQLiteJobQueue(store, poll_interval_seconds=0.01))
    )
    await service.import_conversation(
        project_name="个人知识",
        project_slug="personal",
        conversation_external_id="conversation-1",
        title="导入测试",
        messages=(IncomingConversationMessage("m-1", "user", "原始内容", 0),),
    )

    with pytest.raises(DomainValidationError, match="conflicts"):
        await service.import_conversation(
            project_name="个人知识",
            project_slug="personal",
            conversation_external_id="conversation-1",
            title="导入测试",
            messages=(IncomingConversationMessage("m-1", "user", "被篡改内容", 0),),
        )
