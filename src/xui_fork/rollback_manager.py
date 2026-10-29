"""Rollback precondition: only verified restore into a new file is available."""

from pathlib import Path

from .backup_manager import verify


def verify_checkpoint(folder: Path) -> dict:
    return verify(folder)
