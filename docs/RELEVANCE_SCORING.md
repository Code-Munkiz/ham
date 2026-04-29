# Relevance Filtering for Context Discovery

## Overview

This module implements smart, weighted relevance filtering for file discovery, replacing full-repo scans with targeted filtering based on three key factors:

1. **Recent file modifications** - Files modified recently get higher scores
2. **User prompt term matching** - Files matching the user's query get priority
3. **Hot path tracking** - Files accessed frequently during the session gain prominence

This approach significantly improves both performance and relevance for agent prompts by filtering down from thousands of candidate files to the most relevant subset.

## Module Structure

### `src/context/relevance_scoring.py`

Main scoring module with the following components:

#### Data Classes

- **`FileRelevanceScore`** - Score for a single file
  - `file_path`: Relative path to the file
  - `file_mod_time`: Last modification timestamp
  - `score`: Total relevance score (float)
  - `tier`: One of "hot", "recent", or "baseline"
  - `breakdown`: Dict with individual component scores

- **`RelevanceConfig`** - Configuration for scoring
  - `recent_threshold_days`: Days threshold for recency score (default: 7)
  - `query_term_weight`: Max weight for query matching (default: 100.0)
  - `recent_file_weight`: Max weight for recent files (default: 300.0)
  - `hot_file_weight`: Max weight for hot files (default: 500.0)
  - `baseline_weight`: Weight for older files (default: 100.0)
  - `max_results`: Maximum files to return (default: 50)
  - `enable_hot_tracking`: Whether to track file access frequency

- **`SessionHistory`** - Access history entry
  - `file_path`: File that was accessed/mentioned
  - `access_type`: Type of access ("mentioned", "accessed", "edited")
  - `timestamp`: Time of access

#### Core Functions

##### `calculate_recent_score(file_path: str, threshold_days: int) -> float`

Scores files based on modification recency using exponential decay.

- Returns: 0.0 (old files) → 300.0 (modified today)
- Formula: `300.0 * exp(-log(2) * days_old / threshold)`

```python
>>> score = calculate_recent_score("src/memory_heist.py", threshold_days=7)
>>> 0.0 <= score <= 300.0
```

##### `calculate_query_score(file_path: str, user_query: str) -> float`

Scores files based on matching against user query terms.

Checks multiple surfaces:
- Filename matching
- Directory path matching
- File content (first 1000 chars)

- Returns: 0.0 (no match) → 100.0 (strong match)
- Case-insensitive matching

```python
>>> query = "context discovery implementation"
>>> score = calculate_query_score("src/memory_heist.py", query)
>>> 0.0 <= score <= 100.0
```

##### `calculate_hot_score(file_path: str, session_history: list[SessionHistory]) -> float`

Scores files based on session access frequency.

- Returns: 0.0 (never accessed) → 500.0 (frequently accessed)
- Recent accesses weigh more than older ones
- Uses recency weighting: 1.0 (1 min) → 0.2 (1+ hour)

```python
>>> history = [SessionHistory("src/memory_heist.py", "accessed", time.time()) for _ in range(5)]
>>> score = calculate_hot_score("src/memory_heist.py", history)
>>> 0.0 <= score <= 500.0
```

##### `calculate_combined_score(file_path: str, user_query, session_history, config) -> ScoringResult`

Combines all scoring factors and assigns tier.

- Calculates individual scores with configurable weights
- Assigns tier based on hot score threshold
- Returns `ScoringResult` with breakdown

```python
>>> result = calculate_combined_score(
...     "src/memory_heist.py",
...     user_query="context discovery",
...     session_history=history,
...     config=RelevanceConfig()
... )
>>> result.tier in ["hot", "recent", "baseline"]
```

##### `filter_by_relevance(context, user_query, config, session_memory) -> list[FileRelevanceScore]`

Main entry point. Scans workspace and returns top-N relevant files.

```python
>>> context = ProjectContext.discover(Path.cwd())
>>> scores = filter_by_relevance(context, user_query="API endpoints")
>>> len(scores) <= 50  # Respects max_results
True
```

##### `filter_by_relevance_async(...) -> tuple[list, dict]`

Async-compatible wrapper with metadata return.

Returns tuple of:
- List of `FileRelevanceScore` objects
- Metadata dict with counts and config

### `src/memory_heist.py`

Modified `ProjectContext.discover()` to integrate relevance filtering:

```python
# New signature
context = ProjectContext.discover(
    Path.cwd(),
    use_relevance_filtering=True,  # New parameter
    user_query="what files handle authentication",
    session_memory=session,
)

# Access filtered results
filtered_files = context.relevance_results
metadata = context.relevance_metadata
```

## Usage Patterns

### Basic Usage

```python
from datetime import datetime
from pathlib import Path
from src.memory_heist import ProjectContext, SessionMemory
from src.context.relevance_scoring import RelevanceConfig

# Create project context with relevance filtering
session = SessionMemory()
context = ProjectContext.discover(
    Path.cwd(),
    use_relevance_filtering=True,
    user_query="authentication handler",
    session_memory=session,
)

# Get filtered results
results = context.relevance_results
for result in results[:10]:
    print(f"{result.file_path}: {result.score} ({result.tier})")
```

### Custom Configuration

```python
from src.context.relevance_scoring import RelevanceConfig

config = RelevanceConfig(
    recent_threshold_days=3,  # More recent focus
    query_term_weight=150.0,  # Prioritize query matching
    hot_file_weight=600.0,    # Higher hot file priority
    max_results=100,          # More results
    enable_hot_tracking=True,
)

results = filter_by_relevance(context, user_query="api", config=config)
```

### Disable Relevance Filtering

```python
# Full scan (backward compatible)
context = ProjectContext.discover(
    Path.cwd(),
    use_relevance_filtering=False,
)

# Access metadata
print(context.relevance_metadata)  # None when disabled
print(context.relevance_results)   # None when disabled
```

### Session-Based Hot Tracking

```python
# Build session memory during interactions
session = SessionMemory()
session.add("user", "Edit src/api/auth.py to fix token validation")
session.add("assistant", "I'll update src/api/auth.py now")

# Relevance filtering will automatically track file mentions
context = ProjectContext.discover(
    Path.cwd(),
    use_relevance_filtering=True,
    session_memory=session,
)

# src/api/auth.py will have higher hot score
```

## Output Format

```json
{
  "results": [
    {
      "file_path": "src/memory_heist.py",
      "score": 450,
      "tier": "hot",
      "breakdown": {
        "recent": 280,
        "query": 100,
        "hot": 50
      }
    }
  ],
  "total_candidates": 1000,
  "filtered_count": 50
}
```

## Tier Assignment Logic

Files are assigned to one of three tiers based on their scores:

| Tier | Condition | Typical Use |
|------|-----------|-------------|
| **hot** | `hot_score >= hot_file_weight * 0.5` | Actively worked-on files |
| **recent** | `recent_score >= recent_file_weight * 0.5` | Recently modified files |
| **baseline** | Neither hot nor recent | Older, less relevant files |

## Performance Characteristics

### Before (Full Scan)
- Scans all files in workspace
- Typically 1000-10000 files
- Returns unsorted list
- Prompt context includes all files

### After (Relevance Filtered)
- Scans only relevant extensions
- Filters to top-50 by relevance
- Sorted by total score
- Prompt context is targeted and relevant

**Performance gain:** ~95-99% reduction in context size for large repos.

## Backward Compatibility

The implementation maintains full backward compatibility:

1. **Old `discover()` signature still works:**
   ```python
   context = ProjectContext.discover(Path.cwd())  # Still valid
   ```

2. **Relevance filtering is opt-in:**
   ```python
   context = ProjectContext.discover(Path.cwd(), use_relevance_filtering=False)
   ```

3. **Optional properties return None when disabled:**
   ```python
   context.relevance_results  # None if filtering disabled
   context.relevance_metadata  # None if filtering disabled
   ```

## Testing

Run tests with:
```bash
python3 -m pytest tests/relevance_scoring_test.py -v
```

Test categories:
- Unit tests for each scoring function
- Integration tests for combined scoring
- Tier assignment tests
- Edge case tests (no query, no session history, etc.)
- Backward compatibility tests

## Example Output

```
src/memory_heist.py: 485.2 (hot)
  breakdown: recent=240.0, query=100.0, hot=145.2

src/api/auth.py: 312.8 (recent)
  breakdown: recent=280.0, query=100.0, hot=32.8

docs/README.md: 145.0 (baseline)
  breakdown: recent=100.0, query=45.0, hot=0.0
```

## Implementation Notes

1. **Path matching is flexible:** Supports both absolute and relative paths, normalizes for comparison.
2. **Content scanning is limited:** Only reads first 1000 chars for performance.
3. **Session history extraction:** Uses `_extract_key_files()` from session messages.
4. **Scoring is configurable:** All weights and thresholds can be customized via `RelevanceConfig`.
5. **No external dependencies:** Pure Python implementation using standard library only.

## Future Enhancements

Potential improvements:
1. **Cache hot paths:** Persist hot file tracking across sessions
2. **Machine learning:** Learn from user feedback to improve scoring
3. **File hierarchy awareness:** Weight project root files higher
4. **Dependency graph:** Score files based on import relationships
5. **Real-time tracking:** Update scores as user types queries
