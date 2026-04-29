"""
relevance_scoring.py — Context-based relevance scoring for file discovery.

Provides weighted scoring for files based on:
1. File type priority (config files, instructions, core logic get higher scores)
2. File location hierarchy (root config, src/, docs/ rankings)
3. File size/importance patterns
4. Recent modification time (recency decay)
5. Matching against user query terms
6. Session hot path tracking (access frequency)

This module enables smart, filtered context discovery instead of full-repo scans,
improving both performance and relevance for agent prompts.
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import FileEntry from memory_heist for type hints
from src.memory_heist import FileEntry


# =============================================================================
# Constants for File Type and Location Priorities
# =============================================================================

# High-priority file types (get +0.25 to +0.35 bonus when normalized)
HIGH_PRIORITY_FILETYPES = frozenset({
    # Config files
    "settings.json", "config.json", "package.json", "pyproject.toml",
    "setup.py", "requirements.txt", "Pipfile", "environment.yml",
    ".env", ".env.example", ".gitignore",
    # Instructions
    "SWARM.md", "AGENTS.md", "readme.md", "README.md",
    "instructions.md", "CONTRIBUTING.md", "ARCHITECTURE.md",
    # Core code
    "main.py", "app.py", "cli.py", "index.ts", "handler.py",
    "__init__.py", "registry.py", "manager.py",
    # API/Service definitions
    "api.py", "router.py", "routes.py", "endpoints.py",
    "schema.py", "models.py", "types.py",
})

# Medium-priority file types (get +0.10 to +0.15 bonus)
MEDIUM_PRIORITY_FILETYPES = frozenset({
    # Documentation
    "*.md", "*.rst", "*.txt",
    # Test files
    "test_*.py", "test_*.ts", "*_test.py", "*_test.ts",
    # Build/format config
    "*.prettierrc", "*.eslintrc", ".babelrc",
})

# Location priorities (weight scores)
LOCATION_WEIGHTS = {
    "root_config": 1.5,  # .ham/settings.json, project root configs
    "root_instruction": 1.4,  # Root SWARM.md, AGENTS.md, README.md
    "src": 1.3,  # src/ directory
    "src_core": 1.6,  # src files matching core names
    "docs": 1.2,  # docs/ directory
    "scripts": 1.1,  # scripts/ directory
    "tests": 1.0,  # test/ or tests/ directories
    "normal": 1.0,  # Default location weight
}

# File type name to location category
LOCATION_PATTERNS = {
    "root_config": [
        ".ham/settings.json", ".ham/settings.local.json",
        ".ham.json", "config.json", "settings.json",
    ],
    "root_instruction": [
        "SWARM.md", "AGENTS.md", "README.md", "readme.md",
    ],
    "src_core": [
        "main.py", "app.py", "cli.py", "memory_heist.py",
        "swarm_agency.py", "droid_executor.py", "api.py",
    ],
    "src": ["src/"],
    "docs": ["docs/"],
    "scripts": ["scripts/"],
    "tests": ["tests/", "test/", "testing/"],
}

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FileRelevanceScore:
    """Score for a single file based on relevance factors."""
    
    file_path: str
    file_mod_time: datetime
    score: float  # Normalized score 0.0-1.0 after ranking
    raw_score: float  # Unnormalized raw score
    tier: str  # "hot", "recent", "baseline"
    breakdown: dict[str, float]
    
    def __post_init__(self):
        # Ensure breakdown has proper float values
        for key in self.breakdown:
            if not isinstance(self.breakdown[key], (int, float)):
                self.breakdown[key] = float(self.breakdown[key])
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "score": round(self.score, 4),
            "raw_score": round(self.raw_score, 2),
            "tier": self.tier,
            "breakdown": {
                key: round(val, 2) for key, val in self.breakdown.items()
            },
        }


@dataclass
class RelevanceConfig:
    """Configuration for relevance scoring."""
    
    # Priority weights
    filetype_weight: float = 0.30  # Impact of file type on score
    location_weight: float = 0.25  # Impact of location on score
    size_weight: float = 0.10  # Impact of file size on score
    recent_weight: float = 0.15  # Impact of recency on score
    query_weight: float = 0.10  # Impact of query matching on score
    hot_weight: float = 0.10  # Impact of hot path tracking on score
    
    # Thresholds
    recent_threshold_days: int = 7
    max_results: int = 50
    enable_hot_tracking: bool = True
    
    # Size boundaries (bytes)
    optimal_min_size: int = 100  # Skip tiny files under this
    optimal_max_size: int = 500_000  # Downweight very large files
    optimal_core_size: tuple[int, int] = (500, 50_000)  # Sweet spot for core files
    
    def to_dict(self) -> dict:
        """Serialize config to dictionary."""
        return {
            "filetype_weight": self.filetype_weight,
            "location_weight": self.location_weight,
            "size_weight": self.size_weight,
            "recent_weight": self.recent_weight,
            "query_weight": self.query_weight,
            "hot_weight": self.hot_weight,
            "recent_threshold_days": self.recent_threshold_days,
            "max_results": self.max_results,
            "enable_hot_tracking": self.enable_hot_tracking,
            "optimal_min_size": self.optimal_min_size,
            "optimal_max_size": self.optimal_max_size,
            "optimal_core_size": self.optimal_core_size,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RelevanceConfig":
        """Create config from dictionary."""
        return cls(
            filetype_weight=data.get("filetype_weight", cls.filetype_weight),
            location_weight=data.get("location_weight", cls.location_weight),
            size_weight=data.get("size_weight", cls.size_weight),
            recent_weight=data.get("recent_weight", cls.recent_weight),
            query_weight=data.get("query_weight", cls.query_weight),
            hot_weight=data.get("hot_weight", cls.hot_weight),
            recent_threshold_days=data.get("recent_threshold_days", cls.recent_threshold_days),
            max_results=data.get("max_results", cls.max_results),
            enable_hot_tracking=data.get("enable_hot_tracking", cls.enable_hot_tracking),
            optimal_min_size=data.get("optimal_min_size", cls.optimal_min_size),
            optimal_max_size=data.get("optimal_max_size", cls.optimal_max_size),
            optimal_core_size=data.get("optimal_core_size", cls.optimal_core_size),
        )


@dataclass
class RelevanceMetrics:
    """Metrics for relevance filtering phase."""
    total_candidates: int = 0
    filtered_count: int = 0
    filtering_duration: float = 0.0
    enable_hot_tracking: bool = True
    tier_distribution: dict[str, int] = field(default_factory=dict)
    avg_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-serializable dict."""
        return {
            "total_candidates": self.total_candidates,
            "filtered_count": self.filtered_count,
            "filtering_duration_sec": round(self.filtering_duration, 4),
            "enable_hot_tracking": self.enable_hot_tracking,
            "tier_distribution": self.tier_distribution,
            "avg_score": round(self.avg_score, 4),
            "max_score": round(self.max_score, 4),
            "min_score": round(self.min_score, 4),
        }


@dataclass
class SessionHistory:
    """History entry for file access tracking."""
    
    file_path: str
    access_type: str  # "mentioned", "accessed", "edited"
    timestamp: float
    
    @property
    def is_recent(self) -> bool:
        """Check if access was within the last hour."""
        return (time.time() - self.timestamp) < 3600
    
    @property
    def is_very_recent(self) -> bool:
        """Check if access was within the last minute."""
        return (time.time() - self.timestamp) < 60


def get_session_history(session: "SessionMemory") -> list[SessionHistory]:
    """
    Extract session history from SessionMemory object.
    
    Access patterns tracked:
    - Files accessed during tool execution
    - Files mentioned in user queries
    - Files in assistant responses
    
    Args:
        session: SessionMemory object (or None)
        
    Returns:
        List of SessionHistory entries, or empty list if no session
    """
    if session is None or not session.messages:
        return []
    
    history: list[SessionHistory] = []
    now = time.time()
    for msg in session.messages:
        # Extract file mentions from message content
        files = SessionMemory._extract_key_files([msg])
        for file_path in files:
            history.append(SessionHistory(
                file_path=file_path,
                access_type="mentioned",
                timestamp=now,
            ))
    return history


from src.memory_heist import SessionMemory


# =============================================================================
# Type & Location Scoring Functions
# =============================================================================

def get_location_category(file_path: str) -> tuple[str, float]:
    """
    Determine file location category and weight.
    
    Args:
        file_path: Relative or absolute file path
        
    Returns:
        Tuple of (category_name, weight_multiplier)
    """
    path_lower = file_path.lower()
    rel_path = Path(file_path)
    parts = path_lower.split('/')
    
    # Check for root config files first
    if rel_path.name in LOCATION_PATTERNS["root_config"]:
        return "root_config", LOCATION_WEIGHTS["root_config"]
    
    # Check for root instruction files
    if rel_path.name in LOCATION_PATTERNS["root_instruction"]:
        return "root_instruction", LOCATION_WEIGHTS["root_instruction"]
    
    # Check src/ subdirectories
    if len(parts) >= 2 and parts[0] == "src":
        core_names = LOCATION_PATTERNS["src_core"]
        if rel_path.name.split(".")[0].lower() in [n.split(".")[0].lower() for n in core_names]:
            return "src_core", LOCATION_WEIGHTS["src_core"]
        return "src", LOCATION_WEIGHTS["src"]
    
    # Check docs/
    if len(parts) >= 1 and parts[0] == "docs":
        return "docs", LOCATION_WEIGHTS["docs"]
    
    # Check scripts/
    if len(parts) >= 1 and parts[0] == "scripts":
        return "scripts", LOCATION_WEIGHTS["scripts"]
    
    # Check tests/
    for test_prefix in ["tests", "test", "testing"]:
        if parts[0] == test_prefix:
            return "tests", LOCATION_WEIGHTS["tests"]
    
    return "normal", LOCATION_WEIGHTS["normal"]


def get_filetype_priority(file_path: str) -> float:
    """
    Determine file type priority score (0.0-1.0).
    
    High-priority files get higher base scores.
    
    Args:
        file_path: File path to evaluate
        
    Returns:
        Priority score between 0.0 (low) and 1.0 (high)
    """
    rel_path = Path(file_path)
    filename = rel_path.name.lower()
    
    # Exact matches with high priority files
    if filename in HIGH_PRIORITY_FILETYPES:
        return 1.0
    
    # Pattern matching
    if any(filename.endswith(ext) for ext in [".json", ".toml", ".yaml", ".yml"]):
        if any(p in filename for p in ["config", "settings", "package", "environment"]):
            return 0.85
    
    if any(filename.endswith(p) for p in ["swarm.md", "agents.md", "readme.md", "architecture.md"]):
        return 0.95
    
    if rel_path.suffix.lower() == ".md":
        return 0.7
    
    if any(filename.startswith("test_") or filename.endswith("_test.py") or filename.endswith("_test.ts") for _ in [1]):
        return 0.6
    
    # Code files
    if rel_path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return 0.75
    
    # Documentation
    if rel_path.suffix.lower() in {".md", ".rst", ".txt"}:
        return 0.65
    
    return 0.5


def get_size_score(file_size: int, location_category: str) -> float:
    """
    Score file based on size patterns.
    
    Very small files (<100 bytes) are filtered out.
    Larger files get moderate size scores.
    Core files in sweet spot get higher scores.
    
    Args:
        file_size: File size in bytes
        location_category: Location category from get_location_category
        
    Returns:
        Size score between 0.0 (poor size) and 1.0 (optimal size)
    """
    # Skip tiny files
    if file_size < 50:
        return 0.0
    
    core_configs = {"root_config", "src_core"}
    
    if location_category in core_configs:
        # Core files: prefer medium-sized code
        min_size, max_size = 500, 50_000
        if file_size >= min_size and file_size <= max_size:
            return 1.0
        elif file_size < min_size:
            # Small core files are still useful
            return 0.5 + (file_size / min_size) * 0.5
        else:
            # Gradually decrease for very large core files
            return max(0.3, 1.0 - (file_size - max_size) / (500_000 - max_size))
    else:
        # Normal files
        if file_size >= 100 and file_size <= 50_000:
            return 1.0
        elif file_size < 100:
            return 0.3
        else:
            return max(0.4, 1.0 - math.log10(file_size / 50_000) * 0.2)


# =============================================================================
# Recency Scoring Functions
# =============================================================================

def calculate_recent_score(file_path: str, threshold_days: int = 7) -> float:
    """
    Score files based on modification recency.
    
    Files modified more recently get higher scores, with exponential decay.
    
    Args:
        file_path: Path to the file
        threshold_days: Days threshold for scoring
        
    Returns:
        Score between 0.0 (old) and 1.0 (modified today)
    """
    try:
        stat = Path(file_path).stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        now = datetime.now()
        delta = now - mod_time
        days_old = delta.total_seconds() / (24 * 3600)
        
        # Exponential decay: score decreases as file gets older
        if days_old <= 0:
            return 1.0  # Modified today
        
        # Normalize to 0-1 scale
        max_score = math.exp(-math.log(2) * days_old / max(threshold_days, 1))
        return max(0.0, min(1.0, max_score))
        
    except (OSError, ValueError):
        # File doesn't exist or can't be read - return 0.0
        return 0.0


# =============================================================================
# Query Scoring Functions
# =============================================================================

def calculate_query_score(file_path: str, user_query: str) -> float:
    """
    Score files based on user query term matching.
    
    Checks multiple matching surfaces:
    - Filename (exact and substring)
    - Directory path
    - File content (first 1000 chars)
    
    Args:
        file_path: Path to the file
        user_query: User's search query
        
    Returns:
        Score between 0.0 (no match) and 1.0 (strong match)
    """
    if not user_query or not file_path:
        return 0.0
    
    query_lower = user_query.lower()
    query_terms = query_lower.split()
    
    if not query_terms:
        return 0.0
    
    file_path_lower = file_path.lower()
    path_parts = file_path_lower.split("/")
    
    score = 0.0
    max_possible = 0.0
    
    # --- Filename matching ---
    max_possible += 0.4
    filename = Path(file_path).name.lower()
    
    for term in query_terms:
        # Exact filename match
        if filename == term:
            score += 0.4
            break
        # Filename contains term
        elif term in filename:
            score += 0.2
        # File extension contains term
        if Path(file_path).suffix.lower() == f".{term}":
            score += 0.2
    
    # --- Directory/Path matching ---
    max_possible += 0.3
    
    for term in query_terms:
        # Directory contains term
        for part in path_parts:
            if term in part:
                score += 0.1
                break
    
    # --- Content matching (if file is readable) ---
    max_possible += 0.3
    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            # Read only first 1000 chars for performance
            content = path.read_text(encoding="utf-8", errors="ignore")[:1000].lower()
            
            term_count = 0
            for term in query_terms:
                if term in content:
                    term_count += 1
            
            # Score based on number of terms found
            score += min(0.3, (term_count / len(query_terms)) * 0.3)
            
    except (OSError, UnicodeDecodeError):
        pass  # File not readable, skip content matching
    
    # Normalize to 0-1 scale
    if max_possible > 0:
        normalized = (score / max_possible)
        return min(1.0, normalized)
    
    return 0.0


# =============================================================================
# Hot Path Scoring Functions
# =============================================================================

def calculate_hot_score(file_path: str, session_history: list[SessionHistory]) -> float:
    """
    Score files based on session access frequency.
    
    Files accessed more frequently during the session get higher scores.
    Recent accesses weigh more than older ones.
    
    Args:
        file_path: Path to the file
        session_history: List of session history entries
        
    Returns:
        Score between 0.0 (never accessed) and 1.0 (frequently accessed recently)
    """
    if not session_history:
        return 0.0
    
    # Normalize file paths for comparison
    file_path_lower = Path(file_path).name.lower()
    
    accesses: list[SessionHistory] = []
    
    for entry in session_history:
        entry_lower = Path(entry.file_path).name.lower()
        
        # Match by filename
        if entry_lower == file_path_lower:
            accesses.append(entry)
    
    if not accesses:
        return 0.0
    
    total_score = 0.0
    
    for access in accesses:
        # Calculate recency weight (0.2 to 1.0)
        if access.is_very_recent:
            weight = 1.0
        elif access.is_recent:
            weight = 0.7
        else:
            weight = 0.4
        
        total_score += weight
    
    # Normalize: assume 5 accesses in session = full score
    normalized = (total_score / min(5, len(accesses)))
    return min(1.0, normalized)


# =============================================================================
# Main Scoring Functions
# =============================================================================

@dataclass
class ScoringResult:
    """Result of a scoring calculation."""
    
    file_path: str
    filetype_score: float
    location_score: float
    size_score: float
    recent_score: float
    query_score: float
    hot_score: float
    total_score: float
    tier: str
    breakdown: Dict[str, float]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "score": round(self.total_score, 4),
            "tier": self.tier,
            "breakdown": {
                "filetype": round(self.filetype_score, 4),
                "location": round(self.location_score, 4),
                "size": round(self.size_score, 4),
                "recent": round(self.recent_score, 4),
                "query": round(self.query_score, 4),
                "hot": round(self.hot_score, 4),
            },
        }


def calculate_combined_score(
    entry: "FileEntry",
    user_query: Optional[str] = None,
    session_history: Optional[List[SessionHistory]] = None,
    config: Optional[RelevanceConfig] = None,
) -> ScoringResult:
    """
    Combine all scoring factors and assign tier.
    
    This is the main scoring function that integrates:
    - File type priority
    - Location hierarchy
    - File size/importance patterns
    - Recent modification score
    - Query matching score
    - Hot path tracking score
    
    Args:
        entry: FileEntry from scan_workspace
        user_query: User's query for relevance matching
        session_history: Session access history
        config: Configuration for scoring
        
    Returns:
        ScoringResult with total score and tier assignment
    """
    if config is None:
        config = RelevanceConfig()
    
    if session_history is None:
        session_history = []
    
    # Handle both FileEntry objects and string file paths
    if isinstance(entry, str):
        file_path = entry
        # Create a minimal FileEntry-like object for size access
        import os
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
    else:
        file_path = str(entry.relative)
        size = entry.size
    
    # Calculate individual scores (all 0-1 scale)
    filetype_score = get_filetype_priority(file_path)
    location_category, location_multiplier = get_location_category(file_path)
    location_score = min(1.0, (location_category != "normal") * 0.75 + 0.25)  # 0.25-1.0
    size_score = get_size_score(size, location_category)
    recent_score = calculate_recent_score(file_path, config.recent_threshold_days)
    query_score = calculate_query_score(file_path, user_query or "")
    
    hot_score = 0.0
    if config.enable_hot_tracking:
        hot_score = calculate_hot_score(file_path, session_history)
    
    # Weighted combination
    total_score = (
        config.filetype_weight * filetype_score +
        config.location_weight * location_score +
        config.size_weight * size_score +
        config.recent_weight * recent_score +
        config.query_weight * query_score +
        config.hot_weight * hot_score
    )
    
    # Determine tier based on scores
    if hot_score >= 0.5 or (query_score >= 0.7 and recent_score >= 0.5):
        tier = "hot"
    elif recent_score >= 0.5 or filetype_score >= 0.8:
        tier = "recent"
    else:
        tier = "baseline"
    
    breakdown = {
        "filetype": filetype_score,
        "location": location_score,
        "size": size_score,
        "recent": recent_score,
        "query": query_score,
        "hot": hot_score,
    }
    
    return ScoringResult(
        file_path=file_path,
        filetype_score=filetype_score,
        location_score=location_score,
        size_score=size_score,
        recent_score=recent_score,
        query_score=query_score,
        hot_score=hot_score,
        total_score=total_score,
        tier=tier,
        breakdown=breakdown,
    )


def score_file_entry(
    entry: "FileEntry",
    user_query: Optional[str] = None,
    session_history: Optional[List[SessionHistory]] = None,
    config: Optional[RelevanceConfig] = None,
) -> FileRelevanceScore:
    """
    Score a FileEntry from the workspace scan.
    
    Helper function to score individual file entries from scan_workspace().
    
    Args:
        entry: FileEntry from scan_workspace
        user_query: User's query
        session_history: Session access history
        config: Scoring configuration
        
    Returns:
        FileRelevanceScore with full breakdown
    """
    result = calculate_combined_score(
        entry,
        user_query=user_query,
        session_history=session_history,
        config=config,
    )
    
    from datetime import datetime
    
    return FileRelevanceScore(
        file_path=str(entry.relative),
        file_mod_time=datetime.fromtimestamp(entry.mtime),
        score=result.total_score,
        raw_score=result.total_score,
        tier=result.tier,
        breakdown=result.breakdown,
    )


# =============================================================================
# Main Filter Functions
# =============================================================================

def filter_by_relevance(
    files: List["FileEntry"],
    user_query: Optional[str] = None,
    config: Optional[RelevanceConfig] = None,
    session_memory: Optional["SessionMemory"] = None,
) -> List[FileRelevanceScore]:
    """
    Main entry point for relevance-based file filtering.
    
    Args:
        files: List of FileEntry from scan_workspace
        user_query: User's query for relevance matching
        config: Scoring configuration
        session_memory: SessionMemory for hot path tracking
        
    Returns:
        List of FileRelevanceScore sorted by total score (descending)
        
    Example:
        >>> from src.memory_heist import scan_workspace
        >>> files = scan_workspace(Path.cwd())
        >>> scores = filter_by_relevance(files, user_query="context discovery")
        >>> len(scores) <= 50
        True
    """
    if config is None:
        config = RelevanceConfig()
    
    if session_memory is None:
        session_memory = SessionMemory()
    
    # Extract session history
    session_history = get_session_history(session_memory)
    
    # Score all files
    scored: List[ScoringResult] = []
    for entry in files:
        result = calculate_combined_score(
            entry,
            user_query=user_query,
            session_history=session_history,
            config=config,
        )
        scored.append(result)
    
    # Sort by total score (descending)
    scored.sort(key=lambda r: r.total_score, reverse=True)
    
    # Take top N
    top_files = scored[:config.max_results]
    
    # Convert to FileRelevanceScore format
    results: List[FileRelevanceScore] = []
    for result in top_files:
        # Get file modification time - handle both relative and absolute paths
        file_path_str = result.file_path
        if not Path(file_path_str).is_absolute():
            # If relative, we need the project root to get mtime
            # For now, skip files we can't stat (they'll have stale timestamps)
            try:
                mtime = Path(file_path_str).stat().st_mtime
            except FileNotFoundError:
                mtime = time.time()  # Use current time as fallback
        else:
            mtime = Path(file_path_str).stat().st_mtime
        
        results.append(FileRelevanceScore(
            file_path=result.file_path,
            file_mod_time=datetime.fromtimestamp(mtime),
            score=result.total_score,
            raw_score=result.total_score,
            tier=result.tier,
            breakdown=result.breakdown,
        ))
    
    return results


def filter_by_relevance_async(
    context: "ProjectContext",
    user_query: Optional[str] = None,
    config: Optional[RelevanceConfig] = None,
    session_memory: Optional["SessionMemory"] = None,
    use_relevance_filtering: bool = True,
) -> tuple[List[FileRelevanceScore], dict]:
    """
    Async-compatible wrapper with metadata return.
    
    Args:
        context: ProjectContext
        user_query: User query
        config: Scoring config
        session_memory: Session memory
        use_relevance_filtering: Whether to use filtering or return all
        
    Returns:
        Tuple of (filtered_results, metadata_dict)
    """
    from src.memory_heist import scan_workspace, FileEntry
    
    if config is None:
        config = RelevanceConfig()
    
    if session_memory is None:
        session_memory = SessionMemory()
    
    # Use the files already available from context scan
    # Note: We need to get files from context - in current design, we re-scan
    
    # Re-scan to get fresh FileEntry objects
    relevant_extensions = frozenset({
        ".py", ".md", ".json", ".yaml", ".yml", ".toml", 
        ".ts", ".tsx", ".js", ".jsx"
    })
    
    files = list(scan_workspace(
        context.cwd,
        max_files=10000,
        extensions=relevant_extensions,
    ))
    
    total_candidates = len(files)
    
    if not use_relevance_filtering:
        # Return all files with basic scoring
        results = [
            FileRelevanceScore(
                file_path=str(f.relative),
                file_mod_time=datetime.fromtimestamp(f.mtime),
                score=0.0,
                raw_score=0.0,
                tier="baseline",
                breakdown={
                    "filetype": 0.5,
                    "location": 0.5,
                    "size": 0.5,
                    "recent": 0.5,
                    "query": 0.0,
                    "hot": 0.0,
                },
            )
            for f in files[:config.max_results]
        ]
        
        metadata = {
            "total_candidates": total_candidates,
            "filtered_count": len(results),
            "use_relevance_filtering": False,
        }
        
        return results, metadata
    
    # Use relevance filtering
    results = filter_by_relevance(
        files,
        user_query=user_query,
        config=config,
        session_memory=session_memory,
    )
    
    # Calculate score distribution for metadata
    if results:
        score_stats = {
            "max_score": max(r.score for r in results),
            "min_score": min(r.score for r in results),
            "avg_score": sum(r.score for r in results) / len(results),
            "tier_counts": {
                "hot": sum(1 for r in results if r.tier == "hot"),
                "recent": sum(1 for r in results if r.tier == "recent"),
                "baseline": sum(1 for r in results if r.tier == "baseline"),
            },
        }
    else:
        score_stats = {
            "max_score": 0.0,
            "min_score": 0.0,
            "avg_score": 0.0,
            "tier_counts": {"hot": 0, "recent": 0, "baseline": 0},
        }
    
    metadata = {
        "total_candidates": total_candidates,
        "filtered_count": len(results),
        "use_relevance_filtering": True,
        "config": config.to_dict(),
        "score_stats": score_stats,
    }
    
    return results, metadata
