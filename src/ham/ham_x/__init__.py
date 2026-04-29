"""HAM-on-X Phase 1A scaffold.

This package is intentionally non-mutating: it can shape dry-run plans,
policy decisions, audit rows, and review queue records, but it does not post
to X.
"""

from src.ham.ham_x.config import HamXConfig, load_ham_x_config

__all__ = ["HamXConfig", "load_ham_x_config"]
