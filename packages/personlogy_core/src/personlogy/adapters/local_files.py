"""Safe local object storage used until MinIO/S3 is connected."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from personlogy.ports.ingestion import StoredObject
from personlogy.shared.errors import DomainValidationError


class LocalFileStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, object_key: str) -> Path:
        if not object_key.strip():
            raise DomainValidationError("object key is required")
        candidate = (self.root / object_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise DomainValidationError("object key escapes storage root")
        return candidate

    def _put(self, object_key: str, content: bytes) -> StoredObject:
        target = self._resolve(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return StoredObject(
            object_key=object_key,
            size=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
        )

    def _read(self, object_key: str) -> bytes:
        return self._resolve(object_key).read_bytes()

    async def put(self, object_key: str, content: bytes) -> StoredObject:
        return await asyncio.to_thread(self._put, object_key, content)

    async def read(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._read, object_key)
