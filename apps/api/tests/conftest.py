import os
import tempfile

os.environ.setdefault("PKS_ENVIRONMENT", "test")
os.environ.setdefault("PKS_STORAGE_BACKEND", "memory")
os.environ.setdefault("PKS_QUEUE_BACKEND", "memory")
os.environ.setdefault("PKS_LLM_PROVIDER", "none")
os.environ.setdefault("PKS_RERANK_PROVIDER", "none")
_files = tempfile.TemporaryDirectory(prefix="personlogy-tests-")
os.environ.setdefault("PKS_PDF_STORAGE_ROOT", _files.name)
