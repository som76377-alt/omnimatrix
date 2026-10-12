"""Persistence adapters for durable Omnitrix execution state."""

from core.persistence.sqlite_journal import SQLiteJournal

__all__ = ["SQLiteJournal"]
