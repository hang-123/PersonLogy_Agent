from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for authoritative PostgreSQL models."""
