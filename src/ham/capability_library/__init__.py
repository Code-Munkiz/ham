"""Per-project HAM Capability Library (saved catalog references) — on-disk v1 + audit."""

from __future__ import annotations

from src.ham.capability_library.schema import (
    SCHEMA_VERSION,
    CapabilityLibraryIndex,
    LibraryEntry,
)
from src.ham.capability_library.store import (
    CapabilityLibraryWriteConflictError,
    SaveResult,
    read_capability_library,
    remove_entry,
    reorder_entries,
    revision_for_index,
    save_entry,
)

__all__ = [
    "SCHEMA_VERSION",
    "CapabilityLibraryIndex",
    "LibraryEntry",
    "CapabilityLibraryWriteConflictError",
    "SaveResult",
    "read_capability_library",
    "remove_entry",
    "reorder_entries",
    "revision_for_index",
    "save_entry",
]
