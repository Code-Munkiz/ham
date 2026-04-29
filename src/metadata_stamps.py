"""
metadata_stamps.py — Metadata stamping for rendered prompts.

Provides functionality to stamp rendered prompts with:
- discovered_at timestamp (ISO 8601)
- git_head (full or short hash)
- scan_mode (enum: "full" or "cached")

Stamps are embedded as JSON metadata at the start of rendered output.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ScanMode(str, Enum):
    """Mode for scanning workspace."""
    FULL = "full"
    CACHED = "cached"


@dataclass
class MetadataStamp:
    """Metadata stamp for a rendered prompt."""
    discovered_at: str  # ISO 8601 timestamp
    git_head: str  # Full or short git hash
    scan_mode: ScanMode
    extra: dict[str, Any] = None  # Extra metadata fields
    
    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = {}
    
    def to_json(self) -> str:
        """Convert stamp to JSON string."""
        import json
        return json.dumps({
            "discovered_at": self.discovered_at,
            "git_head": self.git_head,
            "scan_mode": self.scan_mode.value,
            **self.extra,
        })
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetadataStamp":
        """Load stamp from dict."""
        return cls(
            discovered_at=data["discovered_at"],
            git_head=data["git_head"],
            scan_mode=ScanMode(data["scan_mode"]),
            extra=data.get("extra", {}),
        )


def _get_git_head_short(cwd: Path) -> str:
    """
    Get the short git HEAD hash for a directory.
    
    Args:
        cwd: The directory to check for git repo
        
    Returns:
        Short git hash (7 chars) or "no-repo" if not a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "no-repo"


def _get_git_head_full(cwd: Path) -> str:
    """
    Get the full git HEAD hash for a directory.
    
    Args:
        cwd: The directory to check for git repo
        
    Returns:
        Full git hash (40 chars) or "no-repo" if not a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "no-repo"


def create_metadata_stamp(
    cwd: Path,
    scan_mode: ScanMode = ScanMode.FULL,
    git_hash_short: bool = True,
    **extra: Any,
) -> MetadataStamp:
    """
    Create a metadata stamp for the current state.
    
    Args:
        cwd: The current working directory
        scan_mode: The scan mode (full or cached)
        git_hash_short: If True, use short hash (7 chars); else full hash
        **extra: Extra metadata fields
        
    Returns:
        A MetadataStamp instance
        
    Note:
        The discovered_at timestamp is in ISO 8601 format (local time).
        The git_head is the short hash by default for brevity.
    """
    if git_hash_short:
        git_head = _get_git_head_short(cwd)
    else:
        git_head = _get_git_head_full(cwd)
    
    return MetadataStamp(
        discovered_at=datetime.now(timezone.utc).isoformat(),
        git_head=git_head,
        scan_mode=scan_mode,
        extra=extra,
    )


def stamp_rendered_output(
    rendered: str,
    stamp: MetadataStamp,
    comment_style: str = "json",
) -> str:
    """
    Embed metadata stamp into rendered output.
    
    Args:
        rendered: The rendered prompt/output string
        stamp: The MetadataStamp to embed
        comment_style: "json" for top-level JSON block, or "comment" for YAML-like
        
    Returns:
        Stamped output with metadata at the start
        
    Note:
        The stamp is embedded as a JSON block on the first line(s) of output.
        This allows parsers to extract the metadata without affecting the rest
        of the prompt content.
    """
    stamp_json = stamp.to_json()
    
    if comment_style == "json":
        # Place stamp as first line(s) for easy extraction
        return f"{stamp_json}\n\n{rendered}"
    
    # Alternative: embed in comment style
    return f"# {stamp_json}\n\n{rendered}"
