import os

os.environ.setdefault("PKS_ENVIRONMENT", "test")
os.environ.setdefault("PKS_STORAGE_BACKEND", "memory")
os.environ.setdefault("PKS_QUEUE_BACKEND", "memory")
