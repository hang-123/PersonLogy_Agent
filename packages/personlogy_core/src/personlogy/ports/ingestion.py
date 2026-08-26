from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_key: str
    size: int
    content_hash: str


class ObjectStorage(Protocol):
    async def put(self, object_key: str, content: bytes) -> StoredObject: ...

    async def read(self, object_key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ParsedPdfBlock:
    content: str
    locator: dict[str, object]


class PdfParser(Protocol):
    def validate(self, content: bytes) -> int: ...

    def parse(self, content: bytes) -> tuple[ParsedPdfBlock, ...]: ...
